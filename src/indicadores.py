"""Indicadores de análise de ações: retorno, médias móveis, volatilidade e drawdown."""

import numpy as np
import pandas as pd

DIAS_POR_ANO = 252


def calcular_retorno_diario(fechamento: pd.Series) -> pd.Series:
    """Retorno percentual de cada dia em relação ao dia anterior (o primeiro dia fica vazio)."""
    return fechamento.pct_change()


def calcular_retorno_acumulado(retorno: pd.Series) -> pd.Series:
    """Retorno acumulado desde o início da série."""
    retorno_total = (1 + retorno).cumprod() - 1
    return retorno_total


def calcular_media_movel(fechamento: pd.Series, janela: int) -> pd.Series:
    """Média dos últimos `janela` dias."""
    mm = fechamento.rolling(window=janela).mean()
    return mm


def calcular_volatilidade_anual(retorno: pd.Series) -> float:
    """Desvio padrão dos retornos diários, anualizado."""
    vol_anual = retorno.std() * np.sqrt(DIAS_POR_ANO)
    return vol_anual


def calcular_drawdown(fechamento: pd.Series) -> pd.Series:
    """Queda de cada dia em relação ao maior preço visto até ali."""
    pico = fechamento.cummax()
    drawdown = fechamento / pico - 1
    return drawdown
