"""Testes de src/acaso.py."""

import numpy as np
import pandas as pd
import pytest

from src import acaso
from src.backtest import executar_backtest


def _precos(n=600, semente=5, deriva=0.0004, vol=0.01):
    rng = np.random.default_rng(semente)
    return pd.Series(
        100 * np.cumprod(1 + rng.normal(deriva, vol, n)),
        index=pd.bdate_range("2021-01-04", periods=n),
    )


# --- Monte Carlo --------------------------------------------------------------------------


def test_monte_carlo_e_reproduzivel_com_a_mesma_semente():
    ops = pd.Series([0.05, -0.02, 0.03, -0.01, 0.04, 0.02])
    a = acaso.simular_monte_carlo(ops, 500, semente=1)
    b = acaso.simular_monte_carlo(ops, 500, semente=1)
    assert np.array_equal(a.retornos_finais, b.retornos_finais)


def test_monte_carlo_operacoes_iguais_nao_tem_dispersao():
    r = acaso.simular_monte_carlo(pd.Series([0.02] * 6), 200)
    assert np.allclose(r.retornos_finais, 1.02**6 - 1)
    assert np.allclose(r.quedas_maximas, 0)
    assert r.probabilidade_de_prejuizo == 0


def test_monte_carlo_percentis_em_ordem_e_curva_observada():
    ops = pd.Series([0.05, -0.02, 0.03, -0.01, 0.04, 0.02, -0.03])
    r = acaso.simular_monte_carlo(ops, 1000)
    p = r.percentis_da_curva
    assert len(p) == len(ops) + 1
    assert (p["p5"] <= p["p25"]).all() and (p["p25"] <= p["p50"]).all()
    assert (p["p50"] <= p["p75"]).all() and (p["p75"] <= p["p95"]).all()
    assert (p.iloc[0] == 1).all()
    assert r.curva_observada[-1] == pytest.approx((1 + ops).prod())
    assert (r.quedas_maximas <= 0).all()


def test_monte_carlo_so_perdas_da_prejuizo_certo():
    r = acaso.simular_monte_carlo(pd.Series([-0.02] * 6), 200)
    assert r.probabilidade_de_prejuizo == 1


def test_monte_carlo_recusa_poucas_operacoes_e_poucas_simulacoes():
    with pytest.raises(ValueError, match="operações"):
        acaso.simular_monte_carlo(pd.Series([0.1, 0.2]))
    with pytest.raises(ValueError, match="simulações"):
        acaso.simular_monte_carlo(pd.Series([0.01] * 6), 10)


# --- Teste contra o acaso -----------------------------------------------------------------


def test_a_conta_rapida_bate_com_o_motor():
    fechamento = _precos()
    rng = np.random.default_rng(2)
    desejada = pd.Series(
        rng.integers(0, 2, len(fechamento)).astype(float), index=fechamento.index
    )
    esperado = executar_backtest(fechamento, desejada, 0.001).retorno.to_numpy()
    rapido = acaso._retorno_da_posicao(
        fechamento.pct_change().fillna(0.0).to_numpy(), desejada.to_numpy(), 0.001
    )
    assert np.allclose(rapido, esperado)


def test_sinal_com_bola_de_cristal_nao_se_confunde_com_o_acaso():
    fechamento = _precos()
    futuro = fechamento.pct_change().shift(-1).fillna(0.0)
    desejada = (futuro > 0).astype(float)  # olha o futuro de propósito
    r = acaso.testar_contra_o_acaso(fechamento, desejada, 0.0, sorteios=300)
    assert r.p_valor < 0.01
    assert r.sharpe_real > r.sharpes_ao_acaso.max()


def test_posicao_sem_relacao_com_o_preco_tem_p_valor_alto():
    fechamento = _precos(semente=11)
    rng = np.random.default_rng(99)
    desejada = pd.Series(
        rng.integers(0, 2, len(fechamento)).astype(float), index=fechamento.index
    )
    r = acaso.testar_contra_o_acaso(fechamento, desejada, 0.0005, sorteios=300)
    assert r.p_valor > 0.05


def test_comprar_e_segurar_empata_com_todos_os_sorteios():
    fechamento = _precos()
    desejada = pd.Series(1.0, index=fechamento.index)
    r = acaso.testar_contra_o_acaso(fechamento, desejada, 0.0005, sorteios=200)
    assert r.p_valor == 1.0


def test_acaso_mantem_a_exposicao_e_o_numero_de_operacoes():
    desejada = np.array([0, 1, 1, 0, 0, 1, 0, 0, 0, 1], dtype=float)
    girada = np.roll(desejada, 3)
    assert girada.sum() == desejada.sum()
    assert np.abs(np.diff(girada)).sum() == pytest.approx(
        np.abs(np.diff(desejada)).sum(), abs=2
    )


def test_acaso_sem_operacoes_e_com_poucos_dados_da_erro():
    fechamento = _precos()
    with pytest.raises(ValueError, match="não operou"):
        acaso.testar_contra_o_acaso(
            fechamento, pd.Series(0.0, index=fechamento.index), 0.0, sorteios=100
        )
    with pytest.raises(ValueError, match="Poucos dados"):
        acaso.testar_contra_o_acaso(
            fechamento.iloc[:30], pd.Series(1.0, index=fechamento.index[:30]), 0.0
        )


def test_acaso_e_reproduzivel():
    fechamento = _precos()
    desejada = (fechamento > fechamento.rolling(20).mean()).astype(float)
    a = acaso.testar_contra_o_acaso(
        fechamento, desejada, 0.0005, sorteios=100, semente=3
    )
    b = acaso.testar_contra_o_acaso(
        fechamento, desejada, 0.0005, sorteios=100, semente=3
    )
    assert a.p_valor == b.p_valor


# --- Sharpe probabilístico e deflacionado -------------------------------------------------


def test_psr_com_muito_ganho_e_perto_de_um_e_sem_ganho_perto_de_meio():
    rng = np.random.default_rng(0)
    bom = pd.Series(rng.normal(0.002, 0.01, 2000))
    assert acaso.calcular_sharpe_probabilistico(bom) > 0.99
    medias = [
        acaso.calcular_sharpe_probabilistico(
            pd.Series(np.random.default_rng(s).normal(0, 0.01, 500))
        )
        for s in range(60)
    ]
    assert 0.35 < np.mean(medias) < 0.65


def test_psr_com_poucos_dias_e_nan():
    assert np.isnan(acaso.calcular_sharpe_probabilistico(pd.Series([0.01] * 10)))


def test_sharpe_maximo_esperado_cresce_com_as_tentativas():
    valores = [
        acaso.calcular_sharpe_maximo_esperado(1.0, n) for n in (1, 2, 10, 100, 1000)
    ]
    assert valores[0] == 0
    assert valores == sorted(valores)
    assert acaso.calcular_sharpe_maximo_esperado(1.0, 100) == pytest.approx(
        2.533, abs=0.01
    )


def test_sharpe_maximo_esperado_recusa_zero_tentativas():
    with pytest.raises(ValueError):
        acaso.calcular_sharpe_maximo_esperado(1.0, 0)


def test_dsr_nao_se_deixa_enganar_pelo_melhor_de_muitos_candidatos_de_ruido():
    """O melhor de 50 candidatos sem valor parece bom no PSR comum, mas o DSR o desmascara."""
    psr_enganado, dsr_enganado = 0, 0
    for semente in range(40):
        rng = np.random.default_rng(semente)
        candidatos = pd.DataFrame(rng.normal(0, 0.01, (500, 50)))
        melhor = candidatos.apply(acaso._sharpe_diario).idxmax()
        psr_enganado += acaso.calcular_sharpe_probabilistico(candidatos[melhor]) > 0.95
        dsr_enganado += (
            acaso.calcular_sharpe_deflacionado(
                candidatos[melhor], candidatos
            ).probabilidade
            > 0.95
        )
    assert psr_enganado >= 20  # o Sharpe comum cai na armadilha quase sempre
    assert dsr_enganado <= 6  # o deflacionado, só ocasionalmente (esperado: ~5%)


def test_dsr_reconhece_um_candidato_realmente_bom():
    rng = np.random.default_rng(1)
    candidatos = pd.DataFrame(rng.normal(0, 0.01, (1500, 10)))
    candidatos[0] = rng.normal(0.003, 0.01, 1500)
    r = acaso.calcular_sharpe_deflacionado(candidatos[0], candidatos)
    assert r.probabilidade > 0.95
    assert r.tentativas == 10 and r.sharpe_anual > r.sharpe_anual_por_sorte


def test_tentativas_extras_pioram_o_dsr():
    rng = np.random.default_rng(2)
    candidatos = pd.DataFrame(rng.normal(0.0005, 0.01, (800, 8)))
    melhor = candidatos[candidatos.apply(acaso._sharpe_diario).idxmax()]
    sem = acaso.calcular_sharpe_deflacionado(melhor, candidatos)
    com = acaso.calcular_sharpe_deflacionado(melhor, candidatos, tentativas_extras=200)
    assert com.probabilidade < sem.probabilidade
    assert com.tentativas == 208


def test_dsr_recusa_entradas_ruins():
    candidatos = pd.DataFrame(np.random.default_rng(0).normal(0, 0.01, (200, 1)))
    with pytest.raises(ValueError, match="pelo menos 2"):
        acaso.calcular_sharpe_deflacionado(candidatos[0], candidatos)
    with pytest.raises(ValueError, match="negativas"):
        acaso.calcular_sharpe_deflacionado(candidatos[0], candidatos, -1)


# --- PBO ----------------------------------------------------------------------------------


def test_pbo_de_candidatos_sem_valor_fica_perto_de_meio():
    pbos = [
        acaso.calcular_pbo(
            pd.DataFrame(np.random.default_rng(s).normal(0, 0.01, (800, 20)))
        ).probabilidade
        for s in range(8)
    ]
    assert 0.3 < np.mean(pbos) < 0.7


def test_pbo_com_um_candidato_realmente_melhor_e_baixo():
    rng = np.random.default_rng(4)
    candidatos = pd.DataFrame(rng.normal(0, 0.01, (800, 10)))
    candidatos[0] = rng.normal(0.004, 0.01, 800)
    r = acaso.calcular_pbo(candidatos)
    assert r.probabilidade < 0.1
    assert r.combinacoes == 252  # C(10, 5)


def test_pbo_valida_entradas():
    base = pd.DataFrame(np.random.default_rng(0).normal(0, 0.01, (800, 5)))
    with pytest.raises(ValueError, match="par"):
        acaso.calcular_pbo(base, blocos=7)
    with pytest.raises(ValueError, match="2 candidatos"):
        acaso.calcular_pbo(base[[0]])
    with pytest.raises(ValueError, match="Poucos dados"):
        acaso.calcular_pbo(base.iloc[:30])
