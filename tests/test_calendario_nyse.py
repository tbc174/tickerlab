"""Calendário de pregões da NYSE: feriados pelas regras da bolsa, sem internet."""

from datetime import date

import pytest

from src import calendario_nyse as nyse


def test_feriados_de_2026_batem_com_a_lista_da_nyse():
    assert nyse.feriados(2026) == {
        date(2026, 1, 1): "Ano-Novo",
        date(2026, 1, 19): "Martin Luther King Jr. Day",
        date(2026, 2, 16): "Washington's Birthday",
        date(2026, 4, 3): "Sexta-feira Santa",
        date(2026, 5, 25): "Memorial Day",
        date(2026, 6, 19): "Juneteenth",
        date(2026, 7, 3): "Independence Day",  # 04/07 cai no sábado: folga na sexta
        date(2026, 9, 7): "Labor Day",
        date(2026, 11, 26): "Thanksgiving",
        date(2026, 12, 25): "Natal",
    }


def test_feriados_de_2027_com_folgas_no_dia_vizinho():
    feriados = nyse.feriados(2027)
    assert date(2027, 3, 26) in feriados  # Páscoa em 28/03
    assert date(2027, 6, 18) in feriados  # Juneteenth no sábado
    assert date(2027, 7, 5) in feriados  # 04/07 no domingo: folga na segunda
    assert date(2027, 12, 24) in feriados  # Natal no sábado


def test_ano_novo_no_sabado_nao_vira_folga_na_sexta():
    # Regra da NYSE: 01/01/2022 caiu no sábado e 31/12/2021 teve pregão normal.
    assert date(2021, 12, 31) not in nyse.feriados(2021)
    assert nyse.eh_pregao(date(2021, 12, 31))


def test_juneteenth_so_a_partir_de_2022():
    assert date(2021, 6, 18) not in nyse.feriados(2021)
    assert date(2022, 6, 20) in nyse.feriados(2022)  # 19/06/2022 no domingo


@pytest.mark.parametrize(
    "dia",
    [
        date(2026, 9, 7),  # Labor Day: a carga da IEX travou no 404 deste dia
        date(2026, 11, 26),  # Thanksgiving
        date(2026, 7, 4),  # sábado
        date(2025, 1, 9),  # fechamento extra: luto nacional (Jimmy Carter)
    ],
)
def test_dias_sem_pregao(dia):
    assert not nyse.eh_pregao(dia)


@pytest.mark.parametrize(
    "dia", [date(2026, 9, 8), date(2026, 10, 12), date(2026, 11, 27)]
)
def test_dias_com_pregao(dia):
    # 12/10 é feriado no Brasil, não na NYSE; 27/11 (Black Friday) fecha mais cedo, mas abre.
    assert nyse.eh_pregao(dia)
