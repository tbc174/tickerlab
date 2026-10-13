"""Research: Juros e inflação (Selic, CDI, IPCA, juro real e o Focus), com a fonte de cada número.

A tela só lê, chama `src/juros_e_inflacao.py` e mostra. Regra de `telas/`: nenhum estado mutável
no módulo.
"""

import logging
from datetime import timedelta

import pandas as pd
import streamlit as st

from src import graficos, relatorios
from src import juros_e_inflacao as ji
from src.banco.conexao import obter_engine, tabela_inexistente
from src.cdi import CDIIndisponivelError
from telas.comum import cabecalho_da_pagina, mostrar_grafico, obter_cdi

log = logging.getLogger(__name__)
DIAS_DE_CDI = 400  # um pouco mais que um ano de dias corridos: cobre 252 dias úteis


def _ler_painel(hoje):
    """O painel de hoje, ou None se o acervo ainda não tem as séries (ou o banco não respondeu)."""
    try:
        with obter_engine().connect() as conexao:
            lidas = ji.ler_series(conexao, hoje)
    except Exception as erro:
        if not tabela_inexistente(erro):
            log.exception("Falha ao ler as séries de juros e inflação")
            st.error(
                "Não consegui ler as séries do Banco Central agora. Tente de novo em instantes."
            )
            return None
        lidas = {}
    if not lidas:
        st.info(
            "As séries do Banco Central ainda não foram coletadas neste servidor "
            "(`python -m scripts.atualizar_series_macro`)."
        )
        return None
    try:
        inicio = pd.Timestamp(hoje - timedelta(days=DIAS_DE_CDI))
        cdi = obter_cdi(inicio, pd.Timestamp(hoje))
    except CDIIndisponivelError:
        cdi = None
    return ji.montar_painel(lidas, cdi, hoje)


def _mostrar_numeros(painel):
    colunas = st.columns(3)
    for posicao, numero in enumerate(painel.numeros):
        with colunas[posicao % 3]:
            st.metric(numero.nome, ji.formatar_valor(numero))
            st.caption(ji.legenda(numero))


def _mostrar_expectativas(painel):
    if not painel.expectativas:
        return
    st.markdown("**O que o mercado espera (boletim Focus)**")
    st.dataframe(
        pd.DataFrame(
            {
                "Indicador": [e.indicador for e in painel.expectativas],
                "Ano": [str(e.ano) for e in painel.expectativas],
                "Mediana (%)": [
                    f"{e.mediana:.2f}".replace(".", ",") for e in painel.expectativas
                ],
            }
        ),
        hide_index=True,
        width="stretch",
    )
    pesquisa = painel.expectativas[0].pesquisa
    if pesquisa is not None:
        st.caption(
            f"Pesquisa de {pesquisa:%d/%m/%Y} · {ji.FONTE_FOCUS}. É a mediana das projeções, não uma previsão do TickerLab."
        )


def pagina_juros_e_inflacao():
    cabecalho_da_pagina("juros_e_inflacao")
    hoje = pd.Timestamp.now(tz=relatorios.FUSO).date()
    painel = _ler_painel(hoje)
    if painel is None:
        return
    _mostrar_numeros(painel)
    for aviso in painel.avisos:
        st.caption(aviso)
    if painel.historico:
        mostrar_grafico(graficos.criar_grafico_juros_e_inflacao(painel.historico))
    _mostrar_expectativas(painel)
