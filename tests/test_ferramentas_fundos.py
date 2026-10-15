"""Fundo × renda fixa (src/ferramentas/fundos.py): a taxa de administração, a de performance e o
come-cotas (Lei 14.754/2023, art. 17), mês a mês, contra o mesmo CDI."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.ferramentas import fundos, renda_fixa

UM_POR_CENTO_AO_MES = 1.01**12 - 1  # o CDI que rende exatamente 1% ao mês


def _fundo(**kwargs):
    base = {
        "valor": 1000.0,
        "meses": 5,
        "cdi_ao_ano": UM_POR_CENTO_AO_MES,
        "percentual_do_cdi": 1.0,
        "taxa_de_administracao": 0.0,
        "taxa_de_performance": 0.0,
        "longo_prazo": True,
        "mes_inicial": 1,
    }
    return fundos.simular(**{**base, **kwargs})


def test_come_cotas_em_maio_e_o_complemento_no_resgate():
    # jan a mai: 5 meses a 1% = +51,01; em maio, 15% de come-cotas; no resgate (~152 dias, 22,5%),
    # só a diferença; no fim, o mesmo que pagar 22,5% de uma vez (sem rendimento depois do come-cotas)
    r = _fundo()
    ganho = 1000 * 1.01**5 - 1000
    assert r.come_cotas == pytest.approx(0.15 * ganho)
    assert r.ir_no_resgate == pytest.approx((0.225 - 0.15) * ganho)
    assert r.liquido == pytest.approx(1000 + ganho * (1 - 0.225))
    assert r.vezes_do_come_cotas == 1


def test_come_cotas_em_maio_e_novembro_de_cada_ano():
    assert (
        _fundo(meses=25).vezes_do_come_cotas == 4
    )  # mai e nov de dois anos (jan a jan)


def test_curto_prazo_paga_20_por_cento_no_come_cotas():
    r = _fundo(longo_prazo=False)
    ganho = 1000 * 1.01**5 - 1000
    assert r.come_cotas == pytest.approx(0.20 * ganho)


def test_taxa_de_administracao_come_o_patrimonio():
    sem = _fundo(meses=24)
    com = _fundo(meses=24, taxa_de_administracao=0.02)
    assert com.taxa_de_administracao > 0
    assert com.liquido < sem.liquido


def test_performance_so_quando_bate_o_cdi():
    assert (
        _fundo(meses=24, taxa_de_performance=0.2).taxa_de_performance == 0
    )  # rende igual ao CDI
    acima = _fundo(meses=24, percentual_do_cdi=1.3, taxa_de_performance=0.2)
    assert acima.taxa_de_performance > 0


def test_entradas_invalidas():
    with pytest.raises(ValueError, match="prazo"):
        _fundo(meses=0)
    with pytest.raises(ValueError, match="mês"):
        _fundo(mes_inicial=13)
    with pytest.raises(ValueError, match="taxa"):
        _fundo(taxa_de_administracao=-0.01)


@given(
    st.integers(1, 120),
    st.floats(0.5, 1.5),
    st.floats(0, 0.03),
    st.floats(0, 0.3),
    st.booleans(),
    st.integers(1, 12),
)
@settings(max_examples=60, deadline=None)
def test_o_liquido_e_o_patrimonio_menos_o_que_falta_de_ir(
    meses, pct, adm, perf, longo, mes
):
    r = _fundo(
        meses=meses,
        percentual_do_cdi=pct,
        taxa_de_administracao=adm,
        taxa_de_performance=perf,
        longo_prazo=longo,
        mes_inicial=mes,
    )
    assert r.liquido == pytest.approx(r.patrimonio_final - r.ir_no_resgate)
    assert r.ir_no_resgate >= 0
    assert r.come_cotas >= 0


def test_sem_ganho_nao_tem_come_cotas_nem_ir():
    # CDI zero e 2% de administração: o fundo só perde
    r = _fundo(meses=24, cdi_ao_ano=0.0, taxa_de_administracao=0.02)
    assert r.come_cotas == 0
    assert r.ir_no_resgate == 0
    assert r.liquido == pytest.approx(1000 * 0.98**2)


def test_sem_taxas_o_fundo_fica_um_pouco_abaixo_do_cdb():
    # o mesmo 100% do CDI: o come-cotas tira dinheiro que deixaria de render
    meses = 36
    r = _fundo(meses=meses, cdi_ao_ano=0.12)
    cdb = renda_fixa.comparar(
        1000.0, round(meses * fundos.DIAS_POR_MES), [0.12], 1.0, 1.0, 0.005
    )[0]
    assert r.liquido < cdb.liquido
    assert r.liquido > cdb.liquido * 0.99


def test_prazo_ate_10_anos_como_o_cdb_da_comparacao():
    assert fundos.PRAZO_MAXIMO * fundos.DIAS_POR_MES <= renda_fixa.DIAS_MAXIMOS
    with pytest.raises(ValueError, match="prazo"):
        _fundo(meses=fundos.PRAZO_MAXIMO + 1)
