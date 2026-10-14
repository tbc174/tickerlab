"""DARF de ações (src/ferramentas/darf.py), com as regras de src/regras_de_imposto.py.

Regras (Perguntas e Respostas IRPF 2026 da Receita): 15% nas operações comuns e 20% no day trade
(706); isento quando as vendas comuns de ações no mês não passam de R$ 20.000 (707); prejuízo
compensa lucro do mesmo tipo, no mês ou depois, sem prazo (709 a 711); o IR retido abate o imposto
do mês e o que sobra fica para os seguintes (706); DARF abaixo de R$ 10 acumula (Lei 9.430, art. 68).
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.ferramentas import darf
from src.ferramentas.darf import Mes, Saldos

ZERO = Saldos()


def test_vendas_ate_20_mil_com_lucro_sao_isentas():
    a = darf.apurar_mes(Mes(vendas_comuns=15_000, resultado_comum=2_000), ZERO)
    assert a.isento
    assert a.darf == 0
    assert a.saldos_seguintes == ZERO


def test_vendas_acima_de_20_mil_pagam_15_por_cento_menos_o_retido():
    mes = Mes(vendas_comuns=30_000, resultado_comum=3_000, irrf_comum=1.5)
    a = darf.apurar_mes(mes, ZERO)
    assert not a.isento
    assert a.imposto_comum == pytest.approx(450)
    assert a.darf == pytest.approx(448.5)


def test_prejuizo_de_um_mes_abate_o_lucro_do_seguinte():
    meses = [
        Mes(vendas_comuns=25_000, resultado_comum=-2_000),
        Mes(vendas_comuns=40_000, resultado_comum=3_000),
    ]
    primeiro, segundo = darf.apurar_meses(meses, ZERO)
    assert primeiro.saldos_seguintes.prejuizo_comum == 2_000
    assert segundo.base_comum == pytest.approx(1_000)
    assert segundo.darf == pytest.approx(150)
    assert segundo.saldos_seguintes.prejuizo_comum == 0


def test_prejuizo_de_mes_isento_tambem_fica_para_depois():
    a = darf.apurar_mes(Mes(vendas_comuns=10_000, resultado_comum=-500), ZERO)
    assert a.saldos_seguintes.prejuizo_comum == 500


def test_lucro_isento_nao_gasta_o_prejuizo_acumulado():
    a = darf.apurar_mes(
        Mes(vendas_comuns=15_000, resultado_comum=2_000), Saldos(prejuizo_comum=800)
    )
    assert a.isento
    assert a.saldos_seguintes.prejuizo_comum == 800


def test_day_trade_paga_20_por_cento_sem_isencao():
    a = darf.apurar_mes(
        Mes(vendas_comuns=5_000, resultado_day_trade=1_000, irrf_day_trade=10), ZERO
    )
    assert a.imposto_day_trade == pytest.approx(200)
    assert a.darf == pytest.approx(190)


def test_prejuizo_de_day_trade_nao_abate_lucro_comum():
    a = darf.apurar_mes(
        Mes(vendas_comuns=50_000, resultado_comum=1_000, resultado_day_trade=-1_000),
        ZERO,
    )
    assert a.imposto_comum == pytest.approx(150)
    assert a.saldos_seguintes.prejuizo_day_trade == 1_000
    assert a.saldos_seguintes.prejuizo_comum == 0


def test_darf_abaixo_de_10_reais_acumula_ate_passar():
    primeiro = darf.apurar_mes(Mes(vendas_comuns=30_000, resultado_comum=40), ZERO)
    assert primeiro.darf == 0
    assert primeiro.saldos_seguintes.imposto_abaixo_do_minimo == pytest.approx(6)
    segundo = darf.apurar_mes(
        Mes(vendas_comuns=30_000, resultado_comum=40), primeiro.saldos_seguintes
    )
    assert segundo.darf == pytest.approx(12)
    assert segundo.saldos_seguintes.imposto_abaixo_do_minimo == 0


def test_ir_retido_que_sobra_fica_para_os_meses_seguintes():
    a = darf.apurar_mes(
        Mes(vendas_comuns=30_000, resultado_comum=-100, irrf_comum=1.5), ZERO
    )
    assert a.darf == 0
    assert a.saldos_seguintes.irrf_a_compensar == pytest.approx(1.5)
    b = darf.apurar_mes(
        Mes(vendas_comuns=30_000, resultado_comum=1_100), a.saldos_seguintes
    )
    # 1.100 de lucro − 100 de prejuízo = 1.000; 15% = 150; menos 1,50 retido no mês anterior
    assert b.darf == pytest.approx(148.5)


def test_codigo_e_prazo_do_darf():
    assert darf.CODIGO_DO_DARF == "6015"
    assert darf.vencimento(2026, 10) == "último dia útil de novembro de 2026"
    assert darf.vencimento(2026, 12) == "último dia útil de janeiro de 2027"


@pytest.mark.parametrize(
    ("mes", "saldos", "mensagem"),
    [
        (Mes(vendas_comuns=-1), ZERO, "vendas"),
        (Mes(irrf_comum=-1), ZERO, "retido"),
        (Mes(), Saldos(prejuizo_comum=-1), "prejuízo"),
        (Mes(), Saldos(imposto_abaixo_do_minimo=10), "abaixo"),
    ],
)
def test_entradas_invalidas(mes, saldos, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        darf.apurar_mes(mes, saldos)


@given(
    resultados=st.lists(st.floats(-50_000, 50_000), min_size=1, max_size=12),
    vendas=st.floats(0, 200_000),
)
def test_nunca_paga_mais_que_15_por_cento_dos_meses_com_lucro(resultados, vendas):
    """O prejuízo só compensa para a frente: um prejuízo depois do lucro não devolve imposto."""
    apuracoes = darf.apurar_meses(
        [Mes(vendas_comuns=vendas, resultado_comum=r) for r in resultados], ZERO
    )
    pago = sum(a.darf for a in apuracoes)
    a_pagar_no_fim = apuracoes[-1].saldos_seguintes.imposto_abaixo_do_minimo
    lucros = sum(max(r, 0) for r in resultados)
    assert pago + a_pagar_no_fim <= 0.15 * lucros + 1e-6
    if vendas <= 20_000:
        assert pago == 0  # tudo isento
    assert all(a.darf == 0 or a.darf >= darf.DARF_MINIMO for a in apuracoes)
