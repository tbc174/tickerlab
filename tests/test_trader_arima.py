"""H5: ARIMA por ativo (só com os dias de treino) e a previsão da soma dos próximos pregões."""

import warnings

import numpy as np
import pytest
from statsmodels.tsa.statespace.sarimax import SARIMAX

from trader import arima, pipeline

warnings.filterwarnings("ignore")


def _ar1(n, phi, seed):
    rng = np.random.default_rng(seed)
    e = rng.normal(size=n)
    y = np.zeros(n)
    for t in range(1, n):
        y[t] = phi * y[t - 1] + e[t]
    return y


def test_soma_prevista_igual_a_previsao_do_statsmodels():
    y = _ar1(1500, 0.4, 1) + 0.05
    ajustado = SARIMAX(y[:1000], order=(2, 0, 1), trend="c").fit(disp=False)
    soma = arima.soma_prevista(ajustado, y, 5)
    for t in (999, 1200, 1490):
        esperado = ajustado.apply(y[: t + 1]).get_forecast(5).predicted_mean.sum()
        assert soma[t] == pytest.approx(esperado, rel=1e-6, abs=1e-9)


def test_previsao_so_usa_o_passado():
    y = _ar1(800, 0.4, 2)
    ajustado = arima.ajustar(np.where(np.arange(800) < 500, y, np.nan))
    a = arima.soma_prevista(ajustado, y, 5)
    mexido = y.copy()
    mexido[600:] = 0.0  # mudar o futuro não muda a previsão de antes dele
    b = arima.soma_prevista(ajustado, mexido, 5)
    assert np.allclose(a[:600], b[:600])


def test_acerta_a_direcao_de_uma_serie_persistente_e_o_embaralhado_nao():
    y = _ar1(3000, 0.5, 3)
    linhas = [np.arange(3000)]
    treino, teste = np.arange(2000), np.arange(2000, 2995)
    proximo = np.array([y[t + 1 : t + 6].sum() for t in teste])
    _, p = arima.prever_divisao(y, linhas, treino, teste, 5)
    # teto teórico para AR(1) com phi 0,5: correlação ~0,3 entre previsão e soma real, acerto
    # ≈ 0,5 + arcsen(0,3)/π ≈ 59,7%; acima de 56% em ~1000 dias já é bem mais que o acaso
    assert ((p > 0.5) == (proximo > 0)).mean() > 0.56
    _, p_emb = arima.prever_divisao(y, linhas, treino, teste, 5, embaralhar_com=7)
    assert abs(((p_emb > 0.5) == (proximo > 0)).mean() - 0.5) < 0.06


def test_ativo_com_pouco_treino_fica_neutro():
    y = _ar1(400, 0.5, 4)
    _, p = arima.prever_divisao(
        y, [np.arange(400)], np.arange(100), np.arange(100, 400), 5
    )
    assert np.all(p == 0.5)


def test_arima_e_familia_h5():
    assert pipeline.Configuracao("a", "arima").familia == "H5"


def test_pipeline_arima_roda(monkeypatch):
    from tests import test_trader_pipeline as tp

    series, painel = (
        tp.mundo.__wrapped__()
    )  # o mesmo mundo sintético dos testes do pipeline
    monkeypatch.setattr(
        arima, "ORDENS", ((0, 0), (1, 0))
    )  # rápido: 2 ordens bastam aqui
    res = pipeline.rodar(
        pipeline.Configuracao("a", "arima"),
        painel,
        series,
        None,
        cpcv=tp.CPCV_PEQUENO,
        trabalhadores=1,
    )
    assert len(res.caminhos) == 3 and all(c.notna().all() for c in res.caminhos)
