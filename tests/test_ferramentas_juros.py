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


def test_taxa_por_mes_dos_juros_simples_e_a_proporcional():
    # 10% ao ano por 10 anos em juros simples dão R$ 20.000 (a equivalente dava R$ 19.568,97)
    taxa = juros.taxa_por_mes(0.10, "ano", composto=False)
    assert taxa == pytest.approx(0.10 / 12)
    assert juros.montante(10000, taxa, 120, composto=False) == pytest.approx(20000)
    assert juros.taxa_por_mes(0.01, "mes", composto=False) == 0.01
    with pytest.raises(ValueError):
        juros.taxa_por_mes(-1, "ano", composto=False)


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


# --- ferramentas v2: em reais de hoje e depois do IR --------------------------------------------
def test_em_reais_de_hoje_desconta_a_inflacao_do_prazo():
    # R$ 25.937,42 daqui a 10 anos, com inflação de 4% ao ano, compram o que R$ 17.522,39 compram hoje
    assert juros.em_reais_de_hoje(25937.424601, 0.04, 120) == pytest.approx(
        17522.394692056, rel=1e-9
    )


def test_em_reais_de_hoje_sem_inflacao_ou_sem_prazo_nao_muda():
    assert juros.em_reais_de_hoje(5000, 0.0, 120) == 5000
    assert juros.em_reais_de_hoje(5000, 0.1, 0) == 5000


def test_em_reais_de_hoje_recusa_inflacao_de_menos_100_por_cento():
    with pytest.raises(ValueError, match="inflação"):
        juros.em_reais_de_hoje(5000, -1.0, 12)


def test_liquido_de_ir_em_2_anos_tira_15_por_cento_do_ganho():
    bruto = juros.montante(10000, 0.01, 24)
    assert juros.liquido_de_ir(10000, bruto, 24) == pytest.approx(
        12292.744512521, rel=1e-9
    )


def test_liquido_de_ir_em_6_meses_tira_20_por_cento():
    # 6 meses são ~183 dias corridos: já passou dos 180 dias da 1ª faixa (22,5%)
    bruto = juros.montante(10000, 0.01, 6)
    assert juros.liquido_de_ir(10000, bruto, 6) == pytest.approx(
        10492.161204808, rel=1e-9
    )


def test_liquido_de_ir_sem_ganho_nao_cobra_e_sem_prazo_devolve_o_valor():
    assert juros.liquido_de_ir(10000, 9000, 12) == 9000
    assert juros.liquido_de_ir(10000, 10000, 0) == 10000


@given(
    st.floats(min_value=0, max_value=1e7),
    st.floats(min_value=0, max_value=0.05),
    st.integers(min_value=1, max_value=600),
)
def test_liquido_de_ir_fica_entre_o_capital_e_o_bruto(capital, taxa, meses):
    bruto = juros.montante(capital, taxa, meses)
    liquido = juros.liquido_de_ir(capital, bruto, meses)
    assert capital - 1e-6 <= liquido <= bruto + 1e-6
