"""Métricas de desempenho de uma estratégia, calculadas sobre o retorno diário e as operações."""

import numpy as np
import pandas as pd

from src import indicadores as ind

NIVEL_DE_CONFIANCA_95 = 1.96  # z da normal para um intervalo de 95%
NAN = float("nan")


def _curva(retorno: pd.Series) -> pd.Series:
    return (1 + retorno.dropna()).cumprod()


def calcular_retorno_total(retorno: pd.Series) -> float:
    """Quanto a estratégia ganhou (ou perdeu) no período, em fração (0,25 = +25%)."""
    curva = _curva(retorno)
    return float(curva.iloc[-1] - 1) if not curva.empty else NAN


def calcular_sortino(retorno: pd.Series, taxa_livre_de_risco: float = 0.0) -> float:
    """Como o Sharpe, mas só a volatilidade das PERDAS entra no denominador."""
    retorno = retorno.dropna()
    if retorno.empty:
        return NAN
    abaixo = np.minimum(retorno, 0.0)
    desvio_das_perdas = np.sqrt((abaixo**2).mean()) * np.sqrt(ind.DIAS_POR_ANO)
    if desvio_das_perdas == 0:
        return NAN
    anualizado = ind.calcular_retorno_anualizado(retorno)
    return float((anualizado - taxa_livre_de_risco) / desvio_das_perdas)


def calcular_calmar(retorno: pd.Series) -> float:
    """Retorno anualizado dividido pela maior queda (em módulo)."""
    curva = _curva(retorno)
    if curva.empty:
        return NAN
    maior_queda = abs(ind.calcular_drawdown(curva).min())
    if maior_queda == 0:
        return NAN
    return float(ind.calcular_retorno_anualizado(retorno) / maior_queda)


def calcular_duracao_maxima_do_drawdown(retorno: pd.Series) -> int:
    """Maior número de dias seguidos "debaixo d'água" (abaixo do topo anterior)."""
    curva = _curva(retorno)
    if curva.empty:
        return 0
    debaixo_dagua = ind.calcular_drawdown(curva) < 0
    # numera cada trecho; dentro de cada um, conta quantos dias seguidos ficou debaixo d'água
    trecho = (~debaixo_dagua).cumsum()
    dias = debaixo_dagua.groupby(trecho).cumsum()
    return int(dias.max())


def calcular_indice_ulcer(retorno: pd.Series) -> float:
    """Raiz da média dos drawdowns ao quadrado, em pontos percentuais: profundidade e duração."""
    curva = _curva(retorno)
    if curva.empty:
        return NAN
    drawdown_em_pontos = ind.calcular_drawdown(curva) * 100
    return float(np.sqrt((drawdown_em_pontos**2).mean()))


def calcular_razao_de_cauda(retorno: pd.Series) -> float:
    """Percentil 95 dos ganhos dividido pelo percentil 5 das perdas (em módulo)."""
    retorno = retorno.dropna()
    if retorno.empty:
        return NAN
    perda = abs(retorno.quantile(0.05))
    if perda == 0:
        return NAN
    return float(retorno.quantile(0.95) / perda)


def calcular_gain_to_pain(retorno: pd.Series) -> float:
    """Soma de todos os retornos dividida pela soma das perdas (em módulo)."""
    retorno = retorno.dropna()
    perdas = abs(retorno[retorno < 0].sum())
    if retorno.empty or perdas == 0:
        return NAN
    return float(retorno.sum() / perdas)


def calcular_fator_de_recuperacao(retorno: pd.Series) -> float:
    """Retorno total dividido pela pior queda: quantas vezes o lucro cobre o pior susto."""
    curva = _curva(retorno)
    if curva.empty:
        return NAN
    maior_queda = abs(ind.calcular_drawdown(curva).min())
    if maior_queda == 0:
        return NAN
    return float((curva.iloc[-1] - 1) / maior_queda)


def calcular_intervalo_do_sharpe(
    retorno: pd.Series, taxa_livre_de_risco: float = 0.0
) -> tuple[float, float, float]:
    """Sharpe anualizado com um intervalo de ~95% de confiança: (sharpe, mínimo, máximo).

    Aproximação clássica para retornos independentes (Lo, 2002): erro-padrão do Sharpe diário
    = raiz((1 + SR²/2) / T). Com poucos dados o intervalo é largo: o Sharpe é incerto.
    """
    retorno = retorno.dropna()
    if len(retorno) < 3:
        return NAN, NAN, NAN
    sharpe = ind.calcular_indice_sharpe(retorno, taxa_livre_de_risco)
    if np.isnan(sharpe):
        return NAN, NAN, NAN
    sharpe_diario = sharpe / np.sqrt(ind.DIAS_POR_ANO)
    erro = np.sqrt((1 + sharpe_diario**2 / 2) / len(retorno)) * np.sqrt(
        ind.DIAS_POR_ANO
    )
    margem = NIVEL_DE_CONFIANCA_95 * erro
    return float(sharpe), float(sharpe - margem), float(sharpe + margem)


def calcular_omega(retorno: pd.Series, limite_diario: float = 0.0) -> float:
    """Ganhos acima do limite ÷ perdas abaixo dele (acima de 1: os ganhos pesam mais)."""
    retorno = retorno.dropna()
    ganhos = float((retorno - limite_diario).clip(lower=0).sum())
    perdas = float((limite_diario - retorno).clip(lower=0).sum())
    if perdas == 0:
        return float("inf") if ganhos > 0 else NAN
    return ganhos / perdas


def calcular_kelly(retorno: pd.Series) -> float:
    """Fração do capital que maximizaria o crescimento a longo prazo: média ÷ variância diária.

    É uma aproximação contínua, muito sensível ao erro de estimar a média. Meio Kelly (a
    metade) é o que se costuma discutir na prática. Valores acima de 1 pediriam alavancagem.
    """
    retorno = retorno.dropna()
    if len(retorno) < 30 or retorno.var() == 0:
        return NAN
    return float(retorno.mean() / retorno.var())


def calcular_exposicao(posicao: pd.Series) -> float:
    """Fração média do capital que ficou aplicada (1 = sempre comprado, 0 = sempre em caixa)."""
    return float(posicao.mean()) if not posicao.empty else NAN


def resumir_operacoes(operacoes: pd.DataFrame) -> dict[str, float]:
    """Números das operações: quantidade, taxa de acerto, payoff, profit factor e expectativa.

    A operação ainda aberta entra na conta: o resultado até hoje também é resultado.
    """
    resumo = {
        "Operações": float(len(operacoes)),
        "Taxa de acerto": NAN,
        "Payoff médio": NAN,
        "Profit factor": NAN,
        "Expectativa por operação": NAN,
    }
    if operacoes.empty:
        return resumo
    ganhos = operacoes.loc[operacoes["retorno"] > 0, "retorno"]
    perdas = operacoes.loc[operacoes["retorno"] < 0, "retorno"]
    resumo["Taxa de acerto"] = float((operacoes["retorno"] > 0).mean())
    resumo["Expectativa por operação"] = float(operacoes["retorno"].mean())
    if len(ganhos) and len(perdas):
        resumo["Payoff médio"] = float(ganhos.mean() / abs(perdas.mean()))
    if len(perdas):
        resumo["Profit factor"] = float(ganhos.sum() / abs(perdas.sum()))
    return resumo


def resumir_desempenho(
    retorno: pd.Series,
    posicao: pd.Series | None = None,
    operacoes: pd.DataFrame | None = None,
    taxa_livre_de_risco: float = 0.0,
) -> dict[str, float]:
    """Todas as métricas principais num só dicionário, na ordem em que a tela as mostra."""
    resumo = {
        "Retorno total": calcular_retorno_total(retorno),
        "Retorno anualizado": ind.calcular_retorno_anualizado(retorno),
        "Volatilidade anual": ind.calcular_volatilidade_anual(retorno),
        "Índice de Sharpe": ind.calcular_indice_sharpe(retorno, taxa_livre_de_risco),
        "Índice de Sortino": calcular_sortino(retorno, taxa_livre_de_risco),
        "Maior queda": float(ind.calcular_drawdown(_curva(retorno)).min())
        if not _curva(retorno).empty
        else NAN,
        "Índice de Calmar": calcular_calmar(retorno),
        "Dias debaixo d'água (máx.)": float(
            calcular_duracao_maxima_do_drawdown(retorno)
        ),
        "Índice de Ulcer": calcular_indice_ulcer(retorno),
    }
    if posicao is not None:
        resumo["Exposição média"] = calcular_exposicao(posicao)
    if operacoes is not None:
        resumo.update(resumir_operacoes(operacoes))
    return resumo
