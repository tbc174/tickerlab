"""Dados da ficha P0-2: BOVA11, a curva nominal, o CDI e a cesta de ações, em pregões.

Ficha de dados (a mesma série do começo ao fim, como o pré-registro pede):
- **BOVA11:** barras diárias do Yahoo Finance (`dados_mt5/BOVA11.SA_D1.parquet`, `auto_adjust`):
  abertura (o preço do leilão de abertura), fechamento e volume em cotas. O ETF não distribui
  proventos, então o ajuste não muda o preço. Barras de feriado (volume zero e o preço repetido)
  saem; o calendário da ficha são os pregões do BOVA11 com negócio (o volume começa em 2009).
- **WIN e DI1:** sintéticos (`dados_alavancagem`): o excesso do BOVA11 ao CDI e o prefixado de 2
  anos (curva nominal do acervo) menos o CDI.
- **CDI:** SGS 12 do Banco Central, com cache.
- **Cesta (teste b):** as 10 maiores participações da carteira teórica do Ibovespa de 03/11/2026
  (B3, lida no dia) que têm série no `dados_mt5/`; pesos iguais. Lista de hoje aplicada ao passado:
  viés de sobrevivência, declarado. Preços ajustados por proventos (o dividendo vira ganho de
  capital no IR: erra contra a estratégia).
- **Volume para o impacto:** cotas × fechamento, média dos 60 pregões anteriores
  (`tendencia_b3.volume_conhecido`).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from trader.estrategias import dados_p0_3

PASTA_DO_MT5 = dados_p0_3.PASTA_DO_MT5
PASTA_DA_PESQUISA = dados_p0_3.PASTA_DA_PESQUISA
PASTA_DA_CURVA = dados_p0_3.PASTA_DA_CURVA
ARQUIVO_DO_BOVA11 = "BOVA11.SA_D1.parquet"
# Carteira teórica do Ibovespa de 03/11/2026 (B3), em ordem de participação; ficaram de fora as que
# não têm série no dados_mt5/ (SBSP3, ITSA4, EMBJ3, B3SA3, BPAC11, ENEV3).
CESTA = (
    "PETR4",
    "VALE3",
    "ITUB4",
    "PETR3",
    "AXIA3",
    "BBDC4",
    "WEGE3",
    "ABEV3",
    "PRIO3",
    "BBAS3",
)
FONTE_DA_CESTA = "carteira teórica do Ibovespa de 03/11/2026 (B3), as 10 maiores com série no dados_mt5/"


def barras_do_yahoo(arquivo: Path) -> pd.DataFrame:
    """Abertura, fechamento e volume (cotas) de um parquet diário, sem as barras de feriado."""
    tabela = pd.read_parquet(arquivo)
    tabela.index = pd.DatetimeIndex(tabela.index).normalize()
    tabela = tabela.sort_index()
    tabela = tabela[~tabela.index.duplicated(keep="last")]
    repetido = tabela["Close"] == tabela["Close"].shift(1)
    tabela = tabela[(tabela["Volume"] > 0) | ~repetido]
    return pd.DataFrame(
        {
            "abertura": tabela["Open"].astype(float),
            "fechamento": tabela["Close"].astype(float),
            "volume": tabela["Volume"].astype(float),
        }
    )


def so_com_negocio_desde_o_inicio(barras: pd.DataFrame) -> pd.DataFrame:
    """Do primeiro pregão com volume em diante (antes disso a série não tem como medir impacto)."""
    com_volume = barras.index[barras["volume"] > 0]
    if len(com_volume) == 0:
        raise ValueError("a série não tem nenhum pregão com volume")
    return barras.loc[com_volume[0] :]


def no_calendario(barras: pd.DataFrame, pregoes: pd.DatetimeIndex) -> pd.DataFrame:
    """As barras de um papel no calendário da ficha.

    Antes do primeiro preço fica vazio (o papel não entra na cesta); depois, pregão sem barra
    repete o fechamento (abertura igual ao fechamento) e tem volume zero.
    """
    fechamento = barras["fechamento"].reindex(pregoes)
    primeiro = barras.index.min()
    depois = pregoes >= primeiro
    fechamento[depois] = fechamento[depois].ffill()
    abertura = barras["abertura"].reindex(pregoes).fillna(fechamento)
    volume = barras["volume"].reindex(pregoes).fillna(0.0)
    volume[~depois] = np.nan
    return pd.DataFrame(
        {"abertura": abertura, "fechamento": fechamento, "volume": volume}
    )


def carregar_cesta(
    pregoes: pd.DatetimeIndex, pasta: Path = PASTA_DO_MT5, papeis: tuple = CESTA
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Aberturas, fechamentos e volumes em reais dos papéis da cesta, no calendário da ficha."""
    aberturas, fechamentos, volumes = {}, {}, {}
    for papel in papeis:
        barras = no_calendario(
            barras_do_yahoo(pasta / f"{papel}.SA_D1.parquet"), pregoes
        )
        aberturas[papel] = barras["abertura"]
        fechamentos[papel] = barras["fechamento"]
        volumes[papel] = barras["volume"] * barras["fechamento"]
    return (
        pd.DataFrame(aberturas),
        pd.DataFrame(fechamentos),
        pd.DataFrame(volumes).fillna(0.0),
    )


def hash_da_tabela(tabela: pd.DataFrame | pd.Series) -> str:
    """Impressão digital dos dados que entraram (vai para a especificação da tentativa)."""
    bruto = np.ascontiguousarray(
        pd.DataFrame(tabela).round(8).fillna(-1.0).to_numpy(float)
    ).tobytes()
    return hashlib.sha256(bruto).hexdigest()
