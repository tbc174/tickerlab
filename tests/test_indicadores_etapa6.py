"""Indicadores novos da etapa 6 do Research: CVaR, tracking error, Information Ratio, ADX, OBV,
volume relativo e as barras semanais (sem olhar o futuro)."""

import numpy as np
import pandas as pd
import pytest

from src import analise
from src import indicadores as ind
from src.presets import Preset, resolver


@pytest.fixture(scope="module")
def petr4():
    dados = pd.read_csv("dados_de_exemplo/PETR4.SA.csv", index_col=0, parse_dates=True)
    dados.attrs["origem"] = "exemplo"
    return dados


def _barras(precos, volume=1_000_000):
    indice = pd.bdate_range("2026-01-05", periods=len(precos))
    fechamento = pd.Series(precos, index=indice, dtype=float)
    return pd.DataFrame(
        {
            "Open": fechamento.shift(1).fillna(fechamento.iloc[0]),
            "High": fechamento * 1.01,
            "Low": fechamento * 0.99,
            "Close": fechamento,
            "Volume": volume,
        }
    )


def test_cvar_e_a_media_dos_dias_piores_que_o_var():
    retorno = pd.Series([-0.10, -0.05, -0.01, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06])
    var = ind.calcular_var_historico(retorno, 0.80)
    cvar = ind.calcular_cvar_historico(retorno, 0.80)
    assert cvar <= var
    assert cvar == pytest.approx(retorno[retorno <= var].mean())
    assert np.isnan(ind.calcular_cvar_historico(pd.Series(dtype=float)))


def test_tracking_error_e_information_ratio():
    indice = pd.bdate_range("2026-01-05", periods=250)
    referencia = pd.Series(np.random.default_rng(1).normal(0, 0.01, 250), index=indice)
    assert ind.calcular_tracking_error(referencia, referencia) == pytest.approx(0)
    acima = (
        referencia
        + 0.001
        + pd.Series(np.random.default_rng(2).normal(0, 0.002, 250), index=indice)
    )
    assert ind.calcular_tracking_error(acima, referencia) > 0
    assert (
        ind.calcular_information_ratio(acima, referencia) > 0
    )  # rendeu acima do índice
    assert ind.calcular_information_ratio(
        referencia - 0.001, referencia
    ) < 0 or np.isnan(
        ind.calcular_information_ratio(referencia - 0.001, referencia)
    )  # diferença constante: tracking error zero, IR indefinido


def test_adx_alto_na_tendencia_e_baixo_andando_de_lado():
    subida = ind.calcular_adx(_barras(np.linspace(10, 30, 120)), 14)
    assert subida["adx"].iloc[-1] > 25
    assert subida["mais_di"].iloc[-1] > subida["menos_di"].iloc[-1]
    vai_e_volta = ind.calcular_adx(_barras(10 + np.sin(np.arange(120))), 14)
    assert vai_e_volta["adx"].iloc[-1] < subida["adx"].iloc[-1]
    assert subida["adx"].iloc[:14].isna().all()  # sem histórico, vazio


def test_obv_e_volume_relativo():
    dados = _barras([10, 11, 10, 12], volume=[100, 200, 300, 400])
    assert list(ind.calcular_obv(dados)) == [0, 200, -100, 300]
    constante = _barras(np.linspace(10, 20, 30))
    assert ind.calcular_volume_relativo(constante, 20).iloc[-1] == pytest.approx(1.0)


def test_barras_semanais_com_a_data_do_ultimo_pregao():
    dias = pd.DatetimeIndex(["2026-01-05", "2026-01-06", "2026-01-08", "2026-01-12"])
    dados = pd.DataFrame(
        {"Open": [1, 2, 3, 4], "High": [5, 6, 7, 8], "Low": [0.5, 1, 2, 3],
         "Close": [2, 3, 4, 5], "Volume": [10, 20, 30, 40]},
        index=dias,
    )  # fmt: skip
    semanas = ind.para_semanal(dados)
    assert list(semanas.index) == [
        pd.Timestamp("2026-01-08"),
        pd.Timestamp("2026-01-12"),
    ]
    primeira = semanas.iloc[0]
    assert (primeira["Open"], primeira["High"], primeira["Low"]) == (1, 7, 0.5)
    assert (primeira["Close"], primeira["Volume"]) == (4, 60)


def test_fachada_ganha_as_metricas_novas(petr4):
    a = analise.analisar_ativo("PETR4.SA", petr4)
    assert a["cvar"].valor <= a["var"].valor
    assert a["adx"].disponivel and a["volume_relativo"].disponivel
    assert not a["tracking_error"].disponivel  # sem índice de referência, com motivo
    assert "índice de referência" in a["tracking_error"].motivo


def test_tecnica_semanal_conta_em_semanas(petr4):
    semanal = resolver([Preset(escopo="global", parametros={"tecnica.periodicidade": "semanal",
                                                            "tecnica.media_lenta": 300})])  # fmt: skip
    a = analise.analisar_ativo("PETR4.SA", petr4, semanal)
    diaria = analise.analisar_ativo("PETR4.SA", petr4)
    assert a["rsi"].valor != diaria["rsi"].valor  # RSI das barras semanais
    assert "semanas" in a["media_lenta"].motivo  # ~260 semanas não bastam para 300
    assert (
        a["retorno_total"].valor == diaria["retorno_total"].valor
    )  # o risco segue diário
