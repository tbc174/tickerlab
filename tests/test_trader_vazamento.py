"""Verificações de vazamento com um pipeline de brinquedo (honesto e desonesto)."""

import numpy as np
import pandas as pd
import pytest

from trader import vazamento

N = 3000
DATAS = pd.bdate_range("2005-01-03", periods=N)
_rng = np.random.default_rng(0)
RETORNO = pd.Series(_rng.normal(0, 0.01, N), index=DATAS)
# atributo com sinal fraco e real: prevê um pouco o retorno de amanhã
ATRIBUTO = pd.Series(
    0.15 * RETORNO.shift(-1).fillna(0) / 0.01 + _rng.normal(0, 1, N), index=DATAS
)


def _pipeline(trapaca_escondida=False):
    def rodar(variante):
        x = ATRIBUTO.copy()
        if variante == "futuro":
            x = pd.Series(np.sign(RETORNO.shift(-1).fillna(0)), index=DATAS)
        rng = np.random.default_rng(1)
        if variante == "embaralhado":
            x = pd.Series(rng.permutation(x.to_numpy()), index=DATAS)
        if trapaca_escondida:
            # erro escondido: até a variante "normal" já enxerga o retorno de amanhã
            x = pd.Series(np.sign(RETORNO.shift(-1).fillna(0)), index=DATAS)
        posicao = np.sign(x)
        return (posicao.shift(1).fillna(0) * RETORNO).loc[DATAS[1:]]

    return rodar


def test_pipeline_honesto_passa_nas_tres():
    aprov, det = vazamento.verificar(_pipeline())
    assert aprov == {
        "futuro_inflou": True,
        "rotulos_embaralhados_zero": True,
        "reprodutivel": True,
    }
    assert det["sharpe_futuro"] > det["sharpe_normal"]


def test_pipeline_que_ja_olha_o_futuro_nao_infla_e_e_pego():
    aprov, _ = vazamento.verificar(_pipeline(trapaca_escondida=True))
    assert (
        aprov["futuro_inflou"] is False
    )  # o "normal" já é tão bom quanto olhar o futuro


def test_pipeline_nao_reprodutivel_e_pego():
    contador = {"n": 0}

    def instavel(variante):
        contador["n"] += 1
        return RETORNO * (1 + 0.01 * contador["n"])

    aprov2, _ = vazamento.verificar(instavel)
    assert aprov2["reprodutivel"] is False


def test_erro_padrao_do_sharpe():
    r = pd.Series(np.random.default_rng(3).normal(0, 0.01, 2520))  # 10 anos
    assert vazamento.erro_padrao_do_sharpe(r) == pytest.approx(
        np.sqrt(1 / 10), rel=0.05
    )
