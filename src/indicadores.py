"""Indicadores de análise de ações: retorno, médias móveis, volatilidade e drawdown."""

from typing import NamedTuple

import numpy as np
import pandas as pd

DIAS_POR_ANO = 252


class PiorDrawdown(NamedTuple):
    """A pior queda do período: quanto caiu e as datas do topo, do fundo e da recuperação."""

    queda: float
    data_topo: pd.Timestamp | None
    data_fundo: pd.Timestamp | None
    data_recuperacao: pd.Timestamp | None  # None se ainda não voltou ao topo


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


def calcular_volatilidade_movel(retorno: pd.Series, janela: int = 20) -> pd.Series:
    """Volatilidade anualizada calculada numa janela deslizante de `janela` dias."""
    if janela < 2:
        raise ValueError("A janela precisa ter pelo menos 2 dias.")
    return retorno.rolling(window=janela).std() * np.sqrt(DIAS_POR_ANO)


def encontrar_pior_drawdown(fechamento: pd.Series) -> PiorDrawdown:
    """Acha a maior queda do topo ao fundo e diz quando começou e se já foi recuperada."""
    drawdown = calcular_drawdown(fechamento).dropna()
    if drawdown.empty:
        return PiorDrawdown(float("nan"), None, None, None)

    queda = float(drawdown.min())
    if queda == 0:  # o preço nunca ficou abaixo de um topo anterior
        return PiorDrawdown(0.0, None, None, None)

    data_fundo = drawdown.idxmin()
    antes = drawdown.loc[:data_fundo]
    data_topo = antes[antes == 0].index[-1]  # último dia no topo antes do fundo
    depois = drawdown.loc[data_fundo:]
    recuperou = depois[depois == 0]
    data_recuperacao = recuperou.index[0] if not recuperou.empty else None
    return PiorDrawdown(queda, data_topo, data_fundo, data_recuperacao)
