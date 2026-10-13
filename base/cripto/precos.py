"""Preços diários do Bitcoin: Mercado Bitcoin em reais e Kraken em dólar (base de cripto, PR 3).

As duas corretoras não publicam termo sobre o uso dos dados de mercado; o uso segue a decisão do
autor (ADR 0045), **só interno, nunca exportado**. Todas as leituras devolvem a mesma tabela: `dia`
(UTC), `abertura`, `maxima`, `minima`, `fechamento`, `volume` (em BTC), `negocios` (quando a fonte
informa), `moeda` e `divulgado_em`.

**Sem olhar o futuro:** o candle de um dia só existe depois da meia-noite UTC que o fecha
(`divulgado_em`); o candle ainda aberto (o de hoje) nunca entra.
"""

import io
import json
from datetime import datetime

import pandas as pd

UM_DIA = pd.Timedelta(days=1)
COLUNAS_DE_PRECO = ["abertura", "maxima", "minima", "fechamento", "volume"]
# arquivo OHLCVT da Kraken: CSV sem cabeçalho
COLUNAS_DO_ARQUIVO_DA_KRAKEN = ["hora", *COLUNAS_DE_PRECO, "negocios"]
# 0/public/OHLC: o 6º valor é o preço médio ponderado (vwap), que não usamos
COLUNAS_DA_API_DA_KRAKEN = [
    "hora",
    "abertura",
    "maxima",
    "minima",
    "fechamento",
    "vwap",
    "volume",
    "negocios",
]


def ler_mercado_bitcoin(conteudo: bytes, agora: datetime) -> pd.DataFrame:
    """Candles diários de `api/v4/candles` do Mercado Bitcoin (BTC-BRL), em reais."""
    dados = json.loads(conteudo)
    tabela = pd.DataFrame(
        {
            "hora": dados["t"],
            "abertura": dados["o"],
            "maxima": dados["h"],
            "minima": dados["l"],
            "fechamento": dados["c"],
            "volume": dados["v"],
        }
    )
    return _padronizar(tabela, "BRL", agora)


def ler_kraken_rest(conteudo: bytes, agora: datetime) -> pd.DataFrame:
    """Candles diários de `0/public/OHLC` da Kraken (XBTUSD), até o último fechado (`last`)."""
    dados = json.loads(conteudo)
    if dados["error"]:
        raise ValueError(f"A Kraken respondeu com erro: {', '.join(dados['error'])}")
    resultado = dados["result"]
    par = next(chave for chave in resultado if chave != "last")
    tabela = pd.DataFrame(resultado[par], columns=COLUNAS_DA_API_DA_KRAKEN).drop(
        columns="vwap"
    )
    tabela = tabela[tabela["hora"] <= resultado["last"]]
    return _padronizar(tabela, "USD", agora)


def ler_kraken_arquivo(conteudo: bytes, agora: datetime) -> pd.DataFrame:
    """Um CSV diário (`XBTUSD_1440.csv`) do arquivo histórico OHLCVT da Kraken."""
    tabela = pd.read_csv(
        io.BytesIO(conteudo), header=None, names=COLUNAS_DO_ARQUIVO_DA_KRAKEN
    )
    return _padronizar(tabela, "USD", agora)


def _padronizar(tabela: pd.DataFrame, moeda: str, agora: datetime) -> pd.DataFrame:
    abertura_do_dia = pd.to_datetime(tabela["hora"], unit="s", utc=True)
    tabela = tabela.drop(columns="hora").assign(
        dia=abertura_do_dia.dt.date, divulgado_em=abertura_do_dia + UM_DIA, moeda=moeda
    )
    tabela[COLUNAS_DE_PRECO] = tabela[COLUNAS_DE_PRECO].astype(float)
    if "negocios" not in tabela:
        tabela["negocios"] = pd.NA
    fechados = tabela[tabela["divulgado_em"] <= pd.Timestamp(agora)]
    colunas = ["dia", *COLUNAS_DE_PRECO, "negocios", "moeda", "divulgado_em"]
    return fechados[colunas].sort_values("dia").reset_index(drop=True)
