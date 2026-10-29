"""Pesquisa 2, P5 parte 1: juros, dividendos e retornos dos CFDs (dados sintéticos, sem internet)."""

import numpy as np
import pandas as pd
import pytest

from trader.p2 import dividendos, juros, retornos
from trader.p2.mercados import por_codigo


# --- juros ----------------------------------------------------------------------------------
def test_juro_mensal_so_vale_a_partir_do_mes_seguinte():
    mensal = pd.Series([2.0, 3.0], index=pd.to_datetime(["2020-01-01", "2020-02-01"]))
    dias = pd.to_datetime(["2020-01-15", "2020-02-01", "2020-02-20", "2020-03-02"])
    diario = juros.mensal_para_diario(mensal, pd.DatetimeIndex(dias))
    assert np.isnan(diario.iloc[0])  # janeiro ainda não tem o valor de janeiro
    assert diario.iloc[1] == pytest.approx(0.02)  # o de janeiro vale em fevereiro
    assert diario.iloc[3] == pytest.approx(0.03)  # o de fevereiro vale em março


def test_juro_usa_o_bis_onde_a_ocde_falta_e_o_bis_vale_no_dia_seguinte():
    dias = pd.bdate_range("2001-12-27", periods=6)
    ocde = {
        "JPY": pd.Series([0.1], index=pd.to_datetime(["2001-12-01"]))
    }  # vale de 01/01/2002
    bis = pd.DataFrame({"JPY": [0.5] * 6}, index=dias)
    juro = juros.juro_da_moeda("JPY", dias, ocde, bis)
    assert np.isnan(juro.iloc[0])  # 27/12: o BIS do próprio dia ainda não vale
    assert juro.loc["2001-12-28"] == pytest.approx(0.005)  # BIS da véspera
    assert juro.loc["2002-01-01"] == pytest.approx(0.001)  # OCDE tem preferência


def test_euro_antes_de_existir_usa_a_alemanha_e_hong_kong_usa_o_dolar():
    dias = pd.bdate_range("1990-03-01", periods=3)
    ocde = {
        "DEM": pd.Series([8.0], index=pd.to_datetime(["1990-01-01"])),
        "USD": pd.Series([7.0], index=pd.to_datetime(["1990-01-01"])),
    }
    assert juros.juro_da_moeda("EUR", dias, ocde).iloc[0] == pytest.approx(0.08)
    assert juros.juro_da_moeda("HKD", dias, ocde).iloc[0] == pytest.approx(0.07)


# --- dividendos -----------------------------------------------------------------------------
def test_data_de_shiller_vira_mes_certo():
    tabela = pd.DataFrame(
        {
            "Date": [1871.01, 1871.1, 1871.12],
            "P": [4.0, 5.0, 5.0],
            "D": [0.2, 0.25, 0.3],
        }
    )
    rendimento = dividendos.rendimento_mensal(tabela)
    assert list(rendimento.index.month) == [1, 10, 12]
    assert rendimento.iloc[0] == pytest.approx(0.05)


def test_dividendo_do_sp_tem_defasagem_e_os_outros_sao_fixos():
    shiller = pd.Series(
        [0.04, 0.02], index=pd.to_datetime(["2020-01-01", "2020-02-01"])
    )
    dias = pd.DatetimeIndex(pd.to_datetime(["2020-02-15", "2020-03-02", "2020-04-01"]))
    sp = dividendos.rendimento_de_dividendos("USA500", dias, shiller)
    assert sp.iloc[0] == pytest.approx(0.025)  # nada conhecido ainda: fixo
    assert sp.iloc[1] == pytest.approx(0.04)  # o de janeiro só vale em março
    assert sp.iloc[2] == pytest.approx(0.02)
    outro = dividendos.rendimento_de_dividendos("GER40", dias, shiller)
    assert (outro == 0.025).all()


# --- retornos -------------------------------------------------------------------------------
def test_retorno_do_preco_entre_cotacoes_seguidas_e_sobre_o_preco_absoluto():
    precos = pd.Series(
        [10.0, 5.0, -5.0, 10.0], index=pd.bdate_range("2020-04-16", periods=4)
    )
    r = retornos.retorno_do_preco(precos)
    assert list(r.round(6)) == [-0.5, -2.0, 3.0]  # 10/|−5| − (−5)/|−5|... = +3


def test_buraco_nao_ganha_preco_inventado():
    precos = pd.Series(
        [100.0, 110.0], index=pd.to_datetime(["1995-01-02", "1995-01-16"])
    )
    r = retornos.retorno_do_preco(precos)
    assert len(r) == 1 and r.iloc[0] == pytest.approx(
        0.10
    )  # o movimento todo cai no dia com dado


def test_duracao_de_titulo_ao_par_de_10_anos():
    assert retornos.duracao_modificada(0.05) == pytest.approx(7.79, abs=0.01)


def test_titulo_ganha_quando_o_rendimento_cai():
    y = pd.Series([5.0, 4.9], index=pd.bdate_range("2020-01-02", periods=2))
    r = retornos.retorno_do_titulo(y)
    assert r.iloc[0] == pytest.approx(7.79 * 0.001, rel=0.01)


def _juro_fixo(valores):
    return lambda moeda, indice: pd.Series(valores[moeda], index=indice)


def test_carry_das_moedas_e_juro_da_base_menos_juro_da_cotacao():
    dias = pd.bdate_range("2020-01-02", periods=3)
    juro = _juro_fixo({"AUD": 0.05, "USD": 0.02})
    carry = retornos.carry_anual(por_codigo("AUDUSD"), dias, juro, lambda c, i: None)
    assert carry.to_numpy() == pytest.approx([0.03] * 3)


def test_carry_de_indice_e_metal():
    dias = pd.bdate_range("2020-01-02", periods=2)
    juro = _juro_fixo({"EUR": 0.01, "USD": 0.02})
    dividendo = lambda codigo, indice: pd.Series(0.025, index=indice)
    indice = retornos.carry_anual(por_codigo("GER40"), dias, juro, dividendo)
    ouro = retornos.carry_anual(por_codigo("GOLD"), dias, juro, dividendo)
    assert indice.iloc[0] == pytest.approx(0.015) and ouro.iloc[0] == pytest.approx(
        -0.02
    )


def test_montar_soma_o_carry_pelos_dias_corridos():
    precos = pd.Series(
        [1.0, 1.0, 1.01],
        index=pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"]),
    )
    juro = _juro_fixo({"EUR": 0.0365, "USD": 0.0})
    tabela = retornos.montar(por_codigo("EURUSD"), precos, juro, lambda c, i: None)
    assert tabela["total"].iloc[0] == pytest.approx(
        0.0001
    )  # 1 dia de carry, preço parado
    assert tabela["total"].iloc[1] == pytest.approx(
        0.01 + 0.0003
    )  # 3 dias (fim de semana)


def test_montar_titulo_usa_rendimento_da_vespera_no_carry():
    y = pd.Series([4.0, 4.0, 4.0], index=pd.bdate_range("2020-01-02", periods=3))
    juro = _juro_fixo({"USD": 0.01})
    tabela = retornos.montar(por_codigo("UST10"), y, juro, lambda c, i: None)
    assert tabela["preco"].abs().max() == 0
    assert tabela["carry_anual"].iloc[-1] == pytest.approx(0.03)
