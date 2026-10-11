"""Adaptador do MetaTrader 5: só leitura, recusa conta real, converte candles (com um MT5 falso)."""

import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from trader.mt5 import (
    ConexaoMT5,
    ContaRealRecusadaError,
    MT5IndisponivelError,
    SimboloIndisponivelError,
    transformar_candles,
)

RAIZ = Path(__file__).resolve().parent.parent
TIPO_RATES = np.dtype(
    [
        ("time", "i8"),
        ("open", "f8"),
        ("high", "f8"),
        ("low", "f8"),
        ("close", "f8"),
        ("tick_volume", "u8"),
        ("spread", "i4"),
        ("real_volume", "u8"),
    ]
)


def _rates(linhas):
    return np.array(linhas, dtype=TIPO_RATES)


class MT5Falso:
    """O mínimo do módulo `MetaTrader5` que o adaptador usa."""

    TIMEFRAME_D1 = 16408
    TIMEFRAME_H1 = 16385

    def __init__(
        self,
        modo=0,
        inicializa=True,
        conta=True,
        rates=None,
        simbolos=("EURUSD", "USDJPY"),
    ):
        self.modo, self.inicializa, self.tem_conta = modo, inicializa, conta
        self.rates, self.nomes = rates, simbolos
        self.encerrado = False
        self.selecionados = []

    def initialize(self):
        return self.inicializa

    def shutdown(self):
        self.encerrado = True

    def last_error(self):
        return (-10005, "IPC timeout")

    def account_info(self):
        if not self.tem_conta:
            return None
        return SimpleNamespace(
            server="MetaQuotes-Demo", currency="USD", trade_mode=self.modo, leverage=100
        )

    def symbols_get(self, group="*"):
        return [SimpleNamespace(name=n) for n in self.nomes]

    def symbol_info(self, simbolo):
        if simbolo not in self.nomes:
            return None
        return SimpleNamespace(
            description="Euro vs US Dollar",
            digits=5,
            trade_tick_size=0.00001,
            trade_tick_value=1.0,
            trade_contract_size=100000.0,
            volume_min=0.01,
            currency_base="EUR",
            currency_profit="USD",
            spread=12,
        )

    def symbol_select(self, simbolo, ligar):
        self.selecionados.append(simbolo)
        return simbolo in self.nomes

    def copy_rates_range(self, simbolo, timeframe, inicio, fim):
        return self.rates


DIA = 86_400
BASE = 1_700_000_000 - (1_700_000_000 % DIA)  # meia-noite
CANDLES = [
    (BASE, 1.10, 1.12, 1.09, 1.11, 1000, 12, 0),
    (BASE + DIA, 1.11, 1.13, 1.10, 1.12, 1100, 11, 0),
    (BASE + 2 * DIA, 1.12, 1.14, 1.11, 1.13, 900, 10, 50),
]
INICIO = datetime(2023, 1, 1, tzinfo=UTC)


# --- conta ---
def test_conta_demo_conecta_e_encerra():
    falso = MT5Falso(modo=0)
    with ConexaoMT5(falso) as mt5:
        assert mt5.conta.modo == "demo" and mt5.conta.servidor == "MetaQuotes-Demo"
        assert mt5.conta.alavancagem == 100
    assert falso.encerrado


@pytest.mark.parametrize("modo", [1, 2])
def test_conta_real_ou_de_concurso_e_recusada_e_a_conexao_fecha(modo):
    falso = MT5Falso(modo=modo)
    with pytest.raises(ContaRealRecusadaError), ConexaoMT5(falso):
        pass
    assert falso.encerrado  # não deixa o terminal preso


def test_conta_real_so_passa_se_pedirem_explicitamente():
    with ConexaoMT5(MT5Falso(modo=2), exigir_demo=False) as mt5:
        assert mt5.conta.modo == "real"


def test_terminal_que_nao_responde():
    with (
        pytest.raises(MT5IndisponivelError, match="IPC timeout"),
        ConexaoMT5(MT5Falso(inicializa=False)),
    ):
        pass


def test_terminal_sem_conta_logada():
    falso = MT5Falso(conta=False)
    with pytest.raises(MT5IndisponivelError, match="conta logada"), ConexaoMT5(falso):
        pass
    assert falso.encerrado


# --- leitura ---
def test_simbolos_vem_ordenados():
    with ConexaoMT5(MT5Falso(simbolos=("USDJPY", "EURUSD"))) as mt5:
        assert mt5.simbolos() == ["EURUSD", "USDJPY"]


def test_info_do_simbolo():
    with ConexaoMT5(MT5Falso()) as mt5:
        info = mt5.info_do_simbolo("EURUSD")
    assert info["digitos"] == 5 and info["tamanho_do_contrato"] == 100000.0
    assert info["moeda_base"] == "EUR" and info["spread_atual_em_pontos"] == 12


def test_simbolo_desconhecido():
    with ConexaoMT5(MT5Falso()) as mt5, pytest.raises(SimboloIndisponivelError):
        mt5.info_do_simbolo("XXXYYY")
    with ConexaoMT5(MT5Falso()) as mt5, pytest.raises(SimboloIndisponivelError):
        mt5.candles("XXXYYY", "D1", INICIO)


def test_candles_viram_dataframe_do_tickerlab():
    falso = MT5Falso(rates=_rates(CANDLES))
    with ConexaoMT5(falso) as mt5:
        candles = mt5.candles("EURUSD", "D1", INICIO)
    assert list(candles.columns) == ["Open", "High", "Low", "Close", "Volume", "Spread"]
    assert candles.index.name == "Date" and len(candles) == 3
    assert candles["Close"].tolist() == [1.11, 1.12, 1.13]
    assert falso.selecionados == ["EURUSD"]  # habilitou o símbolo antes de pedir


def test_volume_real_quando_existe_senao_o_de_ticks():
    candles = transformar_candles(_rates(CANDLES))
    assert candles["Volume"].tolist() == [1000, 1100, 50]


def test_candles_repetidos_e_fora_de_ordem_sao_arrumados():
    desordem = [CANDLES[2], CANDLES[0], CANDLES[1], CANDLES[1]]
    candles = transformar_candles(_rates(desordem))
    assert candles.index.is_monotonic_increasing and not candles.index.has_duplicates
    assert len(candles) == 3


def test_timeframe_desconhecido():
    with (
        ConexaoMT5(MT5Falso(rates=_rates(CANDLES))) as mt5,
        pytest.raises(ValueError, match="Timeframe"),
    ):
        mt5.candles("EURUSD", "D2", INICIO)


def test_sem_candles_no_periodo_vira_erro_claro():
    with (
        ConexaoMT5(MT5Falso(rates=None)) as mt5,
        pytest.raises(SimboloIndisponivelError, match="Sem candles"),
    ):
        mt5.candles("EURUSD", "D1", INICIO)


# --- a regra desta fase ---
def test_o_codigo_do_trader_nao_tem_nenhuma_chamada_de_ordem():
    """Nesta fase nada envia, altera ou cancela ordens. Se isto falhar, a regra foi quebrada."""
    proibidos = re.compile(
        r"order_send|order_check|order_calc|ORDER_TYPE|TRADE_ACTION|position_close|orders_cancel|positions_close"
    )
    arquivos = list((RAIZ / "trader").rglob("*.py"))
    assert any(
        a.parent.name == "interface" for a in arquivos
    )  # a interface também é varrida
    for arquivo in arquivos:
        assert not proibidos.search(arquivo.read_text(encoding="utf-8")), arquivo.name


def test_a_conexao_nao_tem_metodo_publico_de_ordem():
    publicos = [n for n in dir(ConexaoMT5) if not n.startswith("_")]
    assert not [n for n in publicos if "order" in n.lower() or "ordem" in n.lower()]
    assert pd.Timestamp  # (o pandas é só do formato dos candles)


def test_cotacao_le_compra_venda_e_hora():
    class ComTick(MT5Falso):
        def symbol_info_tick(self, simbolo):
            if simbolo != "EURUSD":
                return None
            return SimpleNamespace(bid=1.1000, ask=1.1002, time=1_700_000_000)

    with ConexaoMT5(ComTick()) as mt5:
        c = mt5.cotacao("EURUSD")
        assert c["compra"] == 1.1 and c["venda"] == 1.1002
        assert c["hora"] == pd.Timestamp(1_700_000_000, unit="s")
        with pytest.raises(SimboloIndisponivelError):
            mt5.cotacao("USDJPY")  # habilita, mas sem tick
