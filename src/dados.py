"""Busca e preparo dos dados de mercado (Yahoo Finance)."""

import re

SUFIXO_B3 = ".SA"
PADRAO_B3 = re.compile(r"[A-Z]{4}\d{1,2}")  # 4 letras + 1 ou 2 números (PETR4, BOVA11)


def normalizar_ticker(ticker: str) -> str:
    """Arruma o que a pessoa digitou: sem espaços, maiúsculo e com .SA nos tickers da B3."""
    ticker = (ticker or "").strip().upper()

    if ticker.startswith("^") or ticker.endswith(SUFIXO_B3):
        return ticker  # índice ou já com .SA: não mexe

    if PADRAO_B3.fullmatch(ticker):
        return ticker + SUFIXO_B3  # B3 sem sufixo

    return ticker  # EUA, cripto e o resto: não mexe
