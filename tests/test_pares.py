"""Testes de src/pares.py."""

import numpy as np
import pandas as pd
import pytest

from src import pares as pr


def _ornstein(n, semente, phi=0.95, vol=0.01):
    rng = np.random.default_rng(semente)
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = phi * x[t - 1] + rng.normal(0, vol)
    return x


def _par_cointegrado(n=1000, semente=0, beta=0.8, phi=0.95):
    rng = np.random.default_rng(semente)
    log_b = np.cumsum(rng.normal(0.0002, 0.012, n)) + np.log(50)
    log_a = beta * log_b + 0.3 + _ornstein(n, semente + 100, phi, 0.01)
    indice = pd.bdate_range("2019-01-02", periods=n)
    return pd.Series(np.exp(log_a), index=indice), pd.Series(
        np.exp(log_b), index=indice
    )


def _passeios_independentes(n=1000, semente=0):
    rng = np.random.default_rng(semente)
    indice = pd.bdate_range("2019-01-02", periods=n)
    a = np.exp(np.cumsum(rng.normal(0.0002, 0.012, n)))
    b = np.exp(np.cumsum(rng.normal(0.0002, 0.012, n)))
    return pd.Series(a * 50, index=indice), pd.Series(b * 50, index=indice)


# --- estatística do spread ----------------------------------------------------------------


def test_relacao_recupera_o_beta_verdadeiro():
    a, b = _par_cointegrado(beta=0.8)
    _, beta = pr.estimar_relacao(np.log(a), np.log(b))
    assert beta == pytest.approx(0.8, abs=0.1)


def test_adf_separa_serie_que_volta_de_passeio_aleatorio():
    estacionarias = [
        pr.calcular_adf(pd.Series(_ornstein(600, s, 0.9))) for s in range(40)
    ]
    passeios = [
        pr.calcular_adf(pd.Series(np.cumsum(np.random.default_rng(s).normal(size=600))))
        for s in range(40)
    ]
    assert np.mean([t < -2.86 for t in estacionarias]) > 0.95
    assert np.mean([t < -2.86 for t in passeios]) < 0.15  # ~5% de falsos positivos


def test_cointegracao_de_engle_granger_taxa_de_falso_positivo():
    falsos = 0
    verdadeiros = 0
    for s in range(60):
        a, b = _passeios_independentes(600, s)
        falsos += pr.analisar_par(np.log(a), np.log(b)).cointegrado
        a, b = _par_cointegrado(600, s)
        verdadeiros += pr.analisar_par(np.log(a), np.log(b)).cointegrado
    assert falsos / 60 < 0.2
    assert verdadeiros / 60 > 0.85


def test_meia_vida_de_um_ar1_conhecido():
    spread = pd.Series(_ornstein(20000, 1, phi=0.9, vol=1.0))
    esperado = -np.log(2) / np.log(0.9)
    assert pr.calcular_meia_vida(spread) == pytest.approx(esperado, rel=0.1)
    passeio = pd.Series(np.cumsum(np.random.default_rng(2).normal(size=3000)))
    assert pr.calcular_meia_vida(passeio) > 100  # praticamente não volta


def test_estatisticas_validam_entradas():
    curta = pd.Series(np.arange(10.0))
    with pytest.raises(ValueError, match="30 dias"):
        pr.estimar_relacao(curta, curta)
    with pytest.raises(ValueError, match="Poucos dias"):
        pr.calcular_adf(curta)
    with pytest.raises(ValueError, match="negativas"):
        pr.calcular_adf(pd.Series(np.arange(100.0)), -1)
    with pytest.raises(ValueError, match="Poucos dias"):
        pr.calcular_meia_vida(curta)


# --- sinal --------------------------------------------------------------------------------


def test_z_do_spread_nao_olha_o_futuro():
    spread = pd.Series(_ornstein(400, 3))
    completo = pr.calcular_z_do_spread(spread, 60)
    cortado = pr.calcular_z_do_spread(spread.iloc[:-50], 60)
    assert np.allclose(completo.iloc[:-50], cortado, equal_nan=True)
    with pytest.raises(ValueError, match="pelo menos 10"):
        pr.calcular_z_do_spread(spread, 5)


def test_lado_entra_sai_e_corta_a_perda():
    z = pd.Series([0, -3, -2.5, -1, -0.3, 0, 3, 1, 0.2, 3, 5, 3, 1.5, 3])
    lado = pr.gerar_lado_do_par(z, entrada=2, saida=0.5, stop=4)
    assert list(lado) == [
        0,  # z = 0: nada
        1,  # abaixo de −2: compra A, vende B
        1,
        1,
        0,  # |z| ≤ 0,5: sai
        0,
        -1,  # acima de 2: vende A, compra B
        -1,
        0,  # sai
        -1,  # entra de novo
        0,  # passou do stop de 4: corta
        0,  # 3 ainda está acima da entrada: continua fora
        0,  # 1,5 voltou para dentro da entrada
        -1,  # 3: entrada nova depois do corte
    ]


def test_lado_valida_faixas_e_trata_vazios():
    z = pd.Series([np.nan, -3.0, 0.0])
    assert list(pr.gerar_lado_do_par(z)) == [0, 1, 0]
    with pytest.raises(ValueError, match="saída < entrada < stop"):
        pr.gerar_lado_do_par(z, entrada=1, saida=2, stop=3)


# --- backtest -----------------------------------------------------------------------------


def test_backtest_do_par_com_numeros_conferidos_a_mao():
    indice = pd.bdate_range("2026-01-05", periods=4)
    a = pd.Series([100.0, 110.0, 110.0, 110.0], index=indice)
    b = pd.Series([100.0, 100.0, 100.0, 100.0], index=indice)
    lado = pd.Series([1.0, 1.0, 0.0, 0.0], index=indice)  # decide comprado no dia 0
    r = pr.executar_backtest_do_par(a, b, lado, beta=1.0, custo_por_operacao=0.001)
    # dia 1: a sobe 10%, b fica parado: (0,10 − 0)/(1+1) = 5%, menos 0,1% de custo de entrada
    assert r.retorno.iloc[1] == pytest.approx(0.05 - 0.001)
    assert r.retorno.iloc[0] == 0
    assert r.retorno.iloc[2] == 0  # segue posicionado, preços parados
    assert r.retorno.iloc[3] == pytest.approx(-0.001)  # custo da saída
    assert r.giro == pytest.approx(2.0)
    assert len(r.operacoes) == 1


def test_lado_vendido_ganha_quando_a_cai():
    indice = pd.bdate_range("2026-01-05", periods=3)
    a = pd.Series([100.0, 90.0, 90.0], index=indice)
    b = pd.Series([100.0, 100.0, 100.0], index=indice)
    lado = pd.Series([-1.0, -1.0, 0.0], index=indice)
    r = pr.executar_backtest_do_par(a, b, lado, 1.0, 0.0)
    assert r.retorno.iloc[1] == pytest.approx(0.05)


def test_backtest_do_par_valida_entradas():
    indice = pd.bdate_range("2026-01-05", periods=3)
    a = pd.Series([1.0, 2.0, 3.0], index=indice)
    with pytest.raises(ValueError, match="mesmas datas"):
        pr.executar_backtest_do_par(a, a.iloc[1:], a, 1.0)
    with pytest.raises(ValueError, match="negativo"):
        pr.executar_backtest_do_par(a, a, a * 0, 1.0, -1)


# --- simulação completa -------------------------------------------------------------------


def test_simular_par_opera_so_no_teste_e_ganha_quando_a_relacao_persiste():
    a, b = _par_cointegrado(1500, semente=4)
    r = pr.simular_par(a, b, custo_por_operacao=0.0005)
    assert r.backtest.curva_de_capital.index[0] == r.inicio_do_teste
    assert (r.lado.loc[: r.inicio_do_teste].iloc[:-1] == 0).all()
    assert r.treino.cointegrado and r.teste.cointegrado
    assert r.backtest.curva_de_capital.iloc[-1] > 1.0
    assert len(r.backtest.operacoes) >= 5


def test_simular_par_de_passeios_independentes_nao_promete_nada():
    ganhos = []
    for s in range(10):
        a, b = _passeios_independentes(1500, s)
        ganhos.append(pr.simular_par(a, b).backtest.curva_de_capital.iloc[-1] - 1)
    assert abs(np.mean(ganhos)) < 0.25  # nenhum efeito sistemático grande


def test_simular_par_valida_entradas():
    a, b = _par_cointegrado(1000)
    with pytest.raises(ValueError, match="fração"):
        pr.simular_par(a, b, fracao_de_treino=0.95)
    with pytest.raises(ValueError, match="Poucos dias"):
        pr.simular_par(a.iloc[:100], b.iloc[:100])


def test_procurar_pares_lista_todas_as_combinacoes_ordenadas():
    a, b = _par_cointegrado(1000, semente=6)
    c, _ = _passeios_independentes(1000, 7)
    tabela = pr.procurar_pares(pd.DataFrame({"A": a, "B": b, "C": c}))
    assert len(tabela) == 3
    assert tabela.index[0] == "A × B"  # o par ligado tem o ADF mais negativo
    assert tabela["ADF no treino"].is_monotonic_increasing
    assert {"Correlação", "Beta", "Continuou no teste"} <= set(tabela.columns)
    with pytest.raises(ValueError, match="2 a 8"):
        pr.procurar_pares(pd.DataFrame({"A": a}))
    with pytest.raises(ValueError, match="fração"):
        pr.procurar_pares(pd.DataFrame({"A": a, "B": b}), 0.1)
