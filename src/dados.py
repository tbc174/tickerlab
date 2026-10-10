"""Busca e preparo dos dados de mercado (Yahoo Finance)."""

import re

import pandas as pd
import yfinance as yf

SUFIXO_B3 = ".SA"
PADRAO_B3 = re.compile(r"[A-Z]{4}\d{1,2}")  # 4 letras + 1 ou 2 números (PETR4, BOVA11)
PERIODOS_VALIDOS = ["6mo", "1y", "2y", "5y"]


class DadosIndisponiveisError(Exception):
    """Não foi possível obter dados para o ticker pedido."""


def normalizar_ticker(ticker: str) -> str:
    """Arruma o que a pessoa digitou: sem espaços, maiúsculo e com .SA nos tickers da B3."""
    ticker = (ticker or "").strip().upper()

    if ticker.startswith("^") or ticker.endswith(SUFIXO_B3):
        return ticker  # índice ou já com .SA: não mexe

    if PADRAO_B3.fullmatch(ticker):
        return ticker + SUFIXO_B3  # B3 sem sufixo

    return ticker  # EUA, cripto e o resto: não mexe


def baixar_dados(ticker: str, periodo: str = "2y") -> pd.DataFrame:
    """Baixa o histórico diário do ticker no Yahoo Finance, já com colunas simples."""
    ticker = normalizar_ticker(ticker)

    if periodo not in PERIODOS_VALIDOS:
        raise ValueError(
            f"Período inválido: {periodo}. Use um destes: {PERIODOS_VALIDOS}."
        )

    if not ticker:
        raise DadosIndisponiveisError("Digite um ticker, por exemplo PETR4 ou AAPL.")

    dados = yf.download(ticker, period=periodo, auto_adjust=True, progress=False)

    if dados is None or dados.empty:
        raise DadosIndisponiveisError(
            f"Não encontrei dados para {ticker}. Confira o ticker (B3 termina em .SA)."
        )

    dados.columns = dados.columns.droplevel("Ticker")  # tira o nível do ticker
    return dados
