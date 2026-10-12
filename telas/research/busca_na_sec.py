"""Busca na hora na SEC (R4): empresa dos EUA ainda fora da base é buscada quando alguém pede.

Saiu do `app.py` sem mudar comportamento. Regra de `telas/`: nenhum estado mutável no módulo
(um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import logging
import re
from datetime import datetime

import streamlit as st

from src import coleta_sec, eventos_sec, relatorios
from src.banco.conexao import obter_engine
from src.configuracao import contato
from src.moedas import moeda_do_ticker

BUSCAS_NA_SEC_POR_SESSAO = 5


ACAO_DOS_EUA = (
    r"[A-Z][A-Z.\-]{0,9}"  # AAPL, BRK-B (sem índices ^GSPC nem cripto BTC-USD)
)


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def _mapa_da_sec(agente):
    """O `company_tickers.json` da SEC inteiro (ticker → CIK), guardado por um dia."""
    cliente = coleta_sec.ClienteSec(agente)
    return eventos_sec.ler_tickers(cliente.baixar(eventos_sec.URL_DOS_TICKERS))


def _pode_buscar_na_sec(ticker):
    return (
        moeda_do_ticker(ticker) == "USD"
        and re.fullmatch(ACAO_DOS_EUA, ticker) is not None
        and not ticker.endswith("-USD")
    )


def _buscar_na_sec(ticker):
    email = contato()
    if email is None:
        st.session_state["busca_na_sec_aviso"] = (
            "A busca na SEC não está configurada neste servidor (falta o e-mail de contato)."
        )
        return
    feitas = st.session_state.get("buscas_na_sec", 0)
    if feitas >= BUSCAS_NA_SEC_POR_SESSAO:
        st.session_state["busca_na_sec_aviso"] = (
            f"Você já fez {feitas} buscas novas nesta visita. Tente de novo mais tarde."
        )
        return
    agente = f"TickerLab {email}"
    try:
        empresa, eventos, lidos = coleta_sec.buscar_agora(
            obter_engine(),
            coleta_sec.ClienteSec(agente),
            ticker,
            _mapa_da_sec(agente),
            datetime.now(relatorios.FUSO),
        )
    except coleta_sec.BuscaRecusada as erro:
        st.session_state["busca_na_sec_aviso"] = str(erro)
        return
    except coleta_sec.ERROS_DE_UMA_EMPRESA:
        logging.getLogger(__name__).exception("Falha na busca na SEC")
        st.session_state["busca_na_sec_aviso"] = (
            "A SEC não respondeu agora. Tente de novo em instantes."
        )
        return
    st.session_state["buscas_na_sec"] = feitas + 1
    st.session_state["busca_na_sec_feita"] = (
        f"{empresa}: {eventos} eventos e {lidos} negociações de pessoas de dentro guardados. "
        "Daqui para frente ela entra na coleta diária."
    )


def oferecer_busca_na_sec(ticker, o_que):
    """Mensagem de "sem cobertura" e, para ações dos EUA fora do S&P 500, o botão da busca."""
    if not _pode_buscar_na_sec(ticker):
        st.info(
            f"{ticker} não tem cadastro na CVM nem na SEC. {o_que} cobrem ações e units da B3 "
            "e ações dos EUA; fundos, ETFs, BDRs, índices e cripto dependem de outras fontes.",
            icon=":material/info:",
        )
        return
    st.info(
        f"{ticker} ainda não está na base do TickerLab (a coleta diária cobre o S&P 500). Dá para "
        "buscar a empresa na SEC agora: leva alguns segundos e ela passa a entrar na coleta "
        "diária.",
        icon=":material/travel_explore:",
    )
    if aviso := st.session_state.pop("busca_na_sec_aviso", None):
        st.warning(aviso)
    st.button(
        "Buscar na SEC agora",
        icon=":material/cloud_download:",
        key=f"buscar_na_sec_{ticker}",
        on_click=_buscar_na_sec,
        args=(ticker,),
    )


def mostrar_resultado_da_busca_na_sec():
    if feita := st.session_state.pop("busca_na_sec_feita", None):
        st.success(feita, icon=":material/check_circle:")
