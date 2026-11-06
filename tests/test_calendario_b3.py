"""Calendário de pregões da B3: feriados pelas regras da bolsa, sem internet."""

from datetime import date

from src import calendario_b3 as b3


def test_feriados_de_2026_batem_com_a_lista_da_b3():
    assert b3.feriados(2026) == {
        date(2026, 1, 1): "Ano-Novo",
        date(2026, 2, 16): "Carnaval (segunda)",
        date(2026, 2, 17): "Carnaval (terça)",
        date(2026, 4, 3): "Sexta-feira Santa",
        date(2026, 4, 21): "Tiradentes",
        date(2026, 5, 1): "Dia do Trabalho",
        date(2026, 6, 4): "Corpus Christi",
        date(2026, 9, 7): "Independência",
        date(2026, 10, 12): "Nossa Senhora Aparecida",
        date(2026, 11, 2): "Finados",
        date(2026, 11, 20): "Consciência Negra",
        date(2026, 12, 24): "Véspera de Natal",
        date(2026, 12, 25): "Natal",
        date(2026, 12, 31): "Véspera de Ano-Novo",
    }  # 15/11 cai no domingo: sem folga na segunda


def test_feriado_no_fim_de_semana_nao_vira_folga_em_dia_util():
    assert date(2026, 11, 15) not in b3.feriados(2026)  # domingo
    assert date(2026, 11, 16) not in b3.feriados(2026)


def test_consciencia_negra_so_a_partir_de_2024():
    assert date(2023, 11, 20) not in b3.feriados(2023)
    assert date(2024, 11, 20) in b3.feriados(2024)


def test_carnaval_e_corpus_christi_seguem_a_pascoa():
    feriados = b3.feriados(2025)  # Páscoa em 20/04
    assert date(2025, 3, 3) in feriados
    assert date(2025, 3, 4) in feriados
    assert date(2025, 6, 19) in feriados


def test_eh_pregao():
    assert not b3.eh_pregao(date(2026, 10, 12))  # feriado (segunda)
    assert not b3.eh_pregao(date(2026, 10, 10))  # sábado
    assert b3.eh_pregao(date(2026, 10, 13))
