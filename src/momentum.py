"""Momentum de vários ativos lado a lado, com a distância da média (reversão à média) opcional.

Momentum é a tendência recente do preço: quem subiu mais nos últimos meses tende, em média, a
continuar à frente por um tempo (não sempre). Já a reversão à média aposta no contrário: o que
se afastou muito da própria média de curto prazo tende a voltar. As duas ideias disputam o
mesmo ativo em prazos diferentes, por isso o app mostra os dois números.
"""

import pandas as pd

from src import indicadores as ind

JANELAS_DO_MOMENTUM = {"1 mês": 21, "3 meses": 63, "6 meses": 126}
JANELA_DO_MOMENTUM_12_1 = 252
PULO_DO_MOMENTUM_12_1 = 21
JANELA_DO_ZSCORE = 20
MIN_DIAS = JANELA_DO_MOMENTUM_12_1 + 1


def calcular_momentos(fechamento: pd.Series) -> dict[str, float]:
    """Retornos de 1, 3 e 6 meses, o 12-1 (12 meses sem o último) e o z-score de 20 dias."""
    fechamento = fechamento.dropna()
    if len(fechamento) < MIN_DIAS:
        raise ValueError(
            f"São necessários {MIN_DIAS} dias de dados para o momentum de 12 meses."
        )
    momentos = {
        nome: float(fechamento.iloc[-1] / fechamento.iloc[-1 - dias] - 1)
        for nome, dias in JANELAS_DO_MOMENTUM.items()
    }
    # 12-1: do preço de 252 dias atrás até o de 21 dias atrás (o último mês fica de fora)
    inicio = len(fechamento) - 1 - JANELA_DO_MOMENTUM_12_1
    fim = len(fechamento) - 1 - PULO_DO_MOMENTUM_12_1
    momentos["12-1 meses"] = float(fechamento.iloc[fim] / fechamento.iloc[inicio] - 1)
    momentos["Z-score (20 dias)"] = float(
        ind.calcular_zscore(fechamento, JANELA_DO_ZSCORE).iloc[-1]
    )
    return momentos


def montar_tabela_de_momentum(
    fechamentos: dict[str, pd.Series],
) -> tuple[pd.DataFrame, list[str]]:
    """Uma linha por ativo, ordenada pelo momentum 12-1. Devolve (tabela, ativos sem histórico)."""
    linhas: dict[str, dict[str, float]] = {}
    sem_historico: list[str] = []
    for ticker, serie in fechamentos.items():
        try:
            linhas[ticker] = calcular_momentos(serie)
        except ValueError:
            sem_historico.append(ticker)
    if not linhas:
        raise ValueError("Nenhum ativo tem histórico suficiente para o momentum.")
    tabela = pd.DataFrame(linhas).T.sort_values("12-1 meses", ascending=False)
    tabela.insert(0, "Posição", range(1, len(tabela) + 1))
    return tabela, sem_historico
