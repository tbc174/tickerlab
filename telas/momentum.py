"""Momentum: a página de momentum entre ativos.

Saiu do `app.py` sem mudar comportamento (Master v3, Fase E). Regra de `telas/`: nenhum estado
mutável no módulo (um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import pandas as pd
import streamlit as st

from src import graficos
from src.dados import DadosIndisponiveisError, normalizar_ticker
from src.momentum import montar_tabela_de_momentum
from telas.comum import (
    ajuda_do,
    cabecalho_da_pagina,
    carregar_contexto,
    carregar_dados,
    formatar_metrica,
    formatar_pct,
    mostrar_grafico,
)


def secao_momentum(principal, periodo):
    st.subheader("Favoritos e momentum")
    st.caption(
        "Compara o momentum (a tendência recente) do ativo principal e dos seus favoritos. "
        "Marque favoritos com o botão do topo da página."
    )
    favoritos = st.session_state.get("favoritos", [])
    tickers = [principal, *[normalizar_ticker(f) for f in favoritos]]
    tickers = list(dict.fromkeys(tickers))
    if len(tickers) < 2:
        st.info(
            "Favorite alguns ativos para compará-los aqui. Por enquanto só há o principal."
        )
    mostrar_reversao = st.checkbox(
        "Mostrar também a reversão à média (z-score de 20 dias)",
        key="momentum_reversao",
        help=ajuda_do("Reversão à média"),
    )
    fechamentos, sem_dados = {}, []
    for ticker in tickers:
        try:
            fechamentos[ticker] = carregar_dados(ticker, periodo)["Close"]
        except DadosIndisponiveisError:
            sem_dados.append(ticker)
    if sem_dados:
        st.warning(f"Não encontrei dados para: {', '.join(sem_dados)}.")
    try:
        tabela, sem_historico = montar_tabela_de_momentum(fechamentos)
    except ValueError as erro:
        st.info(f"{erro} Escolha o período de 2 ou 5 anos.")
        return
    if sem_historico:
        st.caption(
            f"Sem histórico suficiente (menos de 1 ano): {', '.join(sem_historico)}."
        )
    exibicao = pd.DataFrame(index=tabela.index)
    exibicao["Posição"] = tabela["Posição"].astype(int)
    for coluna in ("1 mês", "3 meses", "6 meses", "12-1 meses"):
        exibicao[coluna] = [formatar_pct(v, com_sinal=True) for v in tabela[coluna]]
    exibicao["Momentum"] = [
        "positivo" if v > 0 else "negativo" for v in tabela["12-1 meses"]
    ]
    if mostrar_reversao:
        exibicao["Z-score (20 dias)"] = [
            formatar_metrica("Sharpe", v) for v in tabela["Z-score (20 dias)"]
        ]
        exibicao["Leitura da reversão"] = [
            "esticado para cima"
            if v > 2
            else "esticado para baixo"
            if v < -2
            else "perto da média"
            for v in tabela["Z-score (20 dias)"]
        ]
    st.dataframe(exibicao, width="stretch")
    mostrar_grafico(graficos.criar_grafico_momentum(tabela["12-1 meses"]))
    st.caption(
        "A posição segue o momentum 12-1 (retorno de 12 meses sem contar o último mês). "
        "Momentum positivo não é recomendação de compra: é um fato do passado. Com "
        "poucos ativos e poucos anos, a ordem muda muito de um período para outro. "
        + (
            "Um z-score acima de +2 ou abaixo de −2 indica um preço bem afastado da média "
            "de 20 dias; a reversão à média aposta que ele volta, o momentum aposta que continua."
            if mostrar_reversao
            else ""
        )
    )


def pagina_momentum():
    cabecalho_da_pagina("momentum")
    c = carregar_contexto()
    secao_momentum(c.ticker, c.periodo)
