"""Dias úteis no Brasil (base 252), com os feriados nacionais do calendário da ANBIMA.

Juros no Brasil contam dias úteis: um título que vence em 504 dias úteis está a 2 anos (504 / 252).
Os feriados nacionais são as datas fixas mais as que dependem da Páscoa (Carnaval, Sexta-feira Santa,
Corpus Christi) e, desde 2024, o Dia da Consciência Negra (Lei 14.759/2023). Feriados estaduais e
municipais não contam (é a mesma regra da ANBIMA para títulos públicos).

**Calendário como era na data:** a lei do 20/11 saiu no Diário Oficial em 22/12/2023. Antes disso, quem
calculava um título que vencia em 2029 contava os 20/11 de 2024 a 2028 como dias úteis (o preço do
Tesouro Direto confirma: até 4 dias úteis de diferença). Por isso a contagem recebe a data da cotação.
"""

from datetime import date, timedelta
from functools import cache

import numpy as np
import pandas as pd

DIAS_POR_ANO = 252
FIXOS = ((1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (12, 25))
CONSCIENCIA_NEGRA_DESDE = 2024
CONSCIENCIA_NEGRA_PUBLICADA_EM = date(2023, 12, 22)  # Lei 14.759, de 21/12/2023, no DOU


def pascoa(ano: int) -> date:
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher, calendário gregoriano)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    mes = (h + m - 7 * n + 114) // 31
    dia = (h + m - 7 * n + 114) % 31 + 1
    return date(ano, mes, dia)


def feriados_nacionais(ano: int, conhecidos_em: date | None = None) -> list[date]:
    """Os feriados nacionais do ano (inclusive os que caem no fim de semana).

    Com `conhecidos_em`, só os que já eram lei nessa data (o 20/11 só a partir de 22/12/2023).
    """
    domingo = pascoa(ano)
    moveis = [
        domingo - timedelta(days=48),  # Carnaval (segunda)
        domingo - timedelta(days=47),  # Carnaval (terça)
        domingo - timedelta(days=2),  # Sexta-feira Santa
        domingo + timedelta(days=60),  # Corpus Christi
    ]
    fixos = [date(ano, mes, dia) for mes, dia in FIXOS]
    lei_valia = conhecidos_em is None or conhecidos_em >= CONSCIENCIA_NEGRA_PUBLICADA_EM
    if ano >= CONSCIENCIA_NEGRA_DESDE and lei_valia:
        fixos.append(date(ano, 11, 20))
    return sorted(fixos + moveis)


@cache
def _feriados(
    primeiro_ano: int, ultimo_ano: int, conhecidos_em: date | None
) -> np.ndarray:
    dias = [
        d
        for ano in range(primeiro_ano, ultimo_ano + 1)
        for d in feriados_nacionais(ano, conhecidos_em)
    ]
    return np.array(dias, dtype="datetime64[D]")


def _dias(valores: pd.Series) -> np.ndarray:
    return pd.to_datetime(valores).to_numpy(dtype="datetime64[D]")


def _anos(*datas: np.ndarray) -> tuple[int, int]:
    anos = np.concatenate(datas).astype("datetime64[Y]").astype(int) + 1970
    return int(anos.min()), int(anos.max()) + 1


def dias_uteis(inicio: pd.Series, fim: pd.Series) -> np.ndarray:
    """Dias úteis de `inicio` (conta) até `fim` (não conta), linha a linha, como na ANBIMA.

    O calendário é o que se conhecia em `inicio` (o 20/11 só conta depois de virar lei).
    """
    de, ate = _dias(inicio), _dias(fim)
    if len(de) == 0:
        return np.array([], dtype=int)
    primeiro, ultimo = _anos(de, ate)
    lei = np.datetime64(CONSCIENCIA_NEGRA_PUBLICADA_EM, "D")
    resultado = np.empty(len(de), dtype=int)
    antes_da_lei = CONSCIENCIA_NEGRA_PUBLICADA_EM - timedelta(days=1)
    for depois_da_lei, conhecidos_em in ((False, antes_da_lei), (True, None)):
        linhas = (de >= lei) == depois_da_lei
        feriados = _feriados(primeiro, ultimo, conhecidos_em)
        resultado[linhas] = np.busday_count(de[linhas], ate[linhas], holidays=feriados)
    return resultado


def proximo_dia_util(dias: pd.Series) -> pd.Series:
    """O dia útil seguinte a cada data (sábado, domingo e feriado pulam)."""
    datas = _dias(dias)
    if len(datas) == 0:
        return dias.copy()
    primeiro, ultimo = _anos(datas)
    feriados = _feriados(primeiro, ultimo, None)
    seguinte = np.busday_offset(datas, 1, roll="forward", holidays=feriados)
    return pd.Series(pd.to_datetime(seguinte), index=dias.index)
