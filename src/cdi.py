"""CDI: a taxa livre de risco brasileira, direto do Banco Central (SGS, série 12).

A série traz o CDI de cada dia útil, em % ao dia. Com ela o app responde "bati o CDI?" e usa
uma taxa livre de risco real no Sharpe, em vez de um número digitado.
"""

import pandas as pd
import requests

from src import bcb

# fora de `bcb.SERIES` de propósito: a coleta do acervo percorre aquela lista
SERIE_DO_CDI = bcb.Serie(12, "CDI", "% ao dia")


class CDIIndisponivelError(Exception):
    """Não foi possível obter o CDI do Banco Central."""


def baixar_cdi(
    inicio: pd.Timestamp, fim: pd.Timestamp, buscar: bcb.Buscar | None = None
) -> pd.Series:
    """CDI diário (0,0005 = 0,05% ao dia), indexado pela data, entre `inicio` e `fim`.

    Usa o leitor do SGS de `src/bcb.py`: janelas curtas (numa janela longa o Banco Central passa
    do tempo e devolve uma página de erro) e nova tentativa quando ele falha de passagem.
    """
    inicio, fim = pd.Timestamp(inicio).normalize(), pd.Timestamp(fim).normalize()
    if fim < inicio:
        raise ValueError("A data final deve vir depois da inicial.")
    try:
        # `requests.get` lido agora, e não na definição, para os testes poderem trocá-lo
        serie = bcb.baixar_sgs(
            SERIE_DO_CDI, inicio.date(), fim.date(), buscar=buscar or requests.get
        )
    except bcb.BcbIndisponivelError as erro:
        raise CDIIndisponivelError(
            "Não consegui buscar o CDI no Banco Central agora."
        ) from erro
    return serie / 100


def curva_do_cdi(cdi_diario: pd.Series, indice: pd.DatetimeIndex) -> pd.Series:
    """Quanto R$ 1 aplicado no CDI no primeiro dia de `indice` valeria em cada dia dele.

    Começa em 1. Dias sem CDI (feriados no Brasil, quando o ativo é de fora) repetem o valor
    do dia anterior.
    """
    if len(indice) == 0:
        raise ValueError("Não há datas para a curva do CDI.")
    acumulado = (1 + cdi_diario).cumprod()
    # CDI de um dia rende do dia anterior para ele: o primeiro dia do ativo é o ponto de partida
    na_data = acumulado.reindex(acumulado.index.union(indice)).ffill()
    curva = na_data.reindex(indice).bfill()
    return curva / curva.iloc[0]


def retorno_diario_do_caixa(
    cdi_diario: pd.Series, indice: pd.DatetimeIndex
) -> pd.Series:
    """Quanto o dinheiro parado rende em cada dia de `indice` aplicado no CDI (o primeiro dia é 0)."""
    return curva_do_cdi(cdi_diario, indice).pct_change().fillna(0.0)


def calcular_taxa_anual_do_cdi(
    cdi_diario: pd.Series, indice: pd.DatetimeIndex
) -> float:
    """CDI do período de `indice` convertido em taxa anual composta (0,12 = 12% ao ano)."""
    curva = curva_do_cdi(cdi_diario, indice)
    dias = (indice[-1] - indice[0]).days
    if dias < 1:
        raise ValueError("O período é curto demais para anualizar o CDI.")
    return float(curva.iloc[-1] ** (365 / dias) - 1)
