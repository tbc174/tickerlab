"""Pesquisa 2, P5 parte 3: carteira e custos (dados sintéticos; nenhum dado real)."""

import numpy as np
import pandas as pd
import pytest

from trader.p2 import carteira
from trader.p2.mercados import Mercado, por_codigo

DATAS = pd.bdate_range("2000-01-03", periods=2600)


def _tabela(retornos):
    r = pd.Series(retornos, index=DATAS[: len(retornos)])
    return pd.DataFrame({"preco": r, "carry_anual": 0.0, "total": r})


def _aleatorios(semente, desvio=0.01, media=0.0):
    return np.random.default_rng(semente).normal(media, desvio, len(DATAS))


def test_pesos_seguem_os_grupos_e_somam_um():
    mercados = {
        c: por_codigo(c) for c in ("EURUSD", "GBPUSD", "USA500", "GOLD", "WTI", "UST10")
    }
    disponivel = pd.DataFrame(True, index=DATAS[:3], columns=list(mercados))
    pesos = carteira.pesos_de_risco(mercados, disponivel)
    assert pesos.sum(axis=1).to_numpy() == pytest.approx([1.0] * 3)
    assert pesos["EURUSD"].iloc[0] == pytest.approx(0.15)  # moedas 30% ÷ 2
    assert pesos["UST10"].iloc[0] == pytest.approx(0.10)


def test_grupo_sem_mercado_tem_o_peso_repartido():
    mercados = {c: por_codigo(c) for c in ("EURUSD", "USA500")}
    disponivel = pd.DataFrame({"EURUSD": [True], "USA500": [True]}, index=DATAS[:1])
    pesos = carteira.pesos_de_risco(mercados, disponivel)
    assert pesos.iloc[0].to_dict() == pytest.approx({"EURUSD": 0.5, "USA500": 0.5})


def test_mercado_indisponivel_fica_com_peso_zero():
    mercados = {c: por_codigo(c) for c in ("EURUSD", "GBPUSD")}
    disponivel = pd.DataFrame({"EURUSD": [True], "GBPUSD": [False]}, index=DATAS[:1])
    assert carteira.pesos_de_risco(mercados, disponivel)["GBPUSD"].iloc[0] == 0


def test_idm_de_dois_mercados_independentes_e_raiz_de_dois():
    retornos = pd.DataFrame({"a": _aleatorios(1), "b": _aleatorios(2)}, index=DATAS)
    pesos = pd.DataFrame(0.5, index=DATAS, columns=["a", "b"])
    idm = carteira.idm_anual(retornos, pesos)
    assert idm.iloc[0] == 1.0  # primeiro ano: sem passado
    assert idm.iloc[-1] == pytest.approx(np.sqrt(2), abs=0.1)


def test_idm_de_mercados_iguais_e_um():
    a = _aleatorios(1)
    retornos = pd.DataFrame({"a": a, "b": a}, index=DATAS)
    pesos = pd.DataFrame(0.5, index=DATAS, columns=["a", "b"])
    assert carteira.idm_anual(retornos, pesos).iloc[-1] == pytest.approx(1.0)


def _dois_indices():
    m1 = por_codigo("USA500")
    m2 = Mercado("OUTRO", "indices", "OUTRO-T", "yahoo", "^X", "USD")
    return {"USA500": m1, "OUTRO": m2}


def test_carteira_mira_a_volatilidade_alvo():
    mercados = _dois_indices()
    tabelas = {"USA500": _tabela(_aleatorios(1)), "OUTRO": _tabela(_aleatorios(2))}
    previsoes = {c: pd.Series(10.0, index=DATAS) for c in mercados}
    sem_custo = carteira.Custos(0.0, dict.fromkeys(carteira.MARGEM_DE_MANTER, 0.0))
    res = carteira.simular(mercados, tabelas, previsoes, sem_custo)
    vol = res.retorno.iloc[600:].std() * np.sqrt(256)
    assert vol == pytest.approx(0.12, abs=0.025)


def test_posicao_de_hoje_so_rende_amanha():
    mercados = {"USA500": por_codigo("USA500")}
    r = np.zeros(len(DATAS))
    r[1000] = 0.5  # salto no dia 1000
    tabelas = {"USA500": _tabela(r + _aleatorios(3, 0.005))}
    previsao = pd.Series(0.0, index=DATAS)
    previsao.iloc[1000:] = 10.0  # só passa a comprar NO dia do salto
    sem_custo = carteira.Custos(0.0, dict.fromkeys(carteira.MARGEM_DE_MANTER, 0.0))
    res = carteira.simular(mercados, tabelas, {"USA500": previsao}, sem_custo)
    assert res.retorno.loc[DATAS[1000]] == pytest.approx(0.0)  # não pegou o salto


def test_custos_e_margem_reduzem_o_retorno():
    mercados = _dois_indices()
    tabelas = {"USA500": _tabela(_aleatorios(1)), "OUTRO": _tabela(_aleatorios(2))}
    rng = np.random.default_rng(9)
    previsoes = {
        c: pd.Series(rng.uniform(-20, 20, len(DATAS)), index=DATAS) for c in mercados
    }
    sem_custo = carteira.Custos(0.0, dict.fromkeys(carteira.MARGEM_DE_MANTER, 0.0))
    base = carteira.simular(
        mercados, tabelas, previsoes, carteira.CUSTOS_BASE
    ).retorno.sum()
    limpo = carteira.simular(mercados, tabelas, previsoes, sem_custo).retorno.sum()
    estresse = carteira.simular(
        mercados, tabelas, previsoes, carteira.ESTRESSE_A
    ).retorno.sum()
    assert limpo > base > estresse


def test_moeda_emergente_custa_mais():
    custos = carteira.CUSTOS_BASE
    assert custos.por_lado(por_codigo("USDBRL")) > custos.por_lado(por_codigo("EURUSD"))
    assert carteira.ESTRESSE_B.margem(por_codigo("EURUSD")) == pytest.approx(0.025)
