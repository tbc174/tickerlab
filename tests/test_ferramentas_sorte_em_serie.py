"""Sorte em série (src/ferramentas/sorte_em_serie.py) e o gerador pseudoaleatório (aleatorio.py)."""

import math
import statistics

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.ferramentas import sorte_em_serie as sorte
from src.ferramentas.aleatorio import Gerador


def test_mulberry32_da_os_numeros_de_referencia():
    # os 3 primeiros da semente 42 no mulberry32 original em JavaScript (conferidos no Node)
    g = Gerador(42)
    assert [g.proximo() for _ in range(3)] == pytest.approx(
        [0.6011037519201636, 0.44829055899754167, 0.8524657934904099], abs=1e-15
    )


def test_mesma_semente_mesmos_numeros_e_sempre_entre_0_e_1():
    a, b = Gerador(7), Gerador(7)
    numeros = [a.proximo() for _ in range(1000)]
    assert numeros == [b.proximo() for _ in range(1000)]
    assert all(0 <= n < 1 for n in numeros)
    assert 0.45 < statistics.mean(numeros) < 0.55


def test_simular_cem_estrategias_de_um_ano():
    r = sorte.simular(100, 250, 42)
    assert r.estrategias == 100
    assert (
        len(r.curva_da_melhor) == len(r.curva_da_mediana) == len(r.curva_da_pior) == 251
    )
    assert r.curva_da_melhor[0] == r.curva_da_pior[0] == 1
    assert r.retorno_da_pior <= r.retorno_da_mediana <= r.retorno_da_melhor
    assert r.retorno_da_melhor == pytest.approx(r.curva_da_melhor[-1] - 1)
    # a melhor parece genial por puro acaso
    assert r.sharpe_da_melhor > 1.5
    assert 0 < r.com_sharpe_acima_de_1 < 50
    assert 0 < r.lucraram < 100


def test_mesma_semente_mesmo_resultado_e_outra_semente_outro():
    assert sorte.simular(50, 100, 1) == sorte.simular(50, 100, 1)
    assert sorte.simular(50, 100, 1) != sorte.simular(50, 100, 2)


def test_sharpe_anualizado():
    # retornos +1% e -1% alternados: média 0, Sharpe 0
    assert sorte.sharpe([0.01, -0.01, 0.01, -0.01]) == pytest.approx(0)
    retornos = [0.01, 0.01, -0.01, 0.01]
    esperado = (
        statistics.mean(retornos) / statistics.stdev(retornos) * sorte.DIAS_POR_ANO**0.5
    )
    assert sorte.sharpe(retornos) == pytest.approx(esperado)


@pytest.mark.parametrize(
    ("estrategias", "dias", "mensagem"),
    [
        (1, 250, "estratégias"),
        (sorte.ESTRATEGIAS_MAXIMAS + 1, 250, "estratégias"),
        (100, 1, "dias"),
        (100, sorte.DIAS_MAXIMOS + 1, "dias"),
    ],
)
def test_limites(estrategias, dias, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        sorte.simular(estrategias, dias, 42)


@settings(max_examples=25, deadline=None)  # cada simulação leva ~0,25 s
@given(semente=st.integers(0, 2**32 - 1))
def test_em_media_ninguem_tem_vantagem(semente):
    """Moeda honesta: a média dos retornos diários de todas as estratégias fica perto de zero."""
    r = sorte.simular(200, 250, semente)
    assert abs(r.media_dos_retornos_diarios) < 0.001


# --- ferramentas v2: a distribuição dos retornos e a correção pelas tentativas -----------------
@pytest.mark.parametrize("x", [-3.0, -1.0, -0.2, 0.0, 0.3, 1.0, 1.645, 2.5, 4.0, 6.0])
def test_erfc_aproximada_fica_perto_da_do_python(x):
    assert sorte.erfc(x) == pytest.approx(math.erfc(x), rel=2e-7, abs=1e-15)


def test_p_valor_de_retornos_sem_tendencia_e_meio():
    assert sorte.p_valor([0.01, -0.01] * 50) == pytest.approx(0.5, abs=1e-6)


def test_p_valor_cai_quando_a_media_sobe():
    assert sorte.p_valor([0.02, -0.01] * 50) < sorte.p_valor([0.011, -0.01] * 50)


def test_simular_guarda_o_retorno_final_de_cada_estrategia():
    r = sorte.simular(100, 250, 42)
    assert len(r.retornos_finais) == 100
    assert max(r.retornos_finais) == r.retorno_da_melhor
    assert min(r.retornos_finais) == r.retorno_da_pior


def test_sem_correcao_algumas_passam_por_sorte_e_com_correcao_nenhuma():
    # todas são moeda: a 5%, umas 5 em 100 "passam" por acaso; dividindo o nível pelas 100
    # tentativas, nenhuma
    r = sorte.simular(100, 250, 42)
    assert 1 <= r.passam_sem_correcao <= 15
    assert r.passam_com_correcao == 0


@given(
    st.integers(min_value=2, max_value=200),
    st.integers(min_value=20, max_value=300),
    st.integers(min_value=0, max_value=2**31),
)
@settings(max_examples=30, deadline=None)
def test_com_correcao_nunca_passam_mais_que_sem(estrategias, dias, semente):
    r = sorte.simular(estrategias, dias, semente)
    assert r.passam_com_correcao <= r.passam_sem_correcao
