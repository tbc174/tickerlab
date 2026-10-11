"""Conexão com o MetaTrader 5, SOMENTE LEITURA.

Lê dados (símbolos, candles, informações do ativo e da conta). Não existe aqui nenhuma função de
enviar, alterar ou cancelar ordens, e a conexão recusa conta real por padrão. O envio de ordens
só será escrito na fase de paper trading (conta demo) e depois dos controles de risco.

O terminal MetaTrader 5 precisa estar instalado e aberto, com uma conta (demo) logada.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from types import ModuleType
from typing import Any, Protocol, Self

import pandas as pd

TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1")
COLUNAS = ["Open", "High", "Low", "Close", "Volume", "Spread"]
MODOS_DA_CONTA = {0: "demo", 1: "concurso", 2: "real"}


class ModuloMT5(Protocol):
    """O que o adaptador usa do módulo `MetaTrader5` (permite trocar por um falso nos testes)."""

    def __getattr__(self, nome: str) -> Any: ...  # noqa: ANN401


class MT5IndisponivelError(RuntimeError):
    """O pacote não está instalado ou o terminal não respondeu."""


class ContaRealRecusadaError(RuntimeError):
    """A conta logada no terminal não é demo e a conexão exige demo."""


class SimboloIndisponivelError(RuntimeError):
    """O corretor não tem o símbolo, ou ele não pôde ser habilitado."""


@dataclass(frozen=True)
class InfoDaConta:
    servidor: str
    moeda: str
    modo: str  # "demo", "concurso" ou "real"
    alavancagem: int


def _importar_modulo() -> ModuleType:
    try:
        import MetaTrader5
    except ImportError as erro:
        raise MT5IndisponivelError(
            "O pacote MetaTrader5 não está instalado (ele só funciona no Windows): "
            "python -m pip install -r requirements-trader.txt"
        ) from erro
    return MetaTrader5


class ConexaoMT5:
    """Uso: `with ConexaoMT5() as mt5: mt5.candles("EURUSD", "D1", inicio)`."""

    def __init__(
        self, modulo: ModuloMT5 | None = None, exigir_demo: bool = True
    ) -> None:
        self._mt5 = modulo if modulo is not None else _importar_modulo()
        self._exigir_demo = exigir_demo
        self.conta: InfoDaConta | None = None

    # --- ciclo de vida ---------------------------------------------------------------------
    def __enter__(self) -> Self:
        if not self._mt5.initialize():
            raise MT5IndisponivelError(
                f"Não consegui falar com o terminal MetaTrader 5: {self._mt5.last_error()}. "
                "Ele está aberto e com uma conta logada?"
            )
        try:
            self.conta = self._ler_conta()
            if self._exigir_demo and self.conta.modo != "demo":
                raise ContaRealRecusadaError(
                    f"A conta logada é '{self.conta.modo}'. Entre numa conta DEMO no terminal."
                )
        except Exception:
            self._mt5.shutdown()
            raise
        return self

    def __exit__(self, *_: object) -> None:
        self._mt5.shutdown()

    def _ler_conta(self) -> InfoDaConta:
        info = self._mt5.account_info()
        if info is None:
            raise MT5IndisponivelError(
                "O terminal não tem uma conta logada (faça login no MetaTrader 5)."
            )
        return InfoDaConta(
            servidor=str(info.server),
            moeda=str(info.currency),
            modo=MODOS_DA_CONTA.get(int(info.trade_mode), "desconhecido"),
            alavancagem=int(info.leverage),
        )

    # --- leitura ---------------------------------------------------------------------------
    def simbolos(self, filtro: str = "*") -> list[str]:
        """Nomes dos símbolos que o corretor oferece (`filtro` aceita curingas: "*USD*")."""
        encontrados = self._mt5.symbols_get(group=filtro)
        return sorted(s.name for s in encontrados) if encontrados else []

    def info_do_simbolo(self, simbolo: str) -> dict[str, Any]:
        """Dados do contrato: casas decimais, tamanho do tick, tamanho do contrato, moeda."""
        info = self._mt5.symbol_info(simbolo)
        if info is None:
            raise SimboloIndisponivelError(
                f"Símbolo desconhecido neste corretor: {simbolo}"
            )
        return {
            "simbolo": simbolo,
            "descricao": str(info.description),
            "digitos": int(info.digits),
            "tamanho_do_tick": float(info.trade_tick_size),
            "valor_do_tick": float(info.trade_tick_value),
            "tamanho_do_contrato": float(info.trade_contract_size),
            "volume_minimo": float(info.volume_min),
            "moeda_base": str(info.currency_base),
            "moeda_de_lucro": str(info.currency_profit),
            "spread_atual_em_pontos": int(info.spread),
        }

    def cotacao(self, simbolo: str) -> dict[str, Any]:
        """Último preço de compra e de venda e a hora (só leitura), para a lista de observação."""
        if not self._mt5.symbol_select(simbolo, True):
            raise SimboloIndisponivelError(
                f"Não consegui habilitar o símbolo {simbolo}."
            )
        tick = self._mt5.symbol_info_tick(simbolo)
        if tick is None:
            raise SimboloIndisponivelError(
                f"Sem cotação de {simbolo}: {self._mt5.last_error()}"
            )
        return {
            "simbolo": simbolo,
            "compra": float(tick.bid),
            "venda": float(tick.ask),
            "hora": pd.Timestamp(int(tick.time), unit="s"),
        }

    def candles(
        self,
        simbolo: str,
        timeframe: str,
        inicio: datetime,
        fim: datetime | None = None,
    ) -> pd.DataFrame:
        """Candles do período como DataFrame (Open, High, Low, Close, Volume, Spread).

        O índice é a hora de abertura de cada candle, no relógio do servidor do corretor
        (o MT5 a entrega como se fosse UTC; para candles diários isso não importa).
        """
        if timeframe not in TIMEFRAMES:
            raise ValueError(
                f"Timeframe desconhecido: {timeframe}. Use um destes: {TIMEFRAMES}."
            )
        if not self._mt5.symbol_select(simbolo, True):
            raise SimboloIndisponivelError(
                f"Não consegui habilitar o símbolo {simbolo}."
            )
        fim = fim or datetime.now(UTC)
        constante = getattr(self._mt5, f"TIMEFRAME_{timeframe}")
        bruto = self._mt5.copy_rates_range(simbolo, constante, inicio, fim)
        if bruto is None or len(bruto) == 0:
            raise SimboloIndisponivelError(
                f"Sem candles de {simbolo} ({timeframe}) nesse período: {self._mt5.last_error()}"
            )
        return transformar_candles(bruto)


def transformar_candles(bruto: object) -> pd.DataFrame:
    """Converte o formato do MT5 (matriz com campo `time`, `open`...) para o do TickerLab."""
    tabela = pd.DataFrame(bruto)
    volume = tabela["real_volume"].where(
        tabela["real_volume"] > 0, tabela["tick_volume"]
    )
    candles = pd.DataFrame(
        {
            "Open": tabela["open"],
            "High": tabela["high"],
            "Low": tabela["low"],
            "Close": tabela["close"],
            "Volume": volume,
            "Spread": tabela["spread"],
        }
    )
    candles.index = pd.to_datetime(tabela["time"], unit="s")
    candles.index.name = "Date"
    candles = candles[~candles.index.duplicated(keep="last")].sort_index()
    return candles[COLUNAS]
