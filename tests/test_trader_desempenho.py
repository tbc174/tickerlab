"""A versão rápida (preparo único, numba, joblib) dá exatamente o mesmo resultado da versão simples."""

import numpy as np
import pandas as pd
import pytest

from trader import pipeline, posicao
from trader.backtest import executar_backtest
from trader.baselines import preco_sintetico
from trader.custos import custos_do_ativo
from trader.juros import PAIS_PARA_MOEDA
from trader.rodar_baselines import SerieDoAtivo
from trader.universo import UNIVERSO
from trader.validacao import CPCV


def _ativo(simbolo):
    return next(a for a in UNIVERSO if a.simbolo == simbolo)


@pytest.fixture(scope="module")
def ambiente():
    datas = pd.bdate_range("2003-01-02", periods=1500)
    rng = np.random.default_rng(11)
    taxas = pd.DataFrame(
        rng.uniform(0, 10, (len(datas), len(PAIS_PARA_MOEDA))),
        index=datas,
        columns=list(PAIS_PARA_MOEDA.values()),
    )
    serie = SerieDoAtivo(
        _ativo("USDJPY"), pd.Series(rng.normal(0, 0.007, len(datas)), index=datas)
    )
    sinal = pd.Series(
        np.sin(np.arange(len(datas)) / 13) + rng.normal(0, 0.3, len(datas)), index=datas
    )
    return serie, taxas, sinal


def test_buffer_compilado_igual_ao_laco_em_python():
    rng = np.random.default_rng(3)
    ideal = rng.normal(0, 1, 2000)
    ideal[::97] = np.nan
    faixa = np.abs(rng.normal(0, 0.1, 2000))
    faixa[::131] = np.nan
    esperado, atual = [], 0.0
    for alvo, f in zip(ideal, faixa, strict=True):
        alvo = 0.0 if np.isnan(alvo) else alvo
        f = 0.0 if np.isnan(f) else f
        if atual < alvo - f:
            atual = alvo - f
        elif atual > alvo + f:
            atual = alvo + f
        esperado.append(atual)
    np.testing.assert_allclose(posicao.buffer_numpy(ideal, faixa), esperado)


def test_posicao_rapida_igual_ao_dimensionar(ambiente):
    serie, taxas, sinal = ambiente
    prep = pipeline.preparar_ativos([serie], taxas)["USDJPY"]
    esperado = posicao.dimensionar(
        sinal, serie.retorno, dias_por_ano=serie.dias_por_ano
    )
    np.testing.assert_allclose(prep.posicao(sinal.to_numpy()), esperado.to_numpy())


@pytest.mark.parametrize("mult", [1.0, 2.0])
def test_retorno_rapido_igual_ao_executar_backtest(ambiente, mult):
    serie, taxas, sinal = ambiente
    prep = pipeline.preparar_ativos([serie], taxas)["USDJPY"]
    pos = prep.posicao(sinal.to_numpy())
    esperado = executar_backtest(
        preco_sintetico(serie.retorno),
        pd.Series(pos, index=serie.retorno.index),
        custos_do_ativo(serie.ativo, mult, taxas, serie.retorno.index),
        limite=posicao.TETO_PADRAO,
        retorno_do_ativo=serie.retorno,
    )
    np.testing.assert_allclose(
        prep.retorno_liquido(pos, mult), esperado.retorno.to_numpy()
    )


def test_paralelo_igual_a_sequencial():
    from tests.test_trader_pipeline import _macro, _retornos
    from trader import atributos

    uteis = pd.bdate_range("2000-01-03", periods=1300)
    series = [
        SerieDoAtivo(_ativo("EURUSD"), _retornos(uteis, 21, 0.1)),
        SerieDoAtivo(_ativo("^GSPC"), _retornos(uteis, 22, 0.1)),
    ]
    painel = atributos.montar_painel(
        series, None, _macro(uteis), pd.Timestamp("2001-01-02"), uteis[-1]
    )
    cpcv = CPCV(n_grupos=4, k_teste=2, expurgo=5, embargo=5)
    config = pipeline.Configuracao("t", "logistica")
    um = pipeline.rodar(config, painel, series, None, cpcv=cpcv, trabalhadores=1)
    dois = pipeline.rodar(config, painel, series, None, cpcv=cpcv, trabalhadores=2)
    for a, b in zip(um.caminhos, dois.caminhos, strict=True):
        pd.testing.assert_series_equal(a, b)
    emb1 = pipeline.rodar(
        config, painel, series, None, "embaralhado", cpcv, trabalhadores=1
    )
    emb2 = pipeline.rodar(
        config, painel, series, None, "embaralhado", cpcv, trabalhadores=2
    )
    pd.testing.assert_series_equal(emb1.caminhos[0], emb2.caminhos[0])
