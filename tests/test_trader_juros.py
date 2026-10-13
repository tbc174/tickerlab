"""Taxas básicas (BIS), carry de cada ativo e swap no tempo."""

import numpy as np
import pandas as pd
import pytest

from trader import juros
from trader.backtest import Custos, executar_backtest
from trader.custos import MARGEM_DO_SWAP, custos_do_ativo
from trader.universo import UNIVERSO, Ativo

CSV_DO_BIS = (
    "FREQ,REF_AREA,UNIT_MEASURE,TIME_PERIOD,OBS_VALUE\n"
    "D,US,368,2024-01-01,5.0\n"
    "D,US,368,2024-01-03,4.0\n"
    "D,BR,368,2024-01-01,12.0\n"
    "D,BR,368,2024-01-02,\n"
    "D,JP,368,2024-01-01,-0.1\n"
    "D,XM,368,2024-01-01,4.0\n"
)


@pytest.fixture
def tabela():
    return juros.ler_csv_do_bis(CSV_DO_BIS)


def _ativo(simbolo):
    return next(a for a in UNIVERSO if a.simbolo == simbolo)


def test_le_o_csv_do_bis_com_moedas_nas_colunas(tabela):
    assert set(tabela.columns) == {"USD", "BRL", "JPY", "EUR"}
    assert tabela.loc["2024-01-01", "USD"] == 5.0
    assert pd.Timestamp("2024-01-02") not in tabela.index  # dia só com valor vazio sai


def test_pais_desconhecido_e_recusado():
    with pytest.raises(ValueError, match="inesperado"):
        juros.ler_csv_do_bis(CSV_DO_BIS + "D,ZZ,368,2024-01-01,1.0\n")


def test_taxa_usa_o_valor_da_vespera_e_repete_nos_buracos(tabela):
    indice = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
    usd = juros.taxa(tabela, "USD", indice)
    # 01/01 ainda não conhece nada; 02 e 03 usam o 5% de 01/01; 04 já usa o 4% de 03/01
    assert np.isnan(usd.iloc[0])
    assert usd.iloc[1:].tolist() == pytest.approx([0.05, 0.05, 0.04])
    brl = juros.taxa(tabela, "BRL", indice)
    assert brl.iloc[3] == pytest.approx(0.12)  # buraco em 02/01 repete o 12%
    with pytest.raises(KeyError):
        juros.taxa(tabela, "XYZ", indice)


def test_moedas_do_par():
    assert juros.moedas_do_par("EURUSD") == ("EUR", "USD")
    assert juros.moedas_do_par("BRL=X") == ("USD", "BRL")
    with pytest.raises(ValueError):
        juros.moedas_do_par("^GSPC")


def test_sinais_do_carry(tabela):
    indice = pd.to_datetime(["2024-01-02"])
    # comprar USDJPY: recebe o juro do dólar e paga o do iene
    assert juros.carry_anual(_ativo("USDJPY"), indice, tabela).iloc[0] == pytest.approx(
        0.051
    )
    # comprar dólar contra real (BRL=X): paga a diferença para a Selic
    assert juros.carry_anual(_ativo("BRL=X"), indice, tabela).iloc[0] == pytest.approx(
        -0.07
    )
    # ouro: comprar é tomar dólar emprestado
    assert juros.carry_anual(_ativo("XAUUSD"), indice, tabela).iloc[0] == pytest.approx(
        -0.05
    )
    # ação da B3 à vista: financiada à Selic
    assert juros.carry_anual(_ativo("PETR4.SA"), indice, tabela).iloc[
        0
    ] == pytest.approx(-0.12)
    assert juros.carry_anual(_ativo("BTC-USD"), indice, tabela).iloc[
        0
    ] == pytest.approx(-0.05)
    assert juros.carry_anual(_ativo("^GDAXI"), indice, tabela).iloc[0] == pytest.approx(
        -0.04
    )


def test_todo_ativo_operavel_tem_moeda_de_financiamento():
    tabela = pd.DataFrame(
        0.01,
        index=pd.to_datetime(["2024-01-01"]),
        columns=list(juros.PAIS_PARA_MOEDA.values()),
    )
    indice = pd.to_datetime(["2024-01-02"])
    for ativo in UNIVERSO:
        if ativo.papel == "operar":
            juros.carry_anual(ativo, indice, tabela)  # nenhum KeyError
    with pytest.raises(KeyError, match="moeda"):
        juros.carry_anual(Ativo("XYZ", "yfinance", "indices"), indice, tabela)


def test_swap_com_taxas_segue_o_carry_e_a_margem(tabela):
    indice = pd.to_datetime(["2024-01-02", "2024-01-03"])
    c = custos_do_ativo(_ativo("USDJPY"), taxas=tabela, indice=indice)
    comprado, vendido = c.swaps(indice)
    assert comprado.iloc[0] == pytest.approx(0.051 - MARGEM_DO_SWAP)
    assert vendido.iloc[0] == pytest.approx(-0.051 - MARGEM_DO_SWAP)
    estresse = custos_do_ativo(_ativo("USDJPY"), 2, taxas=tabela, indice=indice)
    assert estresse.swaps(indice)[0].iloc[0] == pytest.approx(
        0.051 - 2 * MARGEM_DO_SWAP
    )


def test_sem_taxas_continua_o_carregamento_simetrico_da_v01():
    c = custos_do_ativo(_ativo("USDJPY"))
    assert c.swap_comprado_anual == c.swap_vendido_anual == -0.02


def test_motor_aplica_swap_que_varia_no_tempo():
    indice = pd.date_range("2024-01-01", periods=3, freq="D")
    p = pd.Series(100.0, index=indice)
    swap = pd.Series([0.365, 0.365, 0.73], index=indice)
    r = executar_backtest(
        p,
        pd.Series(1.0, index=indice),
        Custos(swap_comprado_anual=swap, swap_vendido_anual=0.0),
    )
    assert r.swap.tolist() == pytest.approx([0.0, 0.001, 0.002])
