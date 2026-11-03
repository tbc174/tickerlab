"""Calendário das estratégias quant: pregões da B3, execução no dia seguinte, WIN, DI1 e cripto."""

from datetime import date, timedelta

import pytest

from trader import calendario

# --- Pregões da B3 ---------------------------------------------------------------------


def test_eh_pregao_pula_fim_de_semana_e_feriado():
    assert calendario.eh_pregao(date(2025, 11, 3))  # segunda
    assert not calendario.eh_pregao(date(2025, 11, 1))  # sábado
    assert not calendario.eh_pregao(date(2025, 11, 20))  # Consciência Negra
    assert not calendario.eh_pregao(date(2024, 12, 24))  # véspera de Natal


def test_proximo_pregao_e_pregao_anterior():
    sexta = date(2025, 11, 14)  # 15/11 é sábado e feriado; 17/11 é segunda
    assert calendario.proximo_pregao(sexta) == date(2025, 11, 17)
    assert calendario.pregao_anterior(date(2025, 11, 17)) == sexta
    # véspera de Carnaval de 2025 (03 e 04/03 fechados): sexta 28/02 → quarta 05/03
    assert calendario.proximo_pregao(date(2025, 2, 28)) == date(2025, 3, 5)
    # é sempre o seguinte, mesmo partindo de um pregão
    assert calendario.proximo_pregao(date(2025, 11, 17)) == date(2025, 11, 18)


def test_pregoes_entre_datas_conta_as_pontas_e_pula_os_feriados():
    dias = calendario.pregoes(date(2025, 4, 17), date(2025, 4, 23))
    # 18/04 Sexta-feira Santa, 19 e 20 fim de semana, 21/04 Tiradentes
    assert dias == [date(2025, 4, 17), date(2025, 4, 22), date(2025, 4, 23)]
    assert calendario.pregoes(date(2025, 4, 19), date(2025, 4, 20)) == []


def test_primeiro_e_ultimo_pregao_do_mes():
    assert calendario.primeiro_pregao_do_mes(2025, 1) == date(2025, 1, 2)
    assert calendario.ultimo_pregao_do_mes(2024, 12) == date(
        2024, 12, 30
    )  # 31/12 fechado
    assert calendario.ultimo_pregao_do_mes(2025, 11) == date(2025, 11, 28)


# --- Execução no dia seguinte (sem olhar o futuro) ---------------------------------------


def test_proxima_execucao_na_b3_e_o_pregao_seguinte_ao_sinal():
    # sinal fechado na sexta 14/11/2025 executa na segunda 17/11
    assert calendario.proxima_execucao(date(2025, 11, 14)) == date(2025, 11, 17)
    # sinal num dia sem pregão (sábado) também espera o próximo pregão
    assert calendario.proxima_execucao(date(2025, 11, 15)) == date(2025, 11, 17)


def test_proxima_execucao_em_cripto_e_o_dia_corrido_seguinte():
    assert calendario.proxima_execucao(date(2025, 11, 14), mercado="cripto") == date(
        2025, 11, 15
    )
    assert calendario.proxima_execucao(date(2025, 12, 31), mercado="cripto") == date(
        2026, 1, 1
    )


def test_proxima_execucao_rejeita_mercado_desconhecido():
    with pytest.raises(ValueError, match="mercado"):
        calendario.proxima_execucao(date(2025, 11, 14), mercado="nyse")


def test_proxima_execucao_nunca_e_o_proprio_dia_nem_o_passado():
    dia = date(2024, 1, 1)
    while dia <= date(2026, 12, 31):
        for mercado in calendario.MERCADOS:
            assert calendario.proxima_execucao(dia, mercado=mercado) > dia
        dia += timedelta(days=1)


def test_cortar_o_futuro_nao_muda_o_passado():
    inteiro = calendario.pregoes(date(2024, 1, 1), date(2026, 12, 31))
    cortado = calendario.pregoes(date(2024, 1, 1), date(2025, 6, 30))
    assert inteiro[: len(cortado)] == cortado
    assert calendario.dias_de_cripto(date(2024, 1, 1), date(2024, 1, 10))[:3] == [
        date(2024, 1, 1),
        date(2024, 1, 2),
        date(2024, 1, 3),
    ]


# --- Leilões ------------------------------------------------------------------------------


def test_leiloes_tem_abertura_antes_do_fechamento_e_dentro_do_mesmo_pregao():
    assert calendario.LEILAO_DE_ABERTURA.inicio < calendario.LEILAO_DE_ABERTURA.fim
    assert calendario.LEILAO_DE_FECHAMENTO.inicio < calendario.LEILAO_DE_FECHAMENTO.fim
    assert calendario.LEILAO_DE_ABERTURA.fim <= calendario.LEILAO_DE_FECHAMENTO.inicio


def test_momento_do_leilao_junta_o_pregao_com_a_hora():
    momento = calendario.momento_do_leilao(
        date(2025, 11, 17), calendario.LEILAO_DE_FECHAMENTO
    )
    assert momento.date() == date(2025, 11, 17)
    assert momento.time() == calendario.LEILAO_DE_FECHAMENTO.fim


# --- WIN (índice futuro) --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ano", "mes", "esperado"),
    [
        (2024, 2, date(2024, 2, 14)),  # 15 é quinta: quarta 14
        (2024, 4, date(2024, 4, 17)),  # 15 é segunda: quarta 17
        (
            2024,
            6,
            date(2024, 6, 12),
        ),  # 15 é sábado: quarta 12 (3 dias), não 19 (4 dias)
        (2024, 8, date(2024, 8, 14)),
        (2024, 10, date(2024, 10, 16)),
        (2024, 12, date(2024, 12, 18)),  # 15 é domingo: quarta 18
        (2025, 2, date(2025, 2, 12)),
        (2025, 4, date(2025, 4, 16)),
        (2025, 6, date(2025, 6, 18)),
        (2025, 8, date(2025, 8, 13)),
        (2025, 10, date(2025, 10, 15)),  # o próprio dia 15 é quarta
        (2025, 12, date(2025, 12, 17)),
        (2026, 2, date(2026, 2, 18)),  # 15 é domingo: quarta 18 (Carnaval é 16 e 17)
        (2026, 4, date(2026, 4, 15)),
    ],
)
def test_vencimento_do_win_e_a_quarta_mais_proxima_do_dia_15(ano, mes, esperado):
    assert calendario.vencimento_do_win(ano, mes) == esperado
    assert esperado.weekday() == 2


def test_vencimento_do_win_so_nos_meses_pares():
    with pytest.raises(ValueError, match="pares"):
        calendario.vencimento_do_win(2025, 3)


def test_vencimento_do_win_numa_quarta_sem_pregao_vai_para_o_pregao_seguinte(
    monkeypatch,
):
    # Finge que a quarta 17/12/2025 fechou (luto): o vencimento passa para quinta 18
    monkeypatch.setitem(calendario.FECHAMENTOS_EXTRAS, date(2025, 12, 17), "teste")
    calendario.feriados.cache_clear()
    try:
        assert calendario.vencimento_do_win(2025, 12) == date(2025, 12, 18)
    finally:
        calendario.feriados.cache_clear()


def test_codigo_do_win():
    assert calendario.codigo_do_win(2025, 12) == "WINZ25"
    assert calendario.codigo_do_win(2026, 2) == "WING26"


def test_rolagem_do_win_e_o_pregao_anterior_ao_vencimento():
    assert calendario.rolagem_do_win(2025, 12) == date(2025, 12, 16)
    # vencimento na quarta 18/06/2025; a rolagem é terça 17
    assert calendario.rolagem_do_win(2025, 6) == date(2025, 6, 17)


def test_contrato_do_win_em_vigor_troca_na_rolagem():
    assert calendario.contrato_do_win(date(2025, 11, 17)) == "WINZ25"
    assert (
        calendario.contrato_do_win(date(2025, 12, 16)) == "WINZ25"
    )  # rolagem: sai no fim
    assert (
        calendario.contrato_do_win(date(2025, 12, 17)) == "WING26"
    )  # vencimento: já trocou
    assert calendario.contrato_do_win(date(2025, 12, 18)) == "WING26"
    assert calendario.contrato_do_win(date(2024, 12, 18)) == "WING25"  # virada de ano


def test_vencimentos_do_win_entre_datas():
    assert calendario.vencimentos_do_win(date(2025, 11, 1), date(2026, 3, 1)) == [
        date(2025, 12, 17),
        date(2026, 2, 18),
    ]


# --- DI1 (juros) ----------------------------------------------------------------------------


def test_vencimento_do_di1_e_o_primeiro_pregao_do_mes():
    assert calendario.vencimento_do_di1(2026, 1) == date(2026, 1, 2)  # 01/01 é feriado
    assert calendario.vencimento_do_di1(2025, 11) == date(2025, 11, 3)  # 01/11 é sábado


def test_codigo_do_di1_vale_para_todos_os_meses():
    assert calendario.codigo_do_di1(2027, 1) == "DI1F27"
    assert calendario.codigo_do_di1(2026, 7) == "DI1N26"
    assert calendario.codigo_do_di1(2026, 12) == "DI1Z26"


def test_di1_de_janeiro_mais_perto_do_prazo():
    # de 17/11/2025, 2 anos cai em 17/11/2027: janeiro de 2028 é mais perto que o de 2027
    assert calendario.di1_de_janeiro(date(2025, 11, 17), anos=2) == "DI1F28"
    assert calendario.di1_de_janeiro(date(2025, 3, 1), anos=1) == "DI1F26"


# --- Cripto (365 dias) ------------------------------------------------------------------------


def test_dias_de_cripto_sao_todos_os_dias_corridos():
    dias = calendario.dias_de_cripto(date(2025, 12, 24), date(2026, 1, 2))
    assert len(dias) == 10
    assert dias[0] == date(2025, 12, 24)
    assert dias[-1] == date(2026, 1, 2)
    assert calendario.dias_de_cripto(date(2025, 1, 2), date(2025, 1, 1)) == []


def test_dias_de_negociacao_escolhe_o_calendario_pelo_mercado():
    inicio, fim = date(2025, 11, 14), date(2025, 11, 17)
    assert calendario.dias_de_negociacao(inicio, fim, "b3") == [inicio, fim]
    assert len(calendario.dias_de_negociacao(inicio, fim, "cripto")) == 4
