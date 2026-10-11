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
        if variante == "proporcao":
            x = pd.Series(1.0, index=DATAS)
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
        "embaralhado_nao_supera_a_proporcao": True,
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


# --- regra da v0.2: embaralhado contra a referência da proporção ------------------------------
DERIVA = pd.Series(
    _rng.normal(0.0008, 0.01, N), index=DATAS
)  # mercado que sobe (Sharpe ~1,3)


def _com_vies_comprado(vazar_no_embaralhado=False):
    """Pipeline sem vazamento num mercado que sobe: sorteando os rótulos, só sobra 'fique comprado'."""

    def rodar(variante):
        rng = np.random.default_rng(7)
        if variante == "futuro":
            posicao = pd.Series(np.sign(DERIVA.shift(-1).fillna(0)), index=DATAS)
        elif variante == "embaralhado":
            ruido = pd.Series(
                rng.normal(0, 0.3, N), index=DATAS
            )  # o que o modelo sorteado "aprende"
            posicao = 0.7 + ruido  # ruído simétrico em torno da posição da referência
            if vazar_no_embaralhado:  # erro: o embaralhado ainda enxerga o amanhã
                posicao = pd.Series(np.sign(DERIVA.shift(-1).fillna(0)), index=DATAS)
        elif variante == "proporcao":
            posicao = pd.Series(0.7, index=DATAS)
        else:
            posicao = pd.Series(0.5, index=DATAS)
        return (posicao.shift(1).fillna(0) * DERIVA).loc[DATAS[1:]]

    return rodar


def test_vies_comprado_sem_vazamento_passa_na_regra_da_v02():
    aprov, det = vazamento.verificar(_com_vies_comprado())
    # na v0.1 isto reprovava: o embaralhado sozinho rende como comprar e segurar
    assert det["sharpe_embaralhado"] > 2 * vazamento.erro_padrao_do_sharpe(DERIVA)
    assert aprov["embaralhado_nao_supera_a_proporcao"] is True
    assert abs(det["sharpe_da_diferenca"]) <= det["limite_da_diferenca"]


def test_embaralhado_que_vaza_e_pego_mesmo_com_vies_comprado():
    aprov, det = vazamento.verificar(_com_vies_comprado(vazar_no_embaralhado=True))
    assert aprov["embaralhado_nao_supera_a_proporcao"] is False
    assert det["sharpe_da_diferenca"] > det["limite_da_diferenca"]


def test_embaralhado_identico_a_proporcao_passa():
    def rodar(variante):
        return DERIVA if variante in ("embaralhado", "proporcao") else DERIVA * 0.5

    aprov, det = vazamento.verificar(rodar)
    assert aprov["embaralhado_nao_supera_a_proporcao"] is True
    assert det["sharpe_da_diferenca"] == 0.0


def test_embaralhado_que_rende_menos_nao_e_vazamento():
    """v0.4: ruído que paga custo deixa o embaralhado abaixo da referência; isso não reprova."""
    custo_do_ruido = pd.Series(-0.0004, index=DATAS)  # giro à toa, todo dia

    def rodar(variante):
        if variante == "embaralhado":
            return DERIVA + custo_do_ruido
        return DERIVA if variante == "proporcao" else DERIVA * 0.5

    aprov, det = vazamento.verificar(rodar)
    assert det["sharpe_da_diferenca"] < -det["limite_da_diferenca"]  # na v0.3 reprovava
    assert aprov["embaralhado_nao_supera_a_proporcao"] is True
