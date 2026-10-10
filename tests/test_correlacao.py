"""Testes de src/correlacao.py."""

import numpy as np
import pandas as pd
import pytest

from src import correlacao as co


def _retornos(n=1000, semente=0):
    rng = np.random.default_rng(semente)
    indice = rng.normal(0.0003, 0.01, n)
    datas = pd.bdate_range("2021-01-04", periods=n)
    return pd.DataFrame(
        {
            "IND": indice,
            "dobro": 2 * indice + rng.normal(0, 0.005, n) + 0.0002,
            "metade": 0.5 * indice + rng.normal(0, 0.005, n),
            "solto": rng.normal(0, 0.01, n),
        },
        index=datas,
    )


def test_beta_recupera_a_inclinacao_verdadeira():
    r = _retornos()
    resultado = co.calcular_beta(r["dobro"], r["IND"])
    assert resultado.beta == pytest.approx(2.0, abs=0.1)
    assert resultado.beta_minimo < 2.0 < resultado.beta_maximo
    assert resultado.alfa_anual == pytest.approx(0.0002 * 252, abs=0.05)
    assert resultado.r_quadrado == pytest.approx(resultado.correlacao**2)


def test_beta_com_numeros_conferidos_a_mao():
    indice = pd.Series(np.tile([0.01, -0.01], 20))
    ativo = 1.5 * indice
    r = co.calcular_beta(ativo, indice)
    assert r.beta == pytest.approx(1.5)
    assert r.alfa_anual == pytest.approx(0.0, abs=1e-12)
    assert r.correlacao == pytest.approx(1.0)
    assert r.beta_maximo - r.beta_minimo == pytest.approx(0.0, abs=1e-9)


def test_o_beta_do_indice_contra_ele_mesmo_e_um():
    r = _retornos()
    assert co.calcular_beta(r["IND"], r["IND"]).beta == pytest.approx(1.0)


def test_beta_valida_entradas():
    r = _retornos()
    with pytest.raises(ValueError, match="pelo menos 30"):
        co.calcular_beta(r["dobro"].iloc[:10], r["IND"].iloc[:10])
    with pytest.raises(ValueError, match="não variou"):
        co.calcular_beta(r["dobro"], pd.Series(0.0, index=r.index))


def test_resumo_de_betas_exclui_o_indice_e_ordena_as_colunas():
    tabela = co.resumir_betas(_retornos(), "IND")
    assert list(tabela.index) == ["dobro", "metade", "solto"]
    assert (
        tabela.loc["dobro", "Beta"]
        > tabela.loc["metade", "Beta"]
        > tabela.loc["solto", "Beta"]
    )
    assert abs(tabela.loc["solto", "Beta"]) < 0.15
    assert list(tabela.columns[:3]) == ["Beta", "Beta (mín. 95%)", "Beta (máx. 95%)"]
    with pytest.raises(ValueError, match="não está"):
        co.resumir_betas(_retornos(), "XYZ")
    with pytest.raises(ValueError, match="pelo menos um ativo"):
        co.resumir_betas(_retornos()[["IND"]], "IND")


def test_beta_movel_bate_com_o_beta_da_ultima_janela():
    r = _retornos()
    movel = co.calcular_beta_movel(r["dobro"], r["IND"], janela=100)
    ultimo = co.calcular_beta(r["dobro"].iloc[-100:], r["IND"].iloc[-100:]).beta
    assert movel.iloc[-1] == pytest.approx(ultimo)
    assert len(movel) == len(r) - 99
    with pytest.raises(ValueError, match="pelo menos 30"):
        co.calcular_beta_movel(r["dobro"], r["IND"], janela=10)


def test_beta_movel_mostra_a_mudanca_de_regime():
    rng = np.random.default_rng(1)
    indice = pd.Series(rng.normal(0, 0.01, 800))
    ativo = pd.concat([0.5 * indice.iloc[:400], 1.5 * indice.iloc[400:]])
    movel = co.calcular_beta_movel(ativo, indice, 100)
    assert movel.iloc[250] == pytest.approx(0.5, abs=0.01)
    assert movel.iloc[-1] == pytest.approx(1.5, abs=0.01)


def test_correlacao_movel_bate_com_a_da_ultima_janela():
    r = _retornos()
    movel = co.calcular_correlacao_movel(r["dobro"], r["IND"], 100)
    assert movel.iloc[-1] == pytest.approx(
        r["dobro"].iloc[-100:].corr(r["IND"].iloc[-100:])
    )


def test_correlacao_pode_subir_nos_piores_dias_do_indice():
    rng = np.random.default_rng(2)
    n = 3000
    indice = rng.normal(0, 0.01, n)
    # o ativo quase ignora o índice, exceto nos dias de queda forte, quando o acompanha
    ativo = np.where(indice < -0.01, 1.0, 0.0) * indice + rng.normal(0, 0.002, n)
    retornos = pd.DataFrame({"IND": indice, "A": ativo})
    tabela = co.calcular_correlacao_nas_quedas(retornos, "IND", 0.1)
    assert tabela.loc["A", "Piores dias do índice"] > tabela.loc["A", "Todos os dias"]
    with pytest.raises(ValueError, match="entre 0 e 0,5"):
        co.calcular_correlacao_nas_quedas(retornos, "IND", 0.7)
    with pytest.raises(ValueError, match="poucos dias"):
        co.calcular_correlacao_nas_quedas(retornos.iloc[:40], "IND", 0.1)
    with pytest.raises(ValueError, match="não está"):
        co.calcular_correlacao_nas_quedas(retornos, "XYZ")


def test_calcular_retornos_tira_a_primeira_linha():
    precos = pd.DataFrame({"A": [100.0, 110.0, 121.0]})
    retornos = co.calcular_retornos(precos)
    assert list(retornos["A"]) == pytest.approx([0.1, 0.1])
