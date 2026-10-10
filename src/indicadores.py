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


def calcular_retorno_anualizado(retorno: pd.Series) -> float:
    """Retorno que o ativo teria em 1 ano se mantivesse o ritmo do período (composto)."""
    retorno = retorno.dropna()
    if retorno.empty:
        return float("nan")
    retorno_total = (1 + retorno).prod() - 1
    return (1 + retorno_total) ** (DIAS_POR_ANO / len(retorno)) - 1


def calcular_indice_sharpe(
    retorno: pd.Series, taxa_livre_de_risco: float = 0.0
) -> float:
    """Retorno anualizado acima da taxa livre de risco, por unidade de volatilidade anual."""
    volatilidade = calcular_volatilidade_anual(retorno)
    if np.isnan(volatilidade) or volatilidade == 0:
        return float("nan")  # sem oscilação não dá para dividir
    return (calcular_retorno_anualizado(retorno) - taxa_livre_de_risco) / volatilidade


def encontrar_melhor_dia(retorno: pd.Series) -> tuple[pd.Timestamp, float]:
    """Data e retorno do dia em que o ativo mais subiu."""
    retorno = retorno.dropna()
    if retorno.empty:
        raise ValueError("Série de retornos vazia: não há melhor dia.")
    return retorno.idxmax(), retorno.max()


def encontrar_pior_dia(retorno: pd.Series) -> tuple[pd.Timestamp, float]:
    """Data e retorno do dia em que o ativo mais caiu."""
    retorno = retorno.dropna()
    if retorno.empty:
        raise ValueError("Série de retornos vazia: não há pior dia.")
    return retorno.idxmin(), retorno.min()


def calcular_percentual_dias_positivos(retorno: pd.Series) -> float:
    """Fração dos dias (de 0 a 1) em que o ativo subiu. Dia parado não conta como alta."""
    retorno = retorno.dropna()
    if retorno.empty:
        return float("nan")
    return (retorno > 0).mean()


def calcular_var_historico(retorno: pd.Series, nivel: float = 0.95) -> float:
    """Perda diária que só foi superada em (1 - nivel) dos dias. Vem negativa (é uma perda)."""
    # o quantile ignora o NaN e devolve NaN se não houver nenhum dado
    return retorno.quantile(1 - nivel)
