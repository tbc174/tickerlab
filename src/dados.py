"""Busca e preparo dos dados de mercado (Yahoo Finance), com cache em SQLite e plano B.

Ordem de tentativas em `baixar_dados`:
1. o cache em SQLite (`src/armazenamento.py`), se foi atualizado há pouco;
2. o Yahoo Finance, pedindo só os dias que faltam quando já há histórico guardado;
3. se o Yahoo falhar, o histórico guardado (marcado como antigo);
4. se não houver nada guardado, os dados de exemplo do projeto (se o ticker tiver).
"""

import logging
import re
import sqlite3
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from src import armazenamento
from src.exemplos import DESLOCAMENTO_DO_PERIODO, carregar_exemplo

SUFIXO_B3 = ".SA"
PADRAO_B3 = re.compile(r"[A-Z]{4}\d{1,2}")  # 4 letras + 1 ou 2 números (PETR4, BOVA11)
PERIODOS_VALIDOS = ["6mo", "1y", "2y", "5y"]
TOLERANCIA_DE_COBERTURA = timedelta(
    days=10
)  # feriados e fins de semana no começo do período

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


def _baixar_do_yahoo(ticker: str, **pedido: str) -> pd.DataFrame | None:
    """Uma consulta ao Yahoo, com colunas simples e só dias úteis. None se falhar ou vier vazia."""
    try:
        dados = yf.download(ticker, auto_adjust=True, progress=False, **pedido)
    except Exception as erro:  # noqa: BLE001  (o yfinance levanta vários tipos de erro)
        log.warning("Falha ao baixar %s no Yahoo Finance: %s", ticker, erro)
        return None
    if dados is None or dados.empty:
        return None
    dados.columns = dados.columns.droplevel("Ticker")  # tira o nível do ticker
    log.info("Baixados %d dias de %s (%s).", len(dados), ticker, pedido)
    return manter_apenas_dias_uteis(dados)


def _recortar_periodo(dados: pd.DataFrame, periodo: str) -> pd.DataFrame:
    """Os últimos `periodo` do histórico (o fim é o último dia disponível)."""
    recorte = dados.loc[
        dados.index > dados.index[-1] - DESLOCAMENTO_DO_PERIODO[periodo]
    ]
    recorte.attrs = dict(dados.attrs)
    return recorte


def _cobre_o_periodo(guardado: pd.DataFrame, periodo: str) -> bool:
    if guardado.empty:
        return False
    inicio_necessario = guardado.index[-1] - DESLOCAMENTO_DO_PERIODO[periodo]
    return guardado.index[0] <= inicio_necessario + TOLERANCIA_DE_COBERTURA


def _marcar_como_antigo(dados: pd.DataFrame) -> pd.DataFrame:
    dados.attrs = {
        **dados.attrs,
        "origem": "cache_antigo",
        "ate": dados.index[-1].strftime("%d/%m/%Y"),
    }
    return dados


def _baixar_tudo(
    ticker: str, periodo: str, guardado: pd.DataFrame, usar_banco: bool, agora: datetime
) -> pd.DataFrame:
    dados = _baixar_do_yahoo(ticker, period=periodo)
    if dados is not None:
        if usar_banco:
            armazenamento.salvar_precos(ticker, dados)
            armazenamento.registrar_consulta(ticker, agora)
        return dados
    if not guardado.empty:
        log.warning(
            "Sem resposta do Yahoo para %s: usando o histórico guardado.", ticker
        )
        return _marcar_como_antigo(_recortar_periodo(guardado, periodo))
    exemplo = carregar_exemplo(ticker, periodo)
    if exemplo is not None:
        log.warning("Sem resposta do Yahoo para %s: usando dados de exemplo.", ticker)
        return manter_apenas_dias_uteis(exemplo)
    raise DadosIndisponiveisError(
        f"Não encontrei dados para {ticker}. Confira o código do ativo."
    )


def _trocar_historico_reajustado(
    ticker: str, periodo: str, guardado: pd.DataFrame, agora: datetime
) -> pd.DataFrame:
    """O Yahoo reajustou o passado: baixa o histórico de novo e só então troca o guardado.

    O guardado só sai do banco quando o substituto chega cobrindo o período. Se o download falhar
    ou vier curto, o guardado fica intacto e volta marcado como antigo (preços ajustados e não
    ajustados nunca se misturam).
    """
    completo = _baixar_do_yahoo(ticker, period=periodo)
    if completo is None or not _cobre_o_periodo(completo, periodo):
        log.warning(
            "Histórico novo de %s não chegou inteiro: mantendo o guardado.", ticker
        )
        return _marcar_como_antigo(_recortar_periodo(guardado, periodo))
    armazenamento.substituir_precos(ticker, completo, agora)
    return completo


def _dados_com_banco(ticker: str, periodo: str, agora: datetime) -> pd.DataFrame:
    guardado = armazenamento.ler_precos(ticker)
    if not _cobre_o_periodo(guardado, periodo):
        return _baixar_tudo(ticker, periodo, guardado, True, agora)

    if armazenamento.consulta_recente(ticker, agora):
        log.info("Usando o histórico guardado de %s (consulta recente).", ticker)
        return _recortar_periodo(guardado, periodo)

    # só os dias que faltam, repetindo alguns já guardados para conferir se nada foi reajustado
    inicio = guardado.index[-1] - timedelta(days=armazenamento.DIAS_DE_SOBREPOSICAO)
    novo = _baixar_do_yahoo(ticker, start=inicio.strftime("%Y-%m-%d"))
    if novo is None:
        log.warning(
            "Sem resposta do Yahoo para %s: usando o histórico guardado.", ticker
        )
        return _marcar_como_antigo(_recortar_periodo(guardado, periodo))
    if armazenamento.precos_foram_reajustados(guardado, novo):
        log.info(
            "Preços de %s foram reajustados (dividendo ou desdobramento): baixando de novo.",
            ticker,
        )
        return _trocar_historico_reajustado(ticker, periodo, guardado, agora)
    armazenamento.salvar_precos(ticker, novo)
    armazenamento.registrar_consulta(ticker, agora)
    return _recortar_periodo(armazenamento.ler_precos(ticker), periodo)


def baixar_dados(
    ticker: str,
    periodo: str = "2y",
    forcar_exemplo: bool = False,
    usar_banco: bool = True,
    agora: datetime | None = None,
) -> pd.DataFrame:
    """Histórico diário do ticker, já com colunas simples.

    Usa o cache em SQLite (`usar_banco`), pede ao Yahoo só o que falta e, se ele falhar, cai
    para o histórico guardado e depois para os dados de exemplo. A origem dos dados fica em
    `dados.attrs["origem"]` quando não vêm direto do Yahoo ou de um cache atualizado.
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

    agora = agora or armazenamento.agora_utc()
    if usar_banco:
        try:
            return _dados_com_banco(ticker, periodo, agora)
        except sqlite3.Error as erro:
            log.error("Cache em SQLite indisponível (%s): seguindo sem ele.", erro)
    return _baixar_tudo(ticker, periodo, pd.DataFrame(), False, agora)
