"""Rendimento de dividendos dos índices (pré-registro, seção 3; decisão 0013).

- S&P 500 (USA500): dividendo ÷ preço da base mensal de Robert Shiller, defasado 1 mês;
- demais índices: 2,5% ao ano fixos (limitação declarada).
"""

from __future__ import annotations

import io
import urllib.request

import pandas as pd

URL_DE_SHILLER = "http://www.econ.yale.edu/~shiller/data/ie_data.xls"
RENDIMENTO_FIXO = 0.025
MERCADO_COM_SHILLER = "USA500"
TEMPO_LIMITE_EM_SEGUNDOS = 120


def ler_planilha_de_shiller(conteudo: bytes) -> pd.Series:
    """Rendimento de dividendos (fração ao ano) por mês, a partir da planilha `ie_data.xls`."""
    bruto = pd.read_excel(
        io.BytesIO(conteudo), sheet_name="Data", header=7, engine="xlrd"
    )
    tabela = bruto[["Date", "P", "D"]].apply(pd.to_numeric, errors="coerce").dropna()
    return rendimento_mensal(tabela)


def rendimento_mensal(tabela: pd.DataFrame) -> pd.Series:
    """`Date` no formato de Shiller (1871.01 = janeiro de 1871; 1871.1 = outubro), `P` e `D`."""
    ano = tabela["Date"].astype(int)
    mes = ((tabela["Date"] - ano) * 100).round().astype(int)
    datas = pd.to_datetime({"year": ano, "month": mes, "day": 1})
    return pd.Series(
        (tabela["D"] / tabela["P"]).to_numpy(), index=pd.DatetimeIndex(datas)
    ).sort_index()


def baixar_shiller() -> pd.Series:
    with urllib.request.urlopen(
        URL_DE_SHILLER, timeout=TEMPO_LIMITE_EM_SEGUNDOS
    ) as resposta:
        return ler_planilha_de_shiller(resposta.read())


def rendimento_de_dividendos(
    codigo: str, indice: pd.DatetimeIndex, shiller: pd.Series | None = None
) -> pd.Series:
    """Fração ao ano em cada data; para o S&P, o mês m vale a partir do dia 1 do mês m+2."""
    if codigo != MERCADO_COM_SHILLER or shiller is None:
        return pd.Series(RENDIMENTO_FIXO, index=indice)
    serie = shiller.dropna().sort_index()
    # defasagem de 1 mês além do próprio mês (o dividendo do mês só é conhecido depois)
    serie.index = (serie.index.to_period("M") + 2).to_timestamp()
    alinhada = serie.reindex(serie.index.union(indice)).ffill().reindex(indice)
    return alinhada.fillna(RENDIMENTO_FIXO)
