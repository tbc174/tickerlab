"""Quem a empresa é no INPI (linha 904 da fila, lote 2): as pessoas jurídicas que depositam marca, patente e
desenho industrial ou são titulares de programa de computador. Um retrato inteiro a cada baixada
(`base/retratos.py` junta os retratos numa tabela que só cresce).

Quatro fontes do arquivista, um arquivo de titulares cada (o endereço termina no nome do arquivo):

| tabela                     | fonte                  | arquivo                    | documento             | tipo de pessoa            |
|----------------------------|------------------------|----------------------------|-----------------------|---------------------------|
| `inpi_marcas_titulares`    | `inpi-marcas`          | `MARCAS_DEPOSITANTES.csv`  | `cnpj_cpf_titular`    | `tipo_pfpj_titular`       |
| `inpi_patentes_depositantes` | `inpi-patentes-partes` | `PATENTES_DEPOSITANTES.csv` | `cgccpfdepositante`   | `tipopessoadepositante`   |
| `inpi_desenhos_depositantes` | `inpi-desenhos`      | `DI_DEPOSITANTES.csv`      | `cgccpfdepositante`   | `tipopessoadepositante`   |
| `inpi_programas_titulares` | `inpi-programas`       | `PROG_COMP_TITULAR.csv`    | `cnpj_cpf_titular`    | (não tem; só o documento) |

- **Só pessoa jurídica com CNPJ de DV certo** (ADR 0075). Entra a linha cujo documento tem 14 posições e fecha
  o DV, **e** cujo tipo de pessoa do arquivo não diz "pessoa física" (o INPI marca 8 mil depositantes de
  desenho como `F` com 14 dígitos: na dúvida, ficam fora). O CPF, o nome (do titular ou do depositante), o
  país e o estado nunca são lidos para a tabela, e inventores, autores, procuradores e representantes legais
  nem têm tabela: o arquivista já apaga nome e documento de quem não é CNPJ (`filtrar_titulares`), e a
  raiz de MEI e de empresário individual ainda fica com `trata_como_pessoa` (`base/cadastros_em_retrato.py`),
  que a porta não serve. Raiz que a Receita guardada não tem conta como pessoa.
- **Chave**: número do processo no INPI + CNPJ (a mesma empresa aparece mais de uma vez em um pedido quando
  é cotitular em ordens diferentes; fica uma linha).
- **Sem olhar o futuro** (`disponivel_no_dia`): os arquivos de titulares não têm data de publicação (a data
  do depósito está em outro arquivo e o INPI só publica o pedido depois), então o titular vale a partir do
  **dia do retrato** em que apareceu pela primeira vez. É conservador: nunca antecipa o que o público ainda
  não podia ver.
- Os arquivos são grandes (as marcas têm 6,7 milhões de linhas, 4,7 milhões com CNPJ): lê em pedaços e
  filtra cada um antes de juntar.

Sem Streamlit; pandas só.
"""

import io
from collections.abc import Collection, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import cadastros_em_retrato
from base import cnpj as cnpjs
from base import retratos as motor

PEDACO = 500_000  # linhas lidas de cada vez (o arquivo de marcas tem milhões)
VALORES = ["numero_inpi", "consta"]
COLUNAS = ["id_na_fonte", "cnpj", "cnpj_basico", "numero_inpi"]


@dataclass(frozen=True)
class Titulares:
    """Um arquivo de titulares do INPI: de que fonte vem, onde está o documento e o tipo de pessoa."""

    tabela: str
    fonte: str
    termina_em: str
    documento: str
    tipo_de_pessoa: str | None


ARQUIVOS = (
    Titulares(
        "inpi_marcas_titulares",
        "inpi-marcas",
        "MARCAS_DEPOSITANTES.csv",
        "cnpj_cpf_titular",
        "tipo_pfpj_titular",
    ),
    Titulares(
        "inpi_patentes_depositantes",
        "inpi-patentes-partes",
        "PATENTES_DEPOSITANTES.csv",
        "cgccpfdepositante",
        "tipopessoadepositante",
    ),
    Titulares(
        "inpi_desenhos_depositantes",
        "inpi-desenhos",
        "DI_DEPOSITANTES.csv",
        "cgccpfdepositante",
        "tipopessoadepositante",
    ),
    Titulares(
        "inpi_programas_titulares",
        "inpi-programas",
        "PROG_COMP_TITULAR.csv",
        "cnpj_cpf_titular",
        None,
    ),
)


def _e_pessoa_fisica(tipo: pd.Series) -> pd.Series:
    """O tipo diz pessoa física: "PESSOA FÍSICA", "pessoa física" ou só "F"."""
    minusculo = tipo.str.strip().str.lower()
    return minusculo.str.startswith("pessoa f") | minusculo.eq("f")


def _pedacos(conteudo: bytes, colunas: list[str]) -> Iterator[pd.DataFrame]:
    """O CSV em pedaços, só com as colunas pedidas (o nome do titular não é lido)."""
    yield from pd.read_csv(
        io.BytesIO(conteudo),
        usecols=colunas,
        dtype=str,
        keep_default_na=False,
        chunksize=PEDACO,
    )


def _so_empresas(
    pedaco: pd.DataFrame, arquivo: Titulares
) -> tuple[pd.DataFrame, dict[str, int]]:
    """As linhas de pessoa jurídica com CNPJ de DV certo de um pedaço, e o que ficou de fora."""
    cnpj = pedaco[arquivo.documento].map(cnpjs.completo)
    valido = cnpj.map(lambda c: isinstance(c, str) and cnpjs.dv_confere(c)).astype(bool)
    fisica = (
        _e_pessoa_fisica(pedaco[arquivo.tipo_de_pessoa])
        if arquivo.tipo_de_pessoa
        else pd.Series(False, index=pedaco.index)
    )
    dentro = valido & ~fisica
    tabela = pd.DataFrame(
        {"cnpj": cnpj[dentro], "numero_inpi": pedaco.loc[dentro, "numero_inpi"]}
    )
    contagem = {
        "linhas": len(pedaco),
        "sem_cnpj_valido": int((~valido).sum()),
        "tipo_pessoa_fisica": int((valido & fisica).sum()),
    }
    return tabela, contagem


def ler_retrato(
    conteudo: bytes, arquivo: Titulares
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os titulares pessoa jurídica de um arquivo e a contagem do que ficou de fora."""
    colunas = ["numero_inpi", arquivo.documento]
    if arquivo.tipo_de_pessoa:
        colunas.append(arquivo.tipo_de_pessoa)
    achados: list[pd.DataFrame] = []
    contagem = {"linhas": 0, "sem_cnpj_valido": 0, "tipo_pessoa_fisica": 0}
    for pedaco in _pedacos(conteudo, colunas):
        tabela, parcial = _so_empresas(pedaco, arquivo)
        achados.append(tabela)
        for chave, valor in parcial.items():
            contagem[chave] += valor
    juntos = (
        pd.concat(achados, ignore_index=True)
        if achados
        else pd.DataFrame({"cnpj": [], "numero_inpi": []}, dtype=str)
    )
    juntos["id_na_fonte"] = juntos["numero_inpi"] + "|" + juntos["cnpj"]
    repetido = juntos["id_na_fonte"].duplicated(keep="first")
    contagem["id_repetido"] = int(repetido.sum())
    unicos = juntos[~repetido]
    pronta = pd.DataFrame(
        {
            "id_na_fonte": unicos["id_na_fonte"],
            "cnpj": unicos["cnpj"].map(cnpjs.formatar),
            "cnpj_basico": unicos["cnpj"].str[: cnpjs.TAMANHO_DA_RAIZ],
            "numero_inpi": unicos["numero_inpi"],
        }
    )[COLUNAS].reset_index(drop=True)
    return pronta, contagem


def disponivel_no_dia(novos: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    """O titular do primeiro retrato vale desde o dia dele (o arquivo não traz data de publicação)."""
    return pd.Series(dia, index=novos.index)


def juntar_retratos(
    lidos: list[tuple[motor.Retrato, pd.DataFrame]],
) -> tuple[pd.DataFrame, int]:
    """Os retratos lidos (do mais antigo ao mais novo) numa tabela de valores, e quantos foram pulados."""
    return motor.juntar(lidos, VALORES, disponivel_no_dia)


def _cadastro(arquivo: Titulares) -> cadastros_em_retrato.Cadastro:
    return cadastros_em_retrato.Cadastro(
        tabela=arquivo.tabela,
        nome="titulares",
        fonte=arquivo.fonte,
        ler=lambda retrato: ler_retrato(motor.original(retrato.caminho), arquivo),
        juntar=juntar_retratos,
        colunas=tuple(COLUNAS),
        datas=(),
        url_termina_em=arquivo.termina_em,
    )


CADASTROS = tuple(_cadastro(arquivo) for arquivo in ARQUIVOS)


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """`<pasta>/<tabela>/titulares.parquet` para cada um dos quatro arquivos com retrato guardado.

    O resumo é por tabela (o nome do cadastro, `titulares`, é o mesmo nas quatro)."""
    resumo: dict[str, dict[str, int]] = {}
    for cadastro in CADASTROS:
        feito = cadastros_em_retrato.montar(
            (cadastro,), conexao, pasta, agora, pessoas, refazer
        )
        if feito:
            resumo[cadastro.tabela] = feito[cadastro.nome]
    return resumo
