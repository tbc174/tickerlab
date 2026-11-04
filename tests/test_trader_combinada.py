"""Carteira combinada da ficha C-1 (pré-registro quant v0.2, seção 9).

Históricos artificiais no calendário real da B3: confere o teto, a banda, os pesos valendo de D+1,
o imposto sobre o lucro retirado, a cripto composta no pregão seguinte e que cortar o futuro não
muda o passado.
"""

from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from trader import calendario
from trader.custos_br import PADRAO
from trader.estrategias import combinada

DATAS = pd.DatetimeIndex(calendario.pregoes(date(2015, 1, 2), date(2018, 12, 28)))
CDI = pd.Series(0.0004, index=DATAS)


def _ruido(semente: int, escala: float, media: float = 0.0004) -> pd.Series:
    gerador = np.random.default_rng(semente)
    return pd.Series(media + escala * gerador.standard_normal(len(DATAS)), index=DATAS)


def _camadas() -> pd.DataFrame:
    return pd.DataFrame(
        {"a": _ruido(1, 0.01), "b": _ruido(2, 0.02), "c": _ruido(3, 0.005)}
    )


def test_pesos_inversos_da_sigma_somam_um():
    pesos = combinada.pesos_alvo({"a": 0.01, "b": 0.02, "c": 0.04}, teto=1.0)
    assert sum(pesos.values()) == pytest.approx(1)
    assert pesos["a"] == pytest.approx(2 * pesos["b"]) == pytest.approx(4 * pesos["c"])


def test_teto_repete_ate_ninguem_passar():
    pesos = combinada.pesos_alvo({"a": 0.001, "b": 0.002, "c": 0.02, "d": 0.02})
    assert pesos["a"] == pytest.approx(0.40)
    assert pesos["b"] == pytest.approx(0.40)
    assert pesos["c"] == pytest.approx(0.10) == pytest.approx(pesos["d"])
    assert sum(pesos.values()) == pytest.approx(1)


def test_todas_no_teto_deixam_a_sobra_no_cdi():
    pesos = combinada.pesos_alvo({"a": 0.01, "b": 0.03})
    assert pesos == {"a": 0.40, "b": 0.40}


def test_sigma_zero_vai_ao_teto():
    pesos = combinada.pesos_alvo({"caixa": 0.0, "a": 0.01, "b": 0.02, "c": 0.02})
    assert pesos["caixa"] == pytest.approx(0.40)
    assert sum(pesos.values()) == pytest.approx(1)
    assert pesos["a"] == pytest.approx(2 * pesos["b"])


def test_banda_de_vinte_por_cento_do_alvo():
    alvos = {"a": 0.5, "b": 0.5}
    assert not combinada.fora_da_banda({"a": 0.59, "b": 0.41}, alvos)
    assert combinada.fora_da_banda({"a": 0.61, "b": 0.39}, alvos)
    assert combinada.fora_da_banda({"a": 0.5}, {"a": 0.5, "b": 0.5})


def test_cripto_dos_dias_sem_pregao_entra_composta_no_pregao_seguinte():
    corridos = pd.date_range("2019-01-04", "2019-01-07")  # sexta a segunda
    retorno = pd.Series([0.01, 0.02, 0.03, 0.04], index=corridos)
    pregoes = pd.DatetimeIndex(calendario.pregoes(date(2019, 1, 2), date(2019, 1, 8)))
    composto = combinada.compor_no_pregao(retorno, pregoes)
    assert composto[pd.Timestamp("2019-01-04")] == pytest.approx(0.01)
    assert composto[pd.Timestamp("2019-01-07")] == pytest.approx(1.02 * 1.03 * 1.04 - 1)
    assert np.isnan(composto[pd.Timestamp("2019-01-08")])


def test_comeca_no_primeiro_mes_com_duas_camadas_e_pesos_valem_de_d_mais_1():
    camadas = _camadas()
    camadas.loc[: DATAS[400], "c"] = np.nan  # a "c" só entra mais tarde
    resultado = combinada.combinar(camadas, CDI)
    primeira = resultado.decisoes[0]
    assert (camadas.loc[:primeira, ["a", "b"]].notna().sum() >= 252).all()
    assert resultado.retorno.index[0] == DATAS[DATAS.get_loc(primeira) + 1]
    assert resultado.pesos["c"].iloc[0] == 0.0
    entrada_c = next(d for d in resultado.decisoes if d > DATAS[400 + 252])
    seguinte = DATAS[DATAS.get_loc(entrada_c) + 1]
    assert resultado.pesos.loc[seguinte, "c"] > 0
    assert resultado.pesos.loc[entrada_c, "c"] == 0.0


def test_retorno_e_a_soma_ponderada_mais_a_sobra_no_cdi():
    camadas = pd.DataFrame({"a": _ruido(1, 0.01), "b": _ruido(2, 0.03)})
    resultado = combinada.combinar(camadas, CDI)
    dia = resultado.retorno.index[10]
    pesos = resultado.pesos.loc[dia]
    esperado = (pesos * camadas.loc[dia]).sum() + (1 - pesos.sum()) * CDI[dia]
    assert pesos.sum() == pytest.approx(0.80, abs=0.05)  # as duas no teto de 40%
    assert resultado.retorno[dia] == pytest.approx(esperado)


def test_imposto_so_sobre_o_lucro_retirado():
    sobe = pd.Series(0.004, index=DATAS)
    sobe.iloc[::2] = -0.002  # σ positiva, sempre no lucro
    plano = pd.Series(0.0004, index=DATAS) + _ruido(5, 0.0001, media=0.0)
    camadas = pd.DataFrame({"sobe": sobe, "plano": plano, "terceira": _ruido(7, 0.004)})
    resultado = combinada.combinar(camadas, CDI)
    assert resultado.imposto.sum() > 0
    dias_com_imposto = resultado.imposto[resultado.imposto > 0].index
    assert set(dias_com_imposto) <= {
        DATAS[DATAS.get_loc(d) + 1] for d in resultado.decisoes
    }
    sem_imposto = combinada.combinar(camadas, CDI, custos=replace(PADRAO, ir_swing=0.0))
    assert sem_imposto.imposto.sum() == 0
    assert (1 + sem_imposto.retorno).prod() > (1 + resultado.retorno).prod()


def test_custo_da_troca_e_o_a_vista_sobre_o_valor_trocado():
    camadas = _camadas()
    resultado = combinada.combinar(camadas, CDI)
    primeiro_dia = resultado.retorno.index[0]
    # a primeira alocação compra 100% do patrimônio (as três somam 1 com o teto)
    assert resultado.custo[primeiro_dia] == pytest.approx(
        PADRAO.emolumentos_a_vista, rel=1e-6
    )


def test_cortar_o_futuro_nao_muda_o_passado():
    camadas = _camadas()
    inteiro = combinada.combinar(camadas, CDI)
    corte = DATAS[700]
    cortado = combinada.combinar(camadas.loc[:corte], CDI)
    comum = cortado.retorno.index[:-1]  # o último dia do corte não tem D+1 para decidir
    pd.testing.assert_series_equal(
        inteiro.retorno.loc[comum], cortado.retorno.loc[comum]
    )


def test_olhar_o_futuro_muda_os_pesos():
    camadas = _camadas()
    normal = combinada.combinar(camadas, CDI)
    trapaca = combinada.combinar(
        camadas, CDI, combinada.ParametrosC1(olhar_o_futuro=True)
    )
    assert not normal.pesos.equals(trapaca.pesos)


def test_reexecucao_identica():
    camadas = _camadas()
    um = combinada.combinar(camadas, CDI)
    dois = combinada.combinar(camadas, CDI)
    pd.testing.assert_series_equal(um.retorno, dois.retorno)


def test_serie_freada_troca_por_cdi_depois_da_queda():
    retorno = pd.Series(0.001, index=DATAS)
    retorno.iloc[300] = -0.5
    retorno.iloc[:100] = np.nan
    freada = combinada.serie_freada(retorno, CDI)
    assert freada.iloc[:100].isna().all()
    assert freada.iloc[301] == pytest.approx(CDI.iloc[301])
    assert freada.iloc[299] == pytest.approx(0.001)


def test_plato_mexe_vinte_por_cento_em_cada_parametro():
    vizinhas = combinada.variacoes_do_plato()
    assert {v.janela for v in vizinhas} == {202, 252, 302}
    assert {round(v.teto, 6) for v in vizinhas} == {0.32, 0.40, 0.48}
    assert {round(v.banda, 6) for v in vizinhas} == {0.16, 0.20, 0.24}
