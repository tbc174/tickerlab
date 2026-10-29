"""Pesquisa 2, P5 parte 2: as regras (dados sintéticos; nenhum dado real)."""

import numpy as np
import pandas as pd
import pytest

from trader.p2 import regras
from trader.p2.mercados import por_codigo


def _retornos(media=0.0, desvio=0.01, n=1500, semente=1):
    rng = np.random.default_rng(semente)
    return pd.Series(
        rng.normal(media, desvio, n), index=pd.bdate_range("2000-01-03", periods=n)
    )


def test_t1_fica_comprado_numa_alta_e_vendido_numa_queda():
    assert regras.t1(_retornos(0.002)).iloc[-1] > 5
    assert regras.t1(_retornos(-0.002)).iloc[-1] < -5


def test_previsoes_respeitam_o_limite_de_20():
    forte = regras.t1(_retornos(0.02, 0.001))
    assert forte.max() <= 20 and forte.dropna().iloc[-1] == 20


def test_t1_em_ruido_tem_media_absoluta_perto_de_10():
    """As escalas publicadas valem para preços que oscilam ao acaso (tolerância larga)."""
    ruido = regras.t1(_retornos(0.0, 0.01, n=6000)).dropna()
    assert 5 < ruido.abs().mean() < 16


def test_t1_nao_depende_do_tamanho_das_oscilacoes():
    calmo = regras.t1(_retornos(0.0005, 0.005, semente=3))
    agitado = regras.t1(_retornos(0.0005 * 4, 0.02, semente=3))
    pd.testing.assert_series_equal(calmo.round(6), agitado.round(6), check_names=False)


def test_t1_nao_olha_o_futuro():
    r = _retornos(0.0, 0.01, n=800)
    inteira = regras.t1(r)
    cortada = regras.t1(r.iloc[:600])
    pd.testing.assert_series_equal(inteira.iloc[:600], cortada)


def test_t1_espera_256_dias_de_aquecimento():
    sinal = regras.t1(_retornos(0.001))
    assert sinal.iloc[:255].isna().all() and sinal.iloc[300:].notna().all()


def test_c1_segue_o_sinal_do_carry_e_respeita_o_limite():
    r = _retornos(0.0, 0.006)
    positivo = regras.c1(r, pd.Series(0.03, index=r.index))
    negativo = regras.c1(r, pd.Series(-0.03, index=r.index))
    assert positivo.dropna().gt(0).all() and negativo.dropna().lt(0).all()
    assert positivo.max() <= 20
    assert positivo.iloc[:89].isna().all()  # média de 90 dias


def test_k2_combina_onde_ha_carry_e_e_t1_puro_nos_metais():
    r = _retornos(0.001)
    carry = pd.Series(0.02, index=r.index)
    ouro = regras.k2(por_codigo("GOLD"), r, carry)
    pd.testing.assert_series_equal(ouro, regras.t1(r))
    aud = regras.k2(por_codigo("AUDUSD"), r, carry)
    esperado = (0.6 * regras.t1(r) + 0.4 * regras.c1(r, carry)) * 1.2
    pd.testing.assert_series_equal(aud, esperado.clip(-20, 20))


def test_b0_comprado_em_indices_e_neutro_em_moedas():
    indice = pd.bdate_range("2020-01-02", periods=3)
    assert (regras.b0(por_codigo("USA500"), indice) == 10).all()
    assert (regras.b0(por_codigo("EURUSD"), indice) == 0).all()


def test_configuracao_desconhecida_e_recusada():
    tabela = pd.DataFrame({"preco": [0.0], "carry_anual": [0.0]})
    with pytest.raises(ValueError):
        regras.previsao("K9", por_codigo("USA500"), tabela)
