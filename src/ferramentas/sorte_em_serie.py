"""Sorte em série: muitas "estratégias" de cara ou coroa, e a melhor parece genial.

Cada estratégia ganha ou perde `MOVIMENTO_DIARIO` a cada dia, no cara ou coroa: nenhuma tem
vantagem nenhuma. Mesmo assim, entre 100 delas, a melhor costuma ter um Sharpe que muita gente chamaria
de excelente. É o problema de testar muitas ideias e mostrar só a melhor, que a ficha "Foi sorte?"
do TickerLab corrige contando as tentativas.
"""

import statistics
from dataclasses import dataclass

from src.ferramentas.aleatorio import Gerador

MOVIMENTO_DIARIO = 0.01  # cada dia: +1% ou -1%
DIAS_POR_ANO = 252  # para anualizar o Sharpe, como no resto do TickerLab
LIMITE_DO_SHARPE = 1.0  # o Sharpe que muita gente chama de "estratégia boa"
ESTRATEGIAS_MAXIMAS = 1000
DIAS_MAXIMOS = 2520  # 10 anos


@dataclass(frozen=True)
class ResultadoDaSorte:
    estrategias: int
    dias: int
    curva_da_melhor: list[float]  # patrimônio dia a dia, começando em 1
    curva_da_mediana: list[float]
    curva_da_pior: list[float]
    retorno_da_melhor: float
    retorno_da_mediana: float
    retorno_da_pior: float
    sharpe_da_melhor: float
    com_sharpe_acima_de_1: int
    lucraram: int
    media_dos_retornos_diarios: float


def sharpe(retornos: list[float]) -> float:
    """Sharpe anualizado sem a taxa livre de risco: média / desvio-padrão × √252."""
    desvio = statistics.stdev(retornos)
    return statistics.mean(retornos) / desvio * DIAS_POR_ANO**0.5 if desvio else 0.0


def _curva(retornos: list[float]) -> list[float]:
    curva = [1.0]
    for r in retornos:
        curva.append(curva[-1] * (1 + r))
    return curva


def simular(estrategias: int, dias: int, semente: int) -> ResultadoDaSorte:
    """`estrategias` estratégias de cara ou coroa por `dias` dias, todas da mesma `semente`."""
    if estrategias < 2 or estrategias > ESTRATEGIAS_MAXIMAS:
        raise ValueError(f"Use de 2 a {ESTRATEGIAS_MAXIMAS} estratégias.")
    if dias < 2 or dias > DIAS_MAXIMOS:
        raise ValueError(f"Use de 2 a {DIAS_MAXIMOS} dias.")
    gerador = Gerador(semente)
    todas = [
        [
            MOVIMENTO_DIARIO if gerador.proximo() < 0.5 else -MOVIMENTO_DIARIO
            for _ in range(dias)
        ]
        for _ in range(estrategias)
    ]
    curvas = [_curva(retornos) for retornos in todas]
    # da pior para a melhor pelo valor final; empate fica na ordem em que foi sorteada
    ordem = sorted(range(estrategias), key=lambda k: curvas[k][-1])
    melhor, mediana, pior = ordem[-1], ordem[(estrategias - 1) // 2], ordem[0]
    sharpes = [sharpe(retornos) for retornos in todas]
    return ResultadoDaSorte(
        estrategias=estrategias,
        dias=dias,
        curva_da_melhor=curvas[melhor],
        curva_da_mediana=curvas[mediana],
        curva_da_pior=curvas[pior],
        retorno_da_melhor=curvas[melhor][-1] - 1,
        retorno_da_mediana=curvas[mediana][-1] - 1,
        retorno_da_pior=curvas[pior][-1] - 1,
        sharpe_da_melhor=sharpes[melhor],
        com_sharpe_acima_de_1=sum(s > LIMITE_DO_SHARPE for s in sharpes),
        lucraram=sum(curva[-1] > 1 for curva in curvas),
        media_dos_retornos_diarios=statistics.mean(
            r for retornos in todas for r in retornos
        ),
    )
