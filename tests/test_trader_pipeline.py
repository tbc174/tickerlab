"""Atributos sem olhar o futuro, rótulo, armazém de séries e o pipeline com um CPCV pequeno."""

import numpy as np
import pandas as pd
import pytest

from trader import armazem, atributos, pipeline
from trader.rodar_baselines import SerieDoAtivo
from trader.universo import UNIVERSO
from trader.validacao import CPCV


def _ativo(simbolo):
    return next(a for a in UNIVERSO if a.simbolo == simbolo)


def _retornos(datas, seed, sinal=0.0):
    rng = np.random.default_rng(seed)
    ruido = rng.normal(0, 0.01, len(datas))
    r = pd.Series(ruido, index=datas)
    if sinal:  # um pouco de persistência: o retorno de ontem ajuda a prever o de hoje
        r = r + sinal * r.shift(1).fillna(0)
    return r


def _macro(datas):
    rng = np.random.default_rng(99)
    passeio = lambda base: pd.Series(
        base * np.exp(np.cumsum(rng.normal(0, 0.01, len(datas)))), index=datas
    )
    return {
        "vix": passeio(20),
        "juro_10a": passeio(3),
        "dolar": passeio(90),
        "petroleo": passeio(60),
        "cobre": passeio(3),
    }


@pytest.fixture(scope="module")
def mundo():
    uteis = pd.bdate_range("2000-01-03", periods=1600)
    todos_os_dias = pd.date_range("2000-01-03", uteis[-1], freq="D")
    series = [
        SerieDoAtivo(_ativo("EURUSD"), _retornos(uteis, 1, 0.1)),
        SerieDoAtivo(_ativo("PETR4.SA"), _retornos(uteis, 2, 0.1)),
        SerieDoAtivo(_ativo("^GSPC"), _retornos(uteis, 3, 0.1)),
        SerieDoAtivo(_ativo("BTC-USD"), _retornos(todos_os_dias, 4, 0.1)),
    ]
    painel = atributos.montar_painel(
        series, None, _macro(uteis), pd.Timestamp("2001-01-02"), uteis[-1]
    )
    return series, painel


# --- atributos e rótulo --------------------------------------------------------------------


def test_rotulo_olha_os_proximos_5_pregoes():
    r = pd.Series([0.01, -0.02, 0.03, 0.0, 0.01, -0.05, 0.02, 0.01])
    y = atributos.rotulo(r, 5)
    soma = r.iloc[1:6].sum()  # -0,02 + 0,03 + 0 + 0,01 - 0,05 = -0,03
    assert y.iloc[0] == float(soma > 0) == 0.0
    assert y.iloc[2] == float(r.iloc[3:8].sum() > 0)
    assert y.iloc[-5:].isna().all() and y.iloc[:3].notna().all()


def test_atributos_do_ativo_nao_olham_o_futuro():
    datas = pd.bdate_range("2000-01-03", periods=900)
    r = _retornos(datas, 5)
    a = atributos.atributos_do_ativo(r, 252)
    alterado = r.copy()
    alterado.iloc[-100:] = 0.05
    b = atributos.atributos_do_ativo(alterado, 252)
    pd.testing.assert_frame_equal(a.iloc[:-100], b.iloc[:-100])


def test_macro_e_sempre_da_vespera():
    datas = pd.bdate_range("2000-01-03", periods=600)
    macro = _macro(datas)
    a = atributos.atributos_macro(macro, datas)
    alterado = {k: v.copy() for k, v in macro.items()}
    alterado["vix"].iloc[-1] = 500.0  # choque no último dia
    b = atributos.atributos_macro(alterado, datas)
    pd.testing.assert_frame_equal(a, b)  # o último dia só vê a véspera


def test_painel_tem_todas_as_colunas_e_sem_infinito(mundo):
    _, painel = mundo
    for coluna in (*atributos.ATRIBUTOS, "y", "simbolo", "Date", "retorno_futuro"):
        assert coluna in painel.columns
    assert not np.isinf(painel[list(atributos.ATRIBUTOS)].to_numpy(dtype=float)).any()
    assert painel["simbolo"].nunique() == 4
    assert (painel.loc[painel["simbolo"] == "PETR4.SA", "classe_acoes_b3"] == 1).all()


# --- armazém -------------------------------------------------------------------------------


def test_armazem_guarda_e_monta_candidatos(tmp_path):
    datas = pd.bdate_range("2010-01-04", periods=50)
    a, b = "a" * 64, "b" * 64
    armazem.salvar(
        a, pd.Series(0.01, index=datas), pd.Series(0.0, index=datas), tmp_path
    )
    armazem.salvar(
        b,
        pd.Series(0.02, index=datas[10:]),
        pd.Series(0.0, index=datas[10:]),
        tmp_path,
        apelido="baseline_B1",
    )
    cand = armazem.candidatos(datas, pasta=tmp_path)
    assert list(cand.columns) == [a, b]  # o apelido não conta duas vezes
    assert cand[b].iloc[:10].eq(0).all()
    assert armazem.carregar("baseline_B1", tmp_path)["x1"].iloc[0] == 0.02
    with pytest.raises(FileNotFoundError):
        armazem.carregar("nao_existe", tmp_path)


# --- pipeline ------------------------------------------------------------------------------


CPCV_PEQUENO = CPCV(n_grupos=4, k_teste=2, expurgo=5, embargo=5)


def test_pipeline_monta_os_caminhos_completos(mundo):
    series, painel = mundo
    config = pipeline.Configuracao("teste", "logistica")
    res = pipeline.rodar(config, painel, series, None, cpcv=CPCV_PEQUENO)
    uteis = pipeline.dias_uteis(painel)
    assert len(res.caminhos) == CPCV_PEQUENO.n_caminhos == 3
    for c in res.caminhos + res.caminhos_x2:
        assert c.index.equals(uteis)
    assert set(res.por_ativo[0]) == {"EURUSD", "PETR4.SA", "^GSPC", "BTC-USD"}
    btc = res.por_ativo[0]["BTC-USD"]
    assert (btc.index.weekday >= 5).any()  # cripto no fim de semana entra no caminho
    assert res.posicoes[0].abs().max().max() <= 2.0 + 1e-9
    assert res.custo_por_lado["PETR4.SA"] == pytest.approx(0.0005)


def test_pipeline_custos_x2_nunca_melhoram(mundo):
    series, painel = mundo
    res = pipeline.rodar(
        pipeline.Configuracao("teste", "logistica"),
        painel,
        series,
        None,
        cpcv=CPCV_PEQUENO,
    )
    for c1, c2 in zip(res.caminhos, res.caminhos_x2, strict=True):
        assert c2.sum() <= c1.sum() + 1e-12


def test_variante_futuro_infla_e_embaralhado_some(mundo):
    series, painel = mundo
    config = pipeline.Configuracao(
        "teste", "lightgbm", ajustes={"n_estimators": 50, "min_child_samples": 50}
    )
    normal = pipeline.rodar(
        config, painel, series, None, "normal", CPCV_PEQUENO
    ).caminhos[1]
    futuro = pipeline.rodar(
        config, painel, series, None, "futuro", CPCV_PEQUENO
    ).caminhos[1]
    sharpe = lambda r: r.mean() / r.std() * np.sqrt(252)
    assert sharpe(futuro) > sharpe(normal) + 0.5


def test_variante_desconhecida_e_recusada(mundo):
    series, painel = mundo
    with pytest.raises(ValueError, match="Variante"):
        pipeline.rodar(
            pipeline.Configuracao("t", "logistica"),
            painel,
            series,
            None,
            "x",
            CPCV_PEQUENO,
        )


def test_especificacao_inclui_parametros_e_familia():
    c = pipeline.Configuracao("lgbm", "lightgbm", ajustes={"num_leaves": 7})
    spec = c.especificacao()
    assert c.familia == "H2" and spec["parametros"]["num_leaves"] == 7
    assert spec["parametros"]["min_child_samples"] == 500
    assert pipeline.Configuracao("l", "logistica").familia == "H1"
