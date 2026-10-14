"""Aportes e metas das ferramentas do site (src/ferramentas/aportes.py)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.ferramentas import aportes


def test_valor_futuro_com_aportes_no_fim_do_mes():
    assert aportes.valor_futuro(0, 500, 0.008, 120) == pytest.approx(100108.73470495835)


def test_aporte_no_inicio_do_mes_rende_um_mes_a_mais():
    assert aportes.valor_futuro(0, 500, 0.008, 120, no_inicio=True) == pytest.approx(
        100909.60458259801
    )


def test_valor_inicial_tambem_rende():
    assert aportes.valor_futuro(10000, 500, 0.008, 120) == pytest.approx(
        126126.13225775168
    )


def test_taxa_zero_so_soma():
    assert aportes.valor_futuro(1000, 100, 0, 12) == pytest.approx(2200)
    assert aportes.aporte_para_meta(2200, 1000, 0, 12) == pytest.approx(100)


def test_aporte_para_chegar_na_meta():
    assert aportes.aporte_para_meta(100000, 0, 0.008, 120) == pytest.approx(
        499.4569169949115
    )


def test_meta_ja_alcancada_pede_aporte_zero():
    assert aportes.aporte_para_meta(1000, 5000, 0.01, 12) == 0


def test_meses_ate_a_meta():
    assert aportes.meses_ate_meta(100000, 0, 500, 0.008) == 120
    assert aportes.meses_ate_meta(1000, 5000, 0, 0.01) == 0


def test_meta_que_nunca_chega_devolve_none():
    # sem aporte e com taxa negativa, o dinheiro só encolhe
    assert aportes.meses_ate_meta(2000, 1000, 0, -0.01) is None
    # chega, mas depois de 100 anos (o limite da ferramenta)
    assert aportes.meses_ate_meta(1e9, 0, 1, 0) is None


def test_evolucao_separa_o_que_e_seu_do_que_e_juro():
    linhas = aportes.evolucao(1000, 100, 0.01, 2)
    assert len(linhas) == 3
    assert linhas[0] == aportes.Linha(mes=0, aportado=1000, juros=0, saldo=1000)
    assert linhas[1].aportado == 1100
    assert linhas[1].saldo == pytest.approx(
        1110
    )  # 1000 rende 10, o aporte entra no fim
    assert linhas[2].saldo == pytest.approx(1110 * 1.01 + 100)
    assert linhas[2].juros == pytest.approx(linhas[2].saldo - 1200)
    assert linhas[2].saldo == pytest.approx(aportes.valor_futuro(1000, 100, 0.01, 2))


@pytest.mark.parametrize(
    ("inicial", "aporte", "taxa", "meses", "mensagem"),
    [
        (-1, 100, 0.01, 12, "inicial"),
        (0, -1, 0.01, 12, "aporte"),
        (0, 100, -1.0, 12, "taxa"),
        (0, 100, 0.01, -1, "prazo"),
        (0, 100, 0.01, aportes.PRAZO_MAXIMO + 1, "prazo"),
    ],
)
def test_entradas_invalidas_dao_erro_claro(inicial, aporte, taxa, meses, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        aportes.valor_futuro(inicial, aporte, taxa, meses)


@given(
    inicial=st.floats(0, 1e7),
    aporte=st.floats(0, 1e5),
    taxa=st.floats(-0.02, 0.05),
    meses=st.integers(1, 600),
    no_inicio=st.booleans(),
)
def test_aporte_para_meta_desfaz_o_valor_futuro(
    inicial, aporte, taxa, meses, no_inicio
):
    meta = aportes.valor_futuro(inicial, aporte, taxa, meses, no_inicio)
    volta = aportes.aporte_para_meta(meta, inicial, taxa, meses, no_inicio)
    assert volta == pytest.approx(aporte, rel=1e-6, abs=1e-6)


# --- ferramentas v2: reajuste anual do aporte e a "virada" -------------------------------------
def test_aporte_com_reajuste_sobe_a_cada_12_meses():
    # 500 por mês no 1º ano e 550 no 2º (10%), a 0,5% ao mês: 6.167,8 viram 6.548,2 no 2º ano,
    # mais 550 × 12,3356 = 6.784,6
    assert aportes.valor_futuro(
        0, 500, 0.005, 24, reajuste_anual=0.10
    ) == pytest.approx(13332.755739184153, rel=1e-12)


def test_reajuste_zero_e_a_conta_de_sempre():
    assert aportes.valor_futuro(1000, 500, 0.008, 120, reajuste_anual=0.0) == (
        aportes.valor_futuro(1000, 500, 0.008, 120)
    )


def test_evolucao_com_reajuste_soma_o_que_saiu_do_bolso():
    linhas = aportes.evolucao(1000, 500, 0.005, 24, reajuste_anual=0.10)
    assert linhas[12].aportado == pytest.approx(1000 + 500 * 12)
    assert linhas[24].aportado == pytest.approx(1000 + 500 * 12 + 550 * 12)
    assert linhas[24].saldo == pytest.approx(
        aportes.valor_futuro(1000, 500, 0.005, 24, reajuste_anual=0.10)
    )


@given(
    st.floats(min_value=1, max_value=1e6),
    st.floats(min_value=0, max_value=1e5),
    st.floats(min_value=0, max_value=0.02),
    st.integers(min_value=1, max_value=480),
    st.floats(min_value=0, max_value=0.2),
    st.booleans(),
)
def test_aporte_para_meta_com_reajuste_volta_ao_aporte(
    aporte, inicial, taxa, meses, reajuste, no_inicio
):
    meta = aportes.valor_futuro(inicial, aporte, taxa, meses, no_inicio, reajuste)
    achado = aportes.aporte_para_meta(meta, inicial, taxa, meses, no_inicio, reajuste)
    assert achado == pytest.approx(aporte, rel=1e-6)


def test_meses_ate_meta_com_reajuste_chega_antes():
    sem = aportes.meses_ate_meta(100000, 0, 500, 0.005)
    com = aportes.meses_ate_meta(100000, 0, 500, 0.005, reajuste_anual=0.05)
    assert sem is not None and com is not None
    assert com < sem


def test_mes_da_virada_e_quando_os_juros_do_mes_passam_o_aporte():
    # a 0,5% ao mês, os juros do mês passam R$ 500 quando o saldo passa de R$ 100 mil: mês 140
    assert aportes.mes_da_virada(0, 500, 0.005, 1200) == 140


def test_sem_juros_ou_sem_aporte_nao_ha_virada():
    assert aportes.mes_da_virada(0, 500, 0.0, 600) is None
    assert aportes.mes_da_virada(0, 500, 0.005, 100) is None  # o prazo acaba antes
