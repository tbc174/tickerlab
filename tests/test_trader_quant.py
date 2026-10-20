"""VaR e CVaR históricos e Benjamini-Hochberg: exemplos à mão e propriedades."""

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from trader import quant

RETORNOS = st.lists(
    st.floats(min_value=-0.5, max_value=0.5, allow_nan=False), min_size=5, max_size=200
)
NIVEIS = st.floats(min_value=0.5, max_value=0.99)
P_VALORES = st.lists(st.floats(min_value=0.0, max_value=1.0), min_size=1, max_size=40)


def test_var_e_cvar_calculados_a_mao():
    r = [-0.05, -0.03, -0.01, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06]
    # nível 80%: os 2 piores dias (10 · 20%) são -5% e -3%
    assert quant.var_historico(r, 0.8) == pytest.approx(0.03)
    assert quant.cvar_historico(r, 0.8) == pytest.approx(0.04)
    # nível 95%: 10 · 5% = 0,5 → o pior dia
    assert quant.var_historico(r, 0.95) == pytest.approx(0.05)
    assert quant.cvar_historico(r, 0.95) == pytest.approx(0.05)


def test_var_ignora_vazios_e_recusa_sem_dado():
    assert quant.var_historico([np.nan, -0.02, 0.01], 0.5) == pytest.approx(0.02)
    with pytest.raises(ValueError, match="Não há retornos"):
        quant.cvar_historico([np.nan, np.nan])
    with pytest.raises(ValueError, match="nível"):
        quant.var_historico([0.01, -0.01], 1.0)


def test_var_negativo_quando_ate_o_pior_dia_ganhou():
    assert quant.var_historico([0.01, 0.02, 0.03], 0.9) == pytest.approx(-0.01)


@settings(max_examples=200, deadline=None)
@given(r=RETORNOS, nivel=NIVEIS)
def test_cvar_nunca_menor_que_o_var(r, nivel):
    assert quant.cvar_historico(r, nivel) >= quant.var_historico(r, nivel) - 1e-12


@settings(max_examples=200, deadline=None)
@given(r=RETORNOS, nivel=NIVEIS, escala=st.floats(min_value=0.1, max_value=10))
def test_var_e_cvar_crescem_com_a_escala(r, nivel, escala):
    """Dobrar a posição dobra a perda da cauda (homogeneidade positiva)."""
    escalado = [x * escala for x in r]
    assert quant.var_historico(escalado, nivel) == pytest.approx(
        escala * quant.var_historico(r, nivel), abs=1e-12
    )
    assert quant.cvar_historico(escalado, nivel) == pytest.approx(
        escala * quant.cvar_historico(r, nivel), abs=1e-12
    )


@settings(max_examples=200, deadline=None)
@given(r=RETORNOS, nivel=NIVEIS, ganho=st.floats(min_value=-0.1, max_value=0.1))
def test_somar_um_ganho_fixo_reduz_a_perda_na_mesma_medida(r, nivel, ganho):
    deslocado = [x + ganho for x in r]
    assert quant.cvar_historico(deslocado, nivel) == pytest.approx(
        quant.cvar_historico(r, nivel) - ganho, abs=1e-12
    )


@settings(max_examples=200, deadline=None)
@given(r=RETORNOS, a=NIVEIS, b=NIVEIS)
def test_nivel_maior_olha_cauda_pior(r, a, b):
    baixo, alto = sorted((a, b))
    assert quant.cvar_historico(r, alto) >= quant.cvar_historico(r, baixo) - 1e-12


def test_benjamini_hochberg_calculado_a_mao():
    """Exemplo clássico de 10 hipóteses com q = 5%: limites k · 0,005; só as duas primeiras passam."""
    p = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216]
    assert quant.benjamini_hochberg(p, 0.05).tolist() == [True, True] + [False] * 8
    ajustados = quant.p_ajustados_bh(p)
    assert ajustados[0] == pytest.approx(0.01)  # 0,001 · 10 / 1
    assert ajustados[1] == pytest.approx(0.04)  # 0,008 · 10 / 2
    # 0,039 · 10 / 3 = 0,13, mas 0,042 · 10 / 5 = 0,084 é menor e vem depois: o ajustado não cai
    assert ajustados[2] == pytest.approx(0.084)


def test_benjamini_hochberg_aprova_quem_esta_abaixo_de_uma_maior_aprovada():
    """O BH olha de cima para baixo: 0,04 (4ª de 4) passa no limite 0,05 e leva as menores junto."""
    p = [0.04, 0.03, 0.02, 0.01]
    assert quant.benjamini_hochberg(p, 0.05).all()
    assert quant.p_ajustados_bh(p).tolist() == pytest.approx([0.04] * 4)


def test_p_valores_invalidos_recusam():
    for errado in ([], [0.1, np.nan], [1.2], [-0.1]):
        with pytest.raises(ValueError):
            quant.p_ajustados_bh(errado)
    with pytest.raises(ValueError, match="falsos achados"):
        quant.benjamini_hochberg([0.01], 0.0)


@settings(max_examples=200, deadline=None)
@given(p=P_VALORES, fdr=st.floats(min_value=0.001, max_value=0.5))
def test_bh_aprova_pelo_menos_o_que_bonferroni_aprova(p, fdr):
    bh = quant.benjamini_hochberg(p, fdr)
    bonferroni = np.asarray(p) <= fdr / len(p)
    assert (bh | ~bonferroni).all()


@settings(max_examples=200, deadline=None)
@given(p=P_VALORES, fdr=st.floats(min_value=0.001, max_value=0.5))
def test_aprovadas_sao_as_menores(p, fdr):
    """Se uma hipótese passa, toda hipótese com p-valor menor também passa."""
    bh = quant.benjamini_hochberg(p, fdr)
    p = np.asarray(p)
    assume(bh.any())
    assert (bh[p <= p[bh].max()]).all()


@settings(max_examples=200, deadline=None)
@given(p=P_VALORES)
def test_ajustados_entre_o_p_original_e_1(p):
    ajustados = quant.p_ajustados_bh(p)
    assert (ajustados >= np.asarray(p) - 1e-12).all()
    assert (ajustados <= 1).all()


@settings(max_examples=200, deadline=None)
@given(p=P_VALORES, a=st.floats(0.001, 0.5), b=st.floats(0.001, 0.5))
def test_mais_tolerancia_aprova_mais(p, a, b):
    baixo, alto = sorted((a, b))
    assert (
        quant.benjamini_hochberg(p, alto) | ~quant.benjamini_hochberg(p, baixo)
    ).all()
