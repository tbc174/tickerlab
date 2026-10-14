"""Dias úteis no Brasil com os feriados nacionais (base da curva própria, série B12)."""

from datetime import date

import pandas as pd

from base import dias_uteis as du


def _serie(*dias: str) -> pd.Series:
    return pd.Series(pd.to_datetime(list(dias)))


def test_pascoa_de_anos_conhecidos():
    assert du.pascoa(2024) == date(2024, 3, 31)
    assert du.pascoa(2025) == date(2025, 4, 20)
    assert du.pascoa(2026) == date(2026, 4, 5)


def test_feriados_moveis_e_consciencia_negra_de_2025():
    feriados = set(du.feriados_nacionais(2025))
    carnaval_e_pascoa = {date(2025, 3, 3), date(2025, 3, 4), date(2025, 4, 18)}
    assert carnaval_e_pascoa | {date(2025, 6, 19), date(2025, 11, 20)} <= feriados
    assert len(feriados) == 13
    assert date(2023, 11, 20) not in du.feriados_nacionais(
        2023
    )  # a lei é de dezembro de 2023


def test_consciencia_negra_so_conta_depois_da_lei():
    """Quem cotava antes de 22/12/2023 contava o 20/11/2024 como dia útil (o Tesouro também)."""
    lei = du.CONSCIENCIA_NEGRA_PUBLICADA_EM
    assert date(2024, 11, 20) not in du.feriados_nacionais(2024, date(2023, 12, 21))
    assert date(2024, 11, 20) in du.feriados_nacionais(2024, lei)
    antes, depois = du.dias_uteis(
        _serie("2023-12-21", "2023-12-22"), _serie("2024-11-21", "2024-11-21")
    )
    # um dia útil a menos porque começa um dia depois, e outro porque o 20/11 virou feriado
    assert antes - depois == 2


def test_dias_uteis_pulam_fim_de_semana_e_feriado():
    # semana de 17/11/2025: 17, 18, 19 e 21 (o 20 é feriado)
    assert du.dias_uteis(_serie("2025-11-17"), _serie("2025-11-24")).tolist() == [4]
    assert du.dias_uteis(_serie(), _serie()).tolist() == []


def test_proximo_dia_util_pula_sexta_santa_e_tiradentes():
    seguinte = du.proximo_dia_util(_serie("2025-04-17", "2025-10-10"))
    assert seguinte.dt.date.tolist() == [date(2025, 4, 22), date(2025, 10, 13)]
