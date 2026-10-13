"""Research: Linha do tempo (o preço do ativo e os acontecimentos da empresa no mesmo eixo).

A tela só lê, chama `src/linha_do_tempo.py` e mostra. Regra de `telas/`: nenhum estado mutável
no módulo.
"""

import logging

import pandas as pd
import streamlit as st

from src import graficos
from src import linha_do_tempo as ldt
from src.banco.conexao import obter_engine, tabela_inexistente
from src.banco.eventos import eventos_dos_tickers
from telas.comum import cabecalho_da_pagina, carregar_contexto, mostrar_grafico

log = logging.getLogger(__name__)


def _ler_eventos(ticker, desde):
    """Os acontecimentos do ativo desde `desde`; lista vazia se o banco não tem o Research."""
    try:
        with obter_engine().connect() as conexao:
            return eventos_dos_tickers(
                conexao, [ticker], desde, limite=ldt.LIMITE_DE_EVENTOS
            )
    except Exception as erro:
        if not tabela_inexistente(erro):
            log.exception("Falha ao ler os acontecimentos da linha do tempo")
            st.warning(
                "Não consegui ler os acontecimentos agora; o gráfico mostra só o preço."
            )
        return []


def _mostrar_tabela(linha):
    st.dataframe(
        pd.DataFrame(
            {
                "Data": [f"{m.data:%d/%m/%Y}" for m in linha.marcos],
                "Documento": [m.rotulo for m in linha.marcos],
                "Assunto": [m.assunto for m in linha.marcos],
                "Documento original": [m.link for m in linha.marcos],
            }
        ),
        column_config={
            "Documento original": st.column_config.LinkColumn(display_text="Abrir")
        },
        hide_index=True,
        width="stretch",
    )


def pagina_linha_do_tempo():
    cabecalho_da_pagina("linha_do_tempo")
    c = carregar_contexto()
    relevancia = st.segmented_control(
        "Quais acontecimentos mostrar",
        list(ldt.RELEVANCIAS),
        default="Relevantes",
        key="linha_do_tempo_relevancia",
    )
    eventos = _ler_eventos(c.ticker, c.fechamento.index[0].date())
    linha = ldt.montar_linha_do_tempo(
        c.fechamento,
        eventos,
        ldt.RELEVANCIAS.get(relevancia or "", ldt.MATERIALIDADE_PADRAO),
    )
    mostrar_grafico(graficos.criar_grafico_linha_do_tempo(linha))
    st.caption(ldt.AVISO_DA_LINHA)
    if not linha.marcos:
        st.info(ldt.SEM_ACONTECIMENTOS)
        return
    _mostrar_tabela(linha)
    if linha.fora_do_grafico:
        st.caption(ldt.texto_fora_do_grafico(linha.fora_do_grafico))
