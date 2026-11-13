"""Cadastro de Empregadores (a "lista suja" do trabalho análogo ao escravo) do MTE (linha 227 da fila;
fonte `mte-lista-suja`): um retrato inteiro a cada baixada (`base/retratos.py` junta os retratos numa
tabela que só cresce).

- **Formato** (conferido em 04/11/2026 nos dois CSV guardados): `;`, Latin-1, uma linha por
  empregador e estabelecimento. A coluna `CNPJ/CPF` mistura os dois; o arquivo de 2026 tem layouts
  diferentes (um com `Inclusão no CEAC`, outro com `CNAE` e trabalhadores), então só as colunas em
  comum e as opcionais são lidas.
- **Só pessoa jurídica com CNPJ de DV certo** (ADR 0075): CPF (produtor rural, pessoa física) nunca
  entra, nem o nome dele; documento que não fecha o DV também sai e é contado.
- **Chave**: CNPJ + ano da ação fiscal + estabelecimento (o `ID` do arquivo é só a posição na lista e
  muda a cada baixada, por isso não serve).
- **Sem olhar o futuro** (`disponivel_no_primeiro`): a inclusão no cadastro (a primeira data do
  campo, que às vezes traz um período `dd/mm/aaaa a dd/mm/aaaa`), nunca depois do dia do retrato.

Sem Streamlit; pandas só.
"""

import io
from collections.abc import Collection
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa

from base import cadastros_em_retrato
from base import cnpj as cnpjs
from base import retratos as motor

FONTE = "mte-lista-suja"
SEPARADOR = ";"
CODIFICACAO = "latin-1"
FORMATO_DA_DATA = "%d/%m/%Y"
COLUNAS_DA_FONTE = {
    "Ano da ação fiscal": "ano_da_acao",
    "UF": "uf",
    "Empregador": "empregador",
    "CNPJ/CPF": "documento",
    "Estabelecimento": "estabelecimento",
    "Trabalhadores envolvidos": "trabalhadores",
    "CNAE": "cnae",
    "Inclusão no Cadastro de Empregadores": "incluida_em",
}
TEXTOS = ["uf", "empregador", "estabelecimento", "cnae"]
# `consta` entra nos valores comparados: sem ele, o registro que sai do arquivo não vira a linha
# `consta` falso e continua constando (linha 907)
VALORES = ["ano_da_acao", *TEXTOS, "trabalhadores", "incluida_em", "consta"]
COLUNAS = [
    "id_na_fonte", "cnpj", "cnpj_basico", "ano_da_acao", *TEXTOS, "trabalhadores", "incluida_em",
]  # fmt: skip
PRIMEIRA_DATA = r"(\d{2}/\d{2}/\d{4})"


def ler_retrato(conteudo: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """Os empregadores de pessoa jurídica de um arquivo e a contagem do que ficou de fora."""
    bruta = pd.read_csv(
        io.BytesIO(conteudo),
        sep=SEPARADOR,
        encoding=CODIFICACAO,
        dtype=str,
        keep_default_na=False,
    )
    bruta = bruta.rename(columns=lambda c: COLUNAS_DA_FONTE.get(c.strip(), c))
    for coluna in COLUNAS_DA_FONTE.values():
        if coluna not in bruta:
            bruta[coluna] = ""
    bruta = bruta.apply(lambda serie: serie.str.strip())
    sem_digitos = bruta["documento"].str.replace(r"\D", "", regex=True)
    fora = sem_digitos.str.len().eq(
        cnpjs.TAMANHO_DO_CPF
    )  # CPF: pessoa física nunca entra
    cnpj = bruta["documento"].map(cnpjs.completo)
    valido = cnpj.map(lambda c: isinstance(c, str) and cnpjs.dv_confere(c)).astype(bool)
    tabela = bruta[valido].assign(cnpj=cnpj[valido])
    chave = (
        tabela["cnpj"] + "|" + tabela["ano_da_acao"] + "|" + tabela["estabelecimento"]
    )
    repetido = chave.duplicated(keep="first")
    tabela, chave = tabela[~repetido], chave[~repetido]
    inclusao = tabela["incluida_em"].str.extract(PRIMEIRA_DATA)[0]
    pronta = pd.DataFrame(
        {
            "id_na_fonte": chave,
            "cnpj": tabela["cnpj"].map(cnpjs.formatar),
            "cnpj_basico": tabela["cnpj"].str[: cnpjs.TAMANHO_DA_RAIZ],
            "ano_da_acao": pd.to_numeric(
                motor.sem_vazio(tabela["ano_da_acao"]), errors="coerce"
            ).astype("Int64"),
            **{c: motor.sem_vazio(tabela[c]) for c in TEXTOS},
            "trabalhadores": pd.to_numeric(
                motor.sem_vazio(tabela["trabalhadores"]), errors="coerce"
            ).astype("Int64"),
            "incluida_em": pd.to_datetime(
                inclusao, format=FORMATO_DA_DATA, errors="coerce"
            ),
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
    """A inclusão no cadastro, nunca depois do retrato; sem data, o dia dele."""
    datas = novos["incluida_em"]
    return datas.where(datas <= dia, dia).fillna(dia)


def juntar_retratos(
    lidos: list[tuple[motor.Retrato, pd.DataFrame]],
) -> tuple[pd.DataFrame, int]:
    """Os retratos lidos (do mais antigo ao mais novo) numa tabela de valores, e quantos foram pulados."""
    return motor.juntar(lidos, VALORES, disponivel_no_primeiro)


TABELA = "mte_lista_suja"
CADASTROS = (
    cadastros_em_retrato.Cadastro(
        tabela=TABELA,
        nome="empregadores",
        fonte=FONTE,
        ler=lambda retrato: ler_retrato(motor.original(retrato.caminho)),
        juntar=juntar_retratos,
        colunas=tuple(COLUNAS),
        datas=("incluida_em",),
        url_termina_em=".csv",
    ),
)


def montar(
    conexao: sa.Connection,
    pasta: Path,
    agora: datetime,
    pessoas: Collection[str] | np.ndarray | None = None,
    refazer: bool = False,
) -> dict[str, dict[str, int]]:
    """`<pasta>/mte_lista_suja/empregadores.parquet` (só o CSV do endereço mais novo)."""
    return cadastros_em_retrato.montar(
        CADASTROS, conexao, pasta, agora, pessoas, refazer
    )
