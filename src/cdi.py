"""CDI: a taxa livre de risco brasileira, direto do Banco Central (SGS, série 12).

A série traz o CDI de cada dia útil, em % ao dia. Com ela o app responde "bati o CDI?" e usa
uma taxa livre de risco real no Sharpe, em vez de um número digitado.
"""

import pandas as pd
import requests

URL_SGS_CDI = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados"
ANOS_POR_CONSULTA = (
    9  # o Banco Central limita o tamanho da consulta (10 anos desde 2025)
)
TEMPO_LIMITE = 20  # segundos


class CDIIndisponivelError(Exception):
    """Não foi possível obter o CDI do Banco Central."""


def _consultar(inicio: pd.Timestamp, fim: pd.Timestamp) -> list[dict]:
    try:
        resposta = requests.get(
            URL_SGS_CDI,
            params={
                "formato": "json",
                "dataInicial": inicio.strftime("%d/%m/%Y"),
                "dataFinal": fim.strftime("%d/%m/%Y"),
            },
            timeout=TEMPO_LIMITE,
        )
        resposta.raise_for_status()
        return resposta.json()
    except (requests.RequestException, ValueError) as erro:
        raise CDIIndisponivelError(
            "Não consegui buscar o CDI no Banco Central agora."
        ) from erro


def baixar_cdi(inicio: pd.Timestamp, fim: pd.Timestamp) -> pd.Series:
    """CDI diário (0,0005 = 0,05% ao dia), indexado pela data, entre `inicio` e `fim`."""
    inicio, fim = pd.Timestamp(inicio).normalize(), pd.Timestamp(fim).normalize()
    if fim < inicio:
        raise ValueError("A data final deve vir depois da inicial.")
    registros: list[dict] = []
    comeco = inicio
    while comeco <= fim:
        termino = min(comeco + pd.DateOffset(years=ANOS_POR_CONSULTA), fim)
        registros += _consultar(comeco, termino)
        comeco = termino + pd.Timedelta(days=1)
    return montar_serie_do_cdi(registros)


def montar_serie_do_cdi(registros: list[dict]) -> pd.Series:
    """Converte a resposta do Banco Central (data e valor em %, como texto) numa série."""
    if not registros:
        raise CDIIndisponivelError("O Banco Central não devolveu o CDI deste período.")
    tabela = pd.DataFrame(registros)
    try:
        datas = pd.to_datetime(tabela["data"], format="%d/%m/%Y")
        valores = pd.to_numeric(tabela["valor"]) / 100
    except (KeyError, ValueError) as erro:
        raise CDIIndisponivelError("Resposta inesperada do Banco Central.") from erro
    serie = pd.Series(valores.to_numpy(), index=datas, name="CDI")
    return serie[~serie.index.duplicated()].sort_index()


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


def calcular_taxa_anual_do_cdi(
    cdi_diario: pd.Series, indice: pd.DatetimeIndex
) -> float:
    """CDI do período de `indice` convertido em taxa anual composta (0,12 = 12% ao ano)."""
    curva = curva_do_cdi(cdi_diario, indice)
    dias = (indice[-1] - indice[0]).days
    if dias < 1:
        raise ValueError("O período é curto demais para anualizar o CDI.")
    return float(curva.iloc[-1] ** (365 / dias) - 1)
