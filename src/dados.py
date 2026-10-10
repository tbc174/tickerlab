"""Busca e preparo dos dados de mercado (Yahoo Finance)."""

import logging
import re

import pandas as pd
import yfinance as yf

from src.exemplos import carregar_exemplo

SUFIXO_B3 = ".SA"
PADRAO_B3 = re.compile(r"[A-Z]{4}\d{1,2}")  # 4 letras + 1 ou 2 números (PETR4, BOVA11)
PERIODOS_VALIDOS = ["6mo", "1y", "2y", "5y"]

log = logging.getLogger(__name__)


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


def manter_apenas_dias_uteis(dados: pd.DataFrame) -> pd.DataFrame:
    """Tira sábados e domingos (o Bitcoin negocia todo dia; o resto do app conta 252 dias/ano).

    Nenhum retorno se perde: a variação do fim de semana passa a aparecer na segunda-feira, que
    é comparada com a sexta. Máxima e mínima de sábado e domingo deixam de aparecer.
    """
    uteis = dados[dados.index.dayofweek < 5]
    uteis.attrs = dict(dados.attrs)
    return uteis


def baixar_dados(
    ticker: str, periodo: str = "2y", forcar_exemplo: bool = False
) -> pd.DataFrame:
    """Baixa o histórico diário do ticker no Yahoo Finance, já com colunas simples.

    Se o Yahoo falhar (ou com `forcar_exemplo`) e houver dados de exemplo para o ticker, usa
    esses dados e marca `dados.attrs["origem"] = "exemplo"`.
    """
    ticker = normalizar_ticker(ticker)

    if periodo not in PERIODOS_VALIDOS:
        raise ValueError(
            f"Período inválido: {periodo}. Use um destes: {PERIODOS_VALIDOS}."
        )

    if not ticker:
        raise DadosIndisponiveisError("Digite um ticker, por exemplo PETR4 ou AAPL.")

    if forcar_exemplo:
        exemplo = carregar_exemplo(ticker, periodo)
        if exemplo is None:
            raise DadosIndisponiveisError(
                f"Não há dados de exemplo para {ticker}. Desmarque a opção de dados de exemplo."
            )
        log.info("Usando dados de exemplo para %s (pedido do usuário).", ticker)
        return manter_apenas_dias_uteis(exemplo)

    try:
        dados = yf.download(ticker, period=periodo, auto_adjust=True, progress=False)
    except Exception as erro:  # noqa: BLE001  (o yfinance levanta vários tipos de erro)
        log.warning("Falha ao baixar %s no Yahoo Finance: %s", ticker, erro)
        dados = None

    if dados is None or dados.empty:
        exemplo = carregar_exemplo(ticker, periodo)
        if exemplo is not None:
            log.warning(
                "Sem resposta do Yahoo para %s: usando dados de exemplo.", ticker
            )
            return manter_apenas_dias_uteis(exemplo)
        raise DadosIndisponiveisError(
            f"Não encontrei dados para {ticker}. Confira o ticker (B3 termina em .SA)."
        )

    log.info("Baixados %d dias de %s (%s).", len(dados), ticker, periodo)
    dados.columns = dados.columns.droplevel("Ticker")  # tira o nível do ticker
    return manter_apenas_dias_uteis(dados)
