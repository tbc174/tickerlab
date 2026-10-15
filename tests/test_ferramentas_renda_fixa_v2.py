"""Renda fixa v2 (src/ferramentas/renda_fixa.py): IOF nos primeiros 30 dias, custódia do Tesouro
Direto, Tesouro Prefixado e IPCA+ levados até o vencimento, CDI pelo caminho do Focus e o ponto de
empate entre LCI/LCA e CDB."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.ferramentas import renda_fixa

CDI = [0.1365]
POUPANCA = 0.006704


def _opcao(opcoes, nome):
    (o,) = [o for o in opcoes if o.nome == nome]
    return o


def test_iof_nos_primeiros_30_dias_vem_antes_do_ir():
    # 10 dias: o IOF leva 66% do rendimento e o IR (22,5%) incide sobre o que sobra
    cdb = _opcao(renda_fixa.comparar(10_000, 10, CDI, 1.0, 0.9, POUPANCA), "CDB")
    assert cdb.bruto == pytest.approx(10035.117233274637)
    assert cdb.iof == pytest.approx(23.17737396126064)
    assert cdb.imposto == pytest.approx(2.6864683455097556)
    assert cdb.liquido == pytest.approx(10009.253390967868)


def test_depois_de_30_dias_nao_ha_iof_e_lci_lca_nunca_paga_iof_aqui():
    opcoes = renda_fixa.comparar(10_000, 30, CDI, 1.0, 0.9, POUPANCA)
    assert _opcao(opcoes, "CDB").iof == 0
    assert (
        _opcao(
            renda_fixa.comparar(10_000, 10, CDI, 1.0, 0.9, POUPANCA), "LCI ou LCA"
        ).iof
        == 0
    )


def test_tesouro_selic_paga_custodia_so_acima_de_10_mil():
    pequeno = _opcao(
        renda_fixa.comparar(5_000, 365, CDI, 1.0, 0.9, POUPANCA), "Tesouro Selic"
    )
    assert pequeno.custodia == 0
    grande = _opcao(
        renda_fixa.comparar(50_000, 365, CDI, 1.0, 0.9, POUPANCA), "Tesouro Selic"
    )
    # 0,2% ao ano sobre o saldo médio que passa de R$ 10 mil
    assert grande.custodia == pytest.approx(86.825)
    assert grande.imposto == pytest.approx(1194.375)
    assert grande.liquido == pytest.approx(55543.8)


def test_cdb_nao_tem_custodia():
    assert (
        _opcao(
            renda_fixa.comparar(50_000, 365, CDI, 1.0, 0.9, POUPANCA), "CDB"
        ).custodia
        == 0
    )


def test_mesmo_cdi_todo_ano_da_o_mesmo_que_a_conta_de_antes():
    um_ano = _opcao(renda_fixa.comparar(1000, 800, CDI, 1.0, 0.9, POUPANCA), "CDB")
    tres_anos = _opcao(
        renda_fixa.comparar(1000, 800, CDI * 3, 1.0, 0.9, POUPANCA), "CDB"
    )
    assert tres_anos.bruto == pytest.approx(um_ano.bruto, rel=1e-12)
    assert um_ano.bruto == pytest.approx(1000 * (1 + CDI[0]) ** (800 / 365))


def test_cdi_que_cai_no_segundo_ano_rende_menos():
    parado = _opcao(renda_fixa.comparar(1000, 730, [0.1365], 1.0, 0.9, POUPANCA), "CDB")
    caindo = _opcao(
        renda_fixa.comparar(1000, 730, [0.1365, 0.11], 1.0, 0.9, POUPANCA), "CDB"
    )
    assert caindo.bruto == pytest.approx(1000 * 1.1365 * 1.11)
    assert caindo.bruto < parado.bruto


def test_cdi_pelo_focus_segue_a_selic_esperada_menos_a_diferenca_de_hoje():
    caminho = renda_fixa.cdi_pelo_focus(
        cdi_hoje=0.1365,
        selic_hoje=0.1375,
        selic_esperada={"2026": 0.1325, "2027": 0.12},
        ano_inicial=2026,
        anos=3,
    )
    assert caminho == pytest.approx([0.1315, 0.119, 0.119])  # depois do Focus, o último


def test_tesouro_prefixado_ate_o_vencimento_com_custodia_e_ir():
    o = renda_fixa.tesouro_prefixado(10_000, 730, 0.125)
    assert o.nome == "Tesouro Prefixado"
    assert o.bruto == pytest.approx(12656.25)
    assert o.custodia == pytest.approx(45.3125)
    assert o.liquido == pytest.approx(12212.5)


def test_tesouro_ipca_mais_soma_o_juro_real_e_a_inflacao_esperada():
    o = renda_fixa.tesouro_ipca(10_000, 730, 0.0669, [0.045])
    assert o.nome == "Tesouro IPCA+"
    assert o.bruto == pytest.approx(12430.254230102497)
    assert o.liquido == pytest.approx(12020.855587126916)


def test_ponto_de_empate_faz_o_cdb_render_o_mesmo_que_a_lci():
    percentual = renda_fixa.ponto_de_empate(10_000, 730, CDI, 0.9)
    opcoes = renda_fixa.comparar(10_000, 730, CDI, percentual, 0.9, POUPANCA)
    assert _opcao(opcoes, "CDB").liquido == pytest.approx(
        _opcao(opcoes, "LCI ou LCA").liquido, rel=1e-9
    )
    # não é 90% / 0,85 = 105,9% (regra de bolso de juro simples): com juro composto em 2 anos a
    # 13,65%, a LCI rende 25,75% e o CDB precisa de 30,3% bruto, uns 103,9% do CDI
    assert percentual == pytest.approx(1.0393826, rel=1e-6)


@given(
    st.floats(0.5, 1.2),
    st.integers(31, 3650),
    st.floats(0.02, 0.2),
)
@settings(max_examples=40, deadline=None)
def test_empate_sempre_acima_da_lci_porque_o_cdb_paga_ir(lci, dias, cdi):
    assert renda_fixa.ponto_de_empate(10_000, dias, [cdi], lci) > lci


def test_entradas_invalidas_do_tesouro_e_do_caminho():
    with pytest.raises(ValueError, match="CDI"):
        renda_fixa.comparar(1000, 365, [], 1.0, 0.9, POUPANCA)
    with pytest.raises(ValueError, match="prazo"):
        renda_fixa.tesouro_prefixado(1000, 0, 0.12)
    with pytest.raises(ValueError, match="inflação"):
        renda_fixa.tesouro_ipca(1000, 365, 0.06, [])
