"""O simulador de financiamento SAC × Price do site (src/ferramentas/financiamento.py)."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.ferramentas import financiamento as fin

VALOR, TAXA, MESES = 300_000, 0.01, 360


def test_price_tem_parcela_fixa():
    linhas = fin.tabela("price", VALOR, TAXA, MESES)
    assert len(linhas) == MESES
    assert linhas[0].parcela == pytest.approx(3085.837790776513)
    assert linhas[-1].parcela == pytest.approx(3085.837790776513)
    assert sum(lin.juros for lin in linhas) == pytest.approx(810_901.6046795447)
    assert linhas[-1].saldo == pytest.approx(0, abs=1e-6)


def test_sac_tem_amortizacao_fixa_e_parcela_que_cai():
    linhas = fin.tabela("sac", VALOR, TAXA, MESES)
    assert linhas[0].amortizacao == pytest.approx(VALOR / MESES)
    assert linhas[0].parcela == pytest.approx(3833.3333333333335)
    assert linhas[-1].parcela == pytest.approx(841.6666666666667)
    assert sum(lin.juros for lin in linhas) == pytest.approx(541_500)


def test_juro_zero_divide_o_valor_pelas_parcelas():
    for sistema in ("sac", "price"):
        linhas = fin.tabela(sistema, 1200, 0.0, 12)
        assert all(lin.parcela == pytest.approx(100) for lin in linhas)


def test_amortizacao_extra_reduzindo_o_prazo_termina_antes():
    sem = fin.tabela("price", VALOR, TAXA, MESES)
    com = fin.tabela("price", VALOR, TAXA, MESES, extra_mes=12, extra_valor=50_000)
    assert len(com) < len(sem)
    assert com[11].extra == pytest.approx(50_000)
    assert com[12].parcela == pytest.approx(sem[12].parcela)  # a parcela fica


def test_amortizacao_extra_reduzindo_a_parcela_mantem_o_prazo():
    sem = fin.tabela("sac", VALOR, TAXA, MESES)
    com = fin.tabela(
        "sac",
        VALOR,
        TAXA,
        MESES,
        extra_mes=12,
        extra_valor=50_000,
        extra_modo="parcela",
    )
    assert len(com) == MESES
    assert com[12].parcela < sem[12].parcela


def test_extra_maior_que_o_saldo_quita_tudo():
    linhas = fin.tabela("price", 10_000, TAXA, 24, extra_mes=3, extra_valor=1_000_000)
    assert len(linhas) == 3
    assert linhas[-1].saldo == 0


@pytest.mark.parametrize(
    ("args", "mensagem"),
    [
        (("bala", 1000, 0.01, 12), "sistema"),
        (("sac", 0, 0.01, 12), "valor"),
        (("sac", 1000, -0.01, 12), "taxa"),
        (("sac", 1000, 0.01, 0), "prazo"),
        (("sac", 1000, 0.01, 601), "prazo"),
    ],
)
def test_entradas_invalidas(args, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        fin.tabela(*args)


@given(
    st.sampled_from(["sac", "price"]),
    st.floats(1_000, 2_000_000),
    st.floats(0, 0.03),
    st.integers(1, 420),
    st.integers(0, 420),
    st.floats(0, 500_000),
    st.sampled_from(["prazo", "parcela"]),
)
@settings(max_examples=60, deadline=None)
def test_as_amortizacoes_pagam_exatamente_o_valor(
    sistema, valor, taxa, meses, mes, extra, modo
):
    linhas = fin.tabela(sistema, valor, taxa, meses, min(mes, meses), extra, modo)
    pago = sum(lin.amortizacao + lin.extra for lin in linhas)
    assert pago == pytest.approx(valor, rel=1e-9)
    assert len(linhas) <= meses
