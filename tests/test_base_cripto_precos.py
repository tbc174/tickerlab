"""Preços diários do Bitcoin: Mercado Bitcoin (reais) e Kraken (dólar) (base de cripto, série 1,
PR 3). As respostas são cópias reduzidas das APIs, conferidas em 13/10/2026."""

import json
from datetime import UTC, date, datetime

import pytest

from base.cripto.precos import ler_kraken_arquivo, ler_kraken_rest, ler_mercado_bitcoin

# resposta real de api/v4/candles?symbol=BTC-BRL&resolution=1d de 01 a 05/01/2024
MERCADO_BITCOIN = json.dumps(
    {
        "t": [1704067200, 1704153600, 1704240000, 1704326400, 1704412800],
        "o": [
            "209254.31999999",
            "217289.59393099",
            "221733.00000000",
            "212668.28537785",
            "218150.00000000",
        ],
        "h": [
            "217350.00000000",
            "225945.00000000",
            "224323.00000000",
            "220780.09000000",
            "218802.99994997",
        ],
        "l": [
            "208852.49707343",
            "217289.59393099",
            "205139.99000000",
            "211627.78712556",
            "212014.93000000",
        ],
        "c": [
            "217268.60999999",
            "221651.00000000",
            "212697.47373642",
            "218122.79061029",
            "216718.90000000",
        ],
        "v": [
            "17.91206029",
            "94.16341266",
            "101.70723416",
            "53.14187735",
            "63.76658056",
        ],
    }
).encode()

# formato de 0/public/OHLC: [hora, abertura, máxima, mínima, fechamento, vwap, volume, negócios];
# `last` é o último candle fechado (o de hoje vem aberto)
KRAKEN_REST = json.dumps(
    {
        "error": [],
        "result": {
            "XXBTZUSD": [
                [
                    1791676800,
                    "80000.0",
                    "81000.0",
                    "79000.0",
                    "80500.0",
                    "80200.0",
                    "1000.5",
                    50000,
                ],
                [
                    1791763200,
                    "80500.0",
                    "82000.0",
                    "80100.0",
                    "81737.2",
                    "81000.0",
                    "900.25",
                    45000,
                ],
                [
                    1791849600,
                    "81737.2",
                    "84053.1",
                    "80951.2",
                    "83231.7",
                    "82764.6",
                    "10.0",
                    600,
                ],
            ],
            "last": 1791763200,
        },
    }
).encode()

# arquivo OHLCVT da Kraken (CSV sem cabeçalho): hora, abertura, máxima, mínima, fechamento, volume,
# negócios
KRAKEN_ARQUIVO = b"1381017600,122.0,122.0,122.0,122.0,0.1,1\n1381104000,123.6,123.6,122.0,123.0,2.5,7\n"

AGORA = datetime(2024, 1, 5, 12, tzinfo=UTC)


def test_mercado_bitcoin_em_reais_sem_o_candle_aberto():
    tabela = ler_mercado_bitcoin(MERCADO_BITCOIN, AGORA)

    assert tabela["dia"].tolist() == [date(2024, 1, d) for d in (1, 2, 3, 4)]
    assert (tabela["moeda"] == "BRL").all()
    assert tabela.iloc[0]["fechamento"] == pytest.approx(217268.60999999)
    assert tabela.iloc[0]["volume"] == pytest.approx(17.91206029)


def test_candle_so_vale_depois_da_meia_noite_utc_que_o_fecha():
    tabela = ler_mercado_bitcoin(MERCADO_BITCOIN, AGORA)

    assert tabela.iloc[0]["divulgado_em"] == datetime(2024, 1, 2, tzinfo=UTC)


def test_kraken_rest_usa_so_ate_o_ultimo_candle_fechado():
    tabela = ler_kraken_rest(KRAKEN_REST, datetime(2026, 10, 13, 12, tzinfo=UTC))

    assert tabela["dia"].tolist() == [date(2026, 10, 11), date(2026, 10, 12)]
    assert (tabela["moeda"] == "USD").all()
    assert tabela.iloc[1]["fechamento"] == pytest.approx(81737.2)
    assert tabela.iloc[1]["negocios"] == 45_000


def test_kraken_rest_com_erro_para():
    with pytest.raises(ValueError, match="EGeneral"):
        ler_kraken_rest(b'{"error": ["EGeneral:Internal error"], "result": {}}', AGORA)


def test_kraken_arquivo_historico():
    tabela = ler_kraken_arquivo(KRAKEN_ARQUIVO, AGORA)

    assert tabela["dia"].tolist() == [date(2013, 10, 6), date(2013, 10, 7)]
    assert tabela.iloc[1]["maxima"] == pytest.approx(123.6)
    assert tabela.iloc[1]["negocios"] == 7


def test_candle_aberto_fica_de_fora_tambem_no_arquivo():
    hoje_aberto = b"1704412800,1,1,1,1,1,1\n"

    assert ler_kraken_arquivo(hoje_aberto, AGORA).empty
