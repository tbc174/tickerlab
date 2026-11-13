"""Licitantes inidôneos do TCU (linha 904 da fila, lote 2; fonte `tcu-inidoneos`): um retrato inteiro a cada
baixada (`base/retratos.py` junta os retratos numa tabela que só cresce).

- **Formato** (conferido em 13/11/2026 nos dois retratos guardados): JSON por linha, comprimido. A coluna
  `cpf_cnpj` mistura os dois documentos.
- **Só pessoa jurídica com CNPJ de DV certo** (ADR 0075): documento de 11 dígitos (CPF) nunca entra, e a
  coluna `nome` não é lida (razão social vem da Receita pelo CNPJ). Documento que não fecha o DV também
  sai e é contado. A raiz de MEI e de empresário individual fica com `trata_como_pessoa`
  (`base/cadastros_em_retrato.py`) e a porta não a serve; raiz que a Receita guardada não tem conta como
  pessoa.
- **`uf` e `municipio` não entram**: a UF vem sempre a do TCU (DF), não a da empresa.
- **Chave**: CNPJ + número do processo (a mesma empresa pode ter mais de um processo).
- **Sem olhar o futuro** (`disponivel_no_primeiro`): o que for depois, o acórdão ou o trânsito em julgado
  (a inidoneidade só vale com o trânsito), nunca depois do dia do retrato. `data_final` (fim da
  proibição) é uma data futura anunciada na própria decisão, não uma informação nova.

Sem Streamlit; pandas só.
"""

import json
from collections.abc import Collection
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import cadastros_em_retrato
from base import cnpj as cnpjs
from base import retratos as motor

FONTE = "tcu-inidoneos"
FUSO_DO_TCU = "America/Sao_Paulo"  # as datas vêm em UTC, às 3h: meia-noite de Brasília
DATAS = ["data_acordao", "data_transito_julgado", "data_final"]
TEXTOS = ["processo", "deliberacao"]
VALORES = [*TEXTOS, *DATAS, "consta"]
COLUNAS = ["id_na_fonte", "cnpj", "cnpj_basico", *TEXTOS, *DATAS]


def _data(texto: pd.Series) -> pd.Series:
    """O dia (de Brasília) de um carimbo ISO em UTC; vazio ou ilegível vira nulo."""
    carimbo = pd.to_datetime(texto, utc=True, errors="coerce")
    return carimbo.dt.tz_convert(FUSO_DO_TCU).dt.tz_localize(None).dt.normalize()


def _registros(conteudo: bytes) -> pd.DataFrame:
    linhas = [json.loads(linha) for linha in conteudo.splitlines() if linha.strip()]
    colunas = ["cpf_cnpj", *TEXTOS, *DATAS]
    bruta = pd.DataFrame(linhas, columns=colunas, dtype=str)  # o `nome` nunca é lido
    return bruta.fillna("").apply(lambda serie: serie.str.strip())


def ler_retrato(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os inidôneos de pessoa jurídica de um arquivo e a contagem do que ficou de fora."""
    bruta = _registros(conteudo)
    sem_digitos = bruta["cpf_cnpj"].str.replace(r"\D", "", regex=True)
    fora = sem_digitos.str.len().eq(
        cnpjs.TAMANHO_DO_CPF
    )  # CPF: pessoa física nunca entra
    cnpj = bruta["cpf_cnpj"].map(cnpjs.completo)
    valido = cnpj.map(lambda c: isinstance(c, str) and cnpjs.dv_confere(c)).astype(bool)
    tabela = bruta[valido].assign(cnpj=cnpj[valido])
    chave = tabela["cnpj"] + "|" + tabela["processo"]
    repetido = chave.duplicated(keep="first")
    tabela, chave = tabela[~repetido], chave[~repetido]
    pronta = pd.DataFrame(
        {
            "id_na_fonte": chave,
            "cnpj": tabela["cnpj"].map(cnpjs.formatar),
            "cnpj_basico": tabela["cnpj"].str[: cnpjs.TAMANHO_DA_RAIZ],
            **{c: motor.sem_vazio(tabela[c]) for c in TEXTOS},
            **{c: _data(tabela[c]) for c in DATAS},
        }
    )[COLUNAS].reset_index(drop=True)
    contagem = {
        "linhas": len(bruta),
        "pessoa_fisica": int(fora.sum()),
        "cnpj_invalido": int((~valido & ~fora).sum()),
        "id_repetido": int(repetido.sum()),
    }
    return pronta, contagem


def disponivel_no_primeiro(novos: pd.DataFrame, dia: pd.Timestamp) -> pd.Series:
    """O acórdão ou o trânsito em julgado (o que for depois), nunca depois do retrato; sem data, o dia dele."""
    datas = novos[["data_acordao", "data_transito_julgado"]].max(axis=1)
    return datas.where(datas <= dia, dia).fillna(dia)


def juntar_retratos(
    lidos: list[tuple[motor.Retrato, pd.DataFrame]],
) -> tuple[pd.DataFrame, int]:
    """Os retratos lidos (do mais antigo ao mais novo) numa tabela de valores, e quantos foram pulados."""
    return motor.juntar(lidos, VALORES, disponivel_no_primeiro)


TABELA = "tcu_inidoneos"
CADASTROS = (
    cadastros_em_retrato.Cadastro(
        tabela=TABELA,
        nome="inidoneos",
        fonte=FONTE,
        ler=lambda retrato: ler_retrato(motor.original(retrato.caminho)),
        juntar=juntar_retratos,
        colunas=tuple(COLUNAS),
        datas=tuple(DATAS),
        url_termina_em=None,
    ),
)


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """`<pasta>/tcu_inidoneos/inidoneos.parquet`."""
    return cadastros_em_retrato.montar(
        CADASTROS, conexao, pasta, agora, pessoas, refazer
    )
