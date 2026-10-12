"""Barras de 1 minuto a partir de negócios, e as conferências da qualidade delas.

Vale para qualquer fonte de negócios (IEX nos EUA; na B3, o arquivo de negócios do pregão). A barra
das 10:31 junta os negócios de 10:31:00 até 10:31:59,999 no horário da bolsa: o rótulo é o
**começo** do minuto, como no Yahoo e na maioria dos gráficos.
"""

import pandas as pd

COLUNAS_DAS_BARRAS = [
    "simbolo",
    "minuto",
    "abertura",
    "maxima",
    "minima",
    "fechamento",
    "volume",
    "negocios",
]
MINUTOS_NO_PREGAO_DOS_EUA = 390  # 9h30 às 16h, horário de Nova York


def montar_barras(negocios: pd.DataFrame, fuso: str) -> pd.DataFrame:
    """Uma linha por símbolo e minuto com negócio (minuto sem negócio não vira barra).

    `negocios` precisa das colunas instante (com fuso), simbolo, preco e quantidade, em qualquer
    ordem; `fuso` é o da bolsa ("America/New_York", "America/Sao_Paulo"). O minuto sai sem fuso,
    no horário da bolsa.
    """
    if negocios.empty:
        return pd.DataFrame(columns=COLUNAS_DAS_BARRAS)
    ordenados = negocios.sort_values("instante", kind="stable")
    minuto = (
        ordenados["instante"].dt.tz_convert(fuso).dt.floor("min").dt.tz_localize(None)
    )
    grupos = ordenados.assign(minuto=minuto).groupby(["simbolo", "minuto"], sort=True)
    barras = grupos.agg(
        abertura=("preco", "first"),
        maxima=("preco", "max"),
        minima=("preco", "min"),
        fechamento=("preco", "last"),
        volume=("quantidade", "sum"),
        negocios=("preco", "size"),
    )
    return barras.reset_index()[COLUNAS_DAS_BARRAS]


def cobertura_por_simbolo(
    barras: pd.DataFrame, minutos_no_pregao: int = MINUTOS_NO_PREGAO_DOS_EUA
) -> pd.Series:
    """Fração dos minutos do pregão que têm barra, por símbolo (1,0 = nenhum minuto vazio)."""
    return barras.groupby("simbolo")["minuto"].nunique() / minutos_no_pregao


def conferir_fechamentos(
    barras: pd.DataFrame, fechamentos_oficiais: pd.Series
) -> pd.DataFrame:
    """Último preço das barras do dia contra o fechamento oficial, por símbolo.

    `fechamentos_oficiais` tem o símbolo no índice. A diferença sai em fração (0,001 = 0,1%).
    Não precisa bater exatamente: o fechamento oficial vem do leilão da bolsa principal, e o
    último negócio de uma bolsa só pode ser de alguns segundos antes.
    """
    ultimo = barras.sort_values("minuto").groupby("simbolo")["fechamento"].last()
    tabela = pd.DataFrame(
        {"ultimo_das_barras": ultimo, "oficial": fechamentos_oficiais}
    )
    tabela = tabela.dropna()
    tabela["diferenca"] = tabela["ultimo_das_barras"] / tabela["oficial"] - 1
    return tabela
