"""Moedas: converter os preços de ativos em dólar para reais.

Ações da B3, o Ibovespa e o próprio dólar (`USDBRL=X`, que já é cotado em reais) ficam como
estão. O resto (ações americanas, S&P 500, Bitcoin em `BTC-USD`) é cotado em dólar e pode ser
multiplicado pelo câmbio do dia.

Aproximações: o câmbio usado é o do fechamento do próprio dia para abertura, máxima, mínima e
fechamento; quando o câmbio não tem cotação no dia (feriado em um dos lados), vale a última
cotação conhecida, por no máximo 5 dias.
"""

import pandas as pd

from src.comparacao import _limpar_serie

TICKER_DO_DOLAR = "USDBRL=X"
COLUNAS_DE_PRECO = ["Open", "High", "Low", "Close"]
DIAS_MAXIMOS_SEM_CAMBIO = 5
MIN_DIAS_APOS_CONVERSAO = 30


def moeda_do_ticker(ticker: str) -> str:
    """ "BRL" para B3, Ibovespa e o dólar em reais; "USD" para o resto."""
    ticker = (ticker or "").strip().upper()
    if ticker.endswith(".SA") or ticker in ("^BVSP", TICKER_DO_DOLAR):
        return "BRL"
    return "USD"


def converter_para_reais(dados: pd.DataFrame, cambio: pd.Series) -> pd.DataFrame:
    """Multiplica os preços pelo dólar em reais. O volume não muda."""
    cambio = _limpar_serie(cambio)
    if cambio.empty:
        raise ValueError("Não há cotação do dólar para converter.")
    indice = pd.DatetimeIndex(dados.index).normalize()
    taxa = cambio.reindex(
        cambio.index.union(indice).sort_values(),
        method="ffill",
        limit=DIAS_MAXIMOS_SEM_CAMBIO,
    ).reindex(indice)
    taxa.index = dados.index
    convertido = dados.copy()
    for coluna in COLUNAS_DE_PRECO:
        if coluna in convertido.columns:
            convertido[coluna] = convertido[coluna] * taxa
    convertido = convertido.dropna(subset=["Close"])
    if len(convertido) < MIN_DIAS_APOS_CONVERSAO:
        raise ValueError("Poucos dias com câmbio para converter este ativo.")
    convertido.attrs = {**dados.attrs, "moeda": "BRL"}
    return convertido
