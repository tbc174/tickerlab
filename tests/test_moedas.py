"""Testes de src/moedas.py e da limpeza de fins de semana em src/dados.py."""

import pandas as pd
import pytest

from src.dados import manter_apenas_dias_uteis
from src.exemplos import carregar_exemplo
from src.moedas import converter_para_reais, moeda_do_ticker


def _dados(dias=40):
    indice = pd.bdate_range("2026-01-05", periods=dias)
    return pd.DataFrame(
        {
            "Open": 10.0,
            "High": 12.0,
            "Low": 9.0,
            "Close": 11.0,
            "Volume": 1000,
        },
        index=indice,
    )


@pytest.mark.parametrize(
    ("ticker", "moeda"),
    [
        ("PETR4.SA", "BRL"),
        ("petr4.sa", "BRL"),
        ("^BVSP", "BRL"),
        ("USDBRL=X", "BRL"),
        ("AAPL", "USD"),
        ("^GSPC", "USD"),
        ("BTC-USD", "USD"),
    ],
)
def test_moeda_do_ticker(ticker, moeda):
    assert moeda_do_ticker(ticker) == moeda


def test_conversao_multiplica_os_precos_e_deixa_o_volume():
    dados = _dados()
    cambio = pd.Series(5.0, index=dados.index)
    convertido = converter_para_reais(dados, cambio)
    assert (convertido["Close"] == 55.0).all()
    assert (convertido["Open"] == 50.0).all() and (convertido["High"] == 60.0).all()
    assert (convertido["Volume"] == 1000).all()
    assert convertido.attrs["moeda"] == "BRL"
    assert dados["Close"].iloc[0] == 11.0  # o original não muda


def test_cambio_variavel_entra_no_retorno():
    dados = _dados()
    cambio = pd.Series(5.0, index=dados.index)
    cambio.iloc[1:] = 5.5  # o dólar sobe 10%
    convertido = converter_para_reais(dados, cambio)
    retorno = convertido["Close"].pct_change().iloc[1]
    assert retorno == pytest.approx(0.10)  # preço em dólar parado, ganho só do câmbio


def test_dia_sem_cambio_usa_a_ultima_cotacao_por_ate_5_dias():
    dados = _dados()
    cambio = pd.Series(5.0, index=dados.index).drop(dados.index[10])
    convertido = converter_para_reais(dados, cambio)
    assert convertido["Close"].loc[dados.index[10]] == 55.0
    # câmbio que some por muito tempo: os dias sem cotação saem
    longo = pd.Series(5.0, index=dados.index).drop(dados.index[10:20])
    sem = converter_para_reais(dados, longo)
    assert dados.index[19] not in sem.index and dados.index[12] in sem.index


def test_conversao_valida_entradas():
    dados = _dados()
    with pytest.raises(ValueError, match="cotação do dólar"):
        converter_para_reais(dados, pd.Series(dtype=float))
    with pytest.raises(ValueError, match="Poucos dias"):
        converter_para_reais(dados, pd.Series(5.0, index=dados.index[:5]))


def test_fins_de_semana_saem_sem_perder_o_retorno():
    indice = pd.date_range("2026-01-02", "2026-01-06")  # sex, sáb, dom, seg, ter
    dados = pd.DataFrame({"Close": [100.0, 101.0, 102.0, 110.0, 121.0]}, index=indice)
    dados.attrs["origem"] = "exemplo"
    uteis = manter_apenas_dias_uteis(dados)
    assert list(uteis.index.dayofweek) == [4, 0, 1]
    assert uteis["Close"].pct_change().iloc[1] == pytest.approx(
        0.10
    )  # sexta -> segunda
    assert uteis.attrs["origem"] == "exemplo"


def test_bitcoin_de_exemplo_vem_so_com_dias_uteis_e_ao_ritmo_de_252_por_ano():
    btc = carregar_exemplo("BTC-USD", "5y")
    assert (btc.index.dayofweek < 5).all()
    assert 255 < len(btc) / 5 < 265


def test_dolar_de_exemplo_esta_em_reais_por_dolar():
    dolar = carregar_exemplo("USDBRL=X", "5y")["Close"]
    assert 3 < dolar.min() and dolar.max() < 10
