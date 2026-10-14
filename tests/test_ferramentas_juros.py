"""Juros simples e compostos das ferramentas do site (src/ferramentas/juros.py)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.ferramentas import juros


def test_juros_compostos_de_mil_a_1_por_cento_em_12_meses():
    assert juros.montante(1000, 0.01, 12) == pytest.approx(
        1126.8250301319697, rel=1e-12
    )


def test_juros_simples_de_mil_a_1_por_cento_em_12_meses():
    assert juros.montante(1000, 0.01, 12, composto=False) == pytest.approx(1120.0)


def test_prazo_zero_devolve_o_capital():
    assert juros.montante(1000, 0.05, 0) == 1000
    assert juros.montante(1000, 0.05, 0, composto=False) == 1000


def test_taxa_negativa_encolhe_o_capital():
    assert juros.montante(1000, -0.01, 2) == pytest.approx(980.1)


def test_taxa_anual_e_mensal_dao_o_mesmo():
    anual = juros.taxa_equivalente(0.01, de_meses=1, para_meses=12)
    assert anual == pytest.approx(0.12682503013196977)
    assert juros.taxa_equivalente(anual, de_meses=12, para_meses=1) == pytest.approx(
        0.01
    )


def test_taxa_por_mes_aceita_ao_mes_e_ao_ano():
    assert juros.taxa_por_mes(0.01, "mes") == 0.01
    assert juros.taxa_por_mes(0.12682503013196977, "ano") == pytest.approx(0.01)
    with pytest.raises(ValueError, match="unidade"):
        juros.taxa_por_mes(0.01, "semana")


def test_evolucao_mes_a_mes():
    linhas = juros.evolucao(1000, 0.01, 12)
    assert len(linhas) == 13  # o mês 0 (só o capital) e os 12 meses
    assert linhas[0] == juros.Linha(
        periodo=0, juros_no_periodo=0, juros_acumulados=0, montante=1000
    )
    assert linhas[1].juros_no_periodo == pytest.approx(10)
    assert linhas[2].juros_no_periodo == pytest.approx(10.1)  # juro sobre juro
    assert linhas[-1].montante == pytest.approx(juros.montante(1000, 0.01, 12))
    assert linhas[-1].juros_acumulados == pytest.approx(126.8250301319697)


def test_evolucao_simples_tem_juro_igual_todo_mes():
    linhas = juros.evolucao(1000, 0.01, 3, composto=False)
    assert [linha.juros_no_periodo for linha in linhas[1:]] == pytest.approx(
        [10, 10, 10]
    )


@pytest.mark.parametrize(
    ("capital", "taxa", "periodos", "mensagem"),
    [
        (-1, 0.01, 12, "capital"),
        (1000, -1.0, 12, "taxa"),
        (1000, -1.5, 12, "taxa"),
        (1000, 0.01, -1, "prazo"),
        (1000, 0.01, juros.PRAZO_MAXIMO + 1, "prazo"),
    ],
)
def test_entradas_invalidas_dao_erro_claro(capital, taxa, periodos, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        juros.montante(capital, taxa, periodos)


@given(
    capital=st.floats(0, 1e9),
    taxa=st.floats(0, 0.2),
    periodos=st.integers(1, 600),
)
def test_composto_nunca_rende_menos_que_simples_com_taxa_positiva(
    capital, taxa, periodos
):
    composto = juros.montante(capital, taxa, periodos)
    simples = juros.montante(capital, taxa, periodos, composto=False)
    assert composto >= simples * (1 - 1e-12)
