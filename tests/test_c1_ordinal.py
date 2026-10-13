"""Logística ordinal com L2 do modelo C-1 (pré-registro v2, seção 6), em dados sintéticos com os
coeficientes conhecidos."""

import numpy as np
import pytest
from scipy.optimize import check_grad

from base.cripto.c1.ordinal import LogisticaOrdinal, _perda_e_gradiente


def _amostra(n: int = 4000, semente: int = 7):
    rng = np.random.default_rng(semente)
    x = rng.normal(size=(n, 2))
    beta = np.array([1.5, -0.8])
    latente = x @ beta + rng.logistic(size=n)
    y = np.digitize(latente, [-0.5, 0.7])  # 0, 1 ou 2
    return x, y, beta


def test_recupera_os_coeficientes_de_uma_serie_sintetica():
    x, y, beta = _amostra()

    modelo = LogisticaOrdinal(c=1e6).ajustar(x, y)

    # os coeficientes ficam na escala das entradas padronizadas: volta para a escala original
    assert modelo.coeficientes_originais() == pytest.approx(beta, abs=0.12)


def test_limites_em_ordem_e_probabilidades_somam_um():
    x, y, _ = _amostra()

    modelo = LogisticaOrdinal(c=1.0).ajustar(x, y)
    probabilidades = modelo.probabilidades(x)

    assert modelo.limites[0] < modelo.limites[1]
    assert probabilidades.shape == (len(x), 3)
    assert probabilidades.sum(axis=1) == pytest.approx(np.ones(len(x)))
    assert (probabilidades >= 0).all()


def test_l2_encolhe_os_coeficientes():
    x, y, _ = _amostra()

    forte = LogisticaOrdinal(c=0.001).ajustar(x, y)
    fraca = LogisticaOrdinal(c=1000.0).ajustar(x, y)

    assert np.linalg.norm(forte.coeficientes) < np.linalg.norm(fraca.coeficientes)


def test_gradiente_confere_com_o_numerico():
    x, y, _ = _amostra(n=200)
    parametros = np.array(
        [0.3, -0.2, -0.4, 0.1]
    )  # 2 coeficientes, limite inicial, log do intervalo

    erro = check_grad(
        lambda p: _perda_e_gradiente(p, x, y, 2.0)[0],
        lambda p: _perda_e_gradiente(p, x, y, 2.0)[1],
        parametros,
    )

    assert erro < 1e-4


def test_entrada_constante_nao_quebra_a_padronizacao():
    x, y, _ = _amostra(n=300)
    x[:, 1] = 5.0

    probabilidades = LogisticaOrdinal(c=1.0).ajustar(x, y).probabilidades(x)

    assert np.isfinite(probabilidades).all()
