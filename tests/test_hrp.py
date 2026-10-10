"""Testes de src/hrp.py."""

import numpy as np
import pandas as pd
import pytest

from src.hrp import calcular_pesos_hrp


def _retornos(n=500, semente=0):
    rng = np.random.default_rng(semente)
    base = rng.normal(0, 0.01, n)
    return pd.DataFrame(
        {
            "A": base + rng.normal(0, 0.002, n),
            "A2": base + rng.normal(0, 0.002, n),  # quase igual ao A
            "B": rng.normal(0, 0.01, n),  # independente
        }
    )


def test_pesos_sao_positivos_e_somam_um():
    pesos = calcular_pesos_hrp(_retornos())
    assert (pesos > 0).all()
    assert pesos.sum() == pytest.approx(1.0)
    assert list(pesos.index) == ["A", "A2", "B"]


def test_com_dois_ativos_vira_o_inverso_da_variancia():
    r = _retornos()[["A", "B"]]
    pesos = calcular_pesos_hrp(r)
    inverso = 1 / r.var()
    assert pesos["A"] == pytest.approx(inverso["A"] / inverso.sum())


def test_ativos_parecidos_dividem_uma_mesma_fatia():
    pesos = calcular_pesos_hrp(_retornos())
    # o independente fica com cerca de metade; os dois parecidos dividem a outra metade
    assert pesos["B"] == pytest.approx(0.5, abs=0.06)
    assert pesos["A"] + pesos["A2"] == pytest.approx(0.5, abs=0.06)


def test_ativo_mais_arriscado_recebe_menos():
    rng = np.random.default_rng(3)
    r = pd.DataFrame(
        {
            "calmo": rng.normal(0, 0.005, 600),
            "medio": rng.normal(0, 0.01, 600),
            "agitado": rng.normal(0, 0.03, 600),
        }
    )
    pesos = calcular_pesos_hrp(r)
    assert pesos["calmo"] > pesos["medio"] > pesos["agitado"]


def test_a_ordem_das_colunas_nao_muda_os_pesos():
    r = _retornos(semente=5)
    a = calcular_pesos_hrp(r)
    b = calcular_pesos_hrp(r[["B", "A2", "A"]])
    assert a["A"] == pytest.approx(b["A"]) and a["B"] == pytest.approx(b["B"])


def test_valida_entradas():
    r = _retornos()
    with pytest.raises(ValueError, match="pelo menos 2"):
        calcular_pesos_hrp(r[["A"]])
    with pytest.raises(ValueError, match="Poucos dias"):
        calcular_pesos_hrp(r.iloc[:10])
    with pytest.raises(ValueError, match="não varia"):
        calcular_pesos_hrp(r.assign(B=0.0))
