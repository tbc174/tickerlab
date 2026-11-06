"""t-estatística com a correção de Lo (A5 do pré-registro quant): autocorrelação positiva reduz o t."""

import numpy as np
import pandas as pd
import pytest

from trader import avaliacao


def _serie(valores):
    return pd.Series(valores, index=pd.bdate_range("2010-01-04", periods=len(valores)))


def _ar1(n, phi, media, semente):
    gerador = np.random.default_rng(semente)
    ruido = gerador.normal(0.0, 0.01, n)
    valores = np.empty(n)
    valores[0] = ruido[0]
    for i in range(1, n):
        valores[i] = phi * valores[i - 1] + ruido[i]
    return _serie(valores + media)


def test_sem_defasagens_e_a_t_comum():
    r = _ar1(2000, 0.0, 0.0005, 1)
    assert avaliacao.t_estatistica_corrigida(r, defasagens=0) == pytest.approx(
        avaliacao.t_estatistica(r)
    )


def test_ruido_independente_fica_perto_da_t_comum():
    r = _ar1(4000, 0.0, 0.0005, 2)
    comum = avaliacao.t_estatistica(r)
    corrigida = avaliacao.t_estatistica_corrigida(r)
    assert abs(corrigida - comum) / comum < 0.15


def test_autocorrelacao_positiva_reduz_a_t():
    r = _ar1(4000, 0.6, 0.0005, 3)
    assert avaliacao.t_estatistica_corrigida(r) < 0.8 * avaliacao.t_estatistica(r)


def test_numero_de_defasagens_segue_a_regra_de_newey_west():
    assert avaliacao.defasagens_de_newey_west(100) == 4
    assert avaliacao.defasagens_de_newey_west(2500) == 8


def test_series_degeneradas_dao_nan():
    assert np.isnan(avaliacao.t_estatistica_corrigida(_serie([0.01, 0.01, 0.01])))
    assert np.isnan(avaliacao.t_estatistica_corrigida(_serie([0.01])))
