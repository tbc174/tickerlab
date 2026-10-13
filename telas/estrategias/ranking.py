"""Estratégias: ranking de todas as estratégias no mesmo ativo.

Saiu do `app.py` sem mudar comportamento (Master v3, Fase E). Regra de `telas/`: nenhum estado
mutável no módulo (um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import streamlit as st

from src import graficos
from src.backtest import CUSTO_PADRAO_POR_OPERACAO
from src.indicadores import MOTIVO_SEM_ANUALIZAR
from src.ranking import montar_ranking
from telas.comum import (
    ajuda_do,
    cabecalho_da_pagina,
    carregar_contexto,
    formatar_metrica,
    mostrar_grafico,
)
from telas.estrategias.comum import ESTRATEGIA_DE_REFERENCIA


@st.cache_data(show_spinner="Rodando todas as estratégias...")
def calcular_ranking(dados, custo, taxa, extras):
    return montar_ranking(dados, custo, taxa, extras)


def secao_ranking(dados, taxa_livre_de_risco):
    st.subheader("Ranking: todas as estratégias no mesmo ativo")
    st.caption(
        "Cada estratégia roda com os valores padrão, sem proteções, e é ordenada pelo Sharpe. "
        "Olhar só o topo da lista é o jeito mais fácil de se enganar: leia as duas colunas "
        "que descontam a sorte."
    )
    col_custo, col_extras = st.columns(2)
    custo_percentual = col_custo.number_input(
        "Custo por operação (%)",
        min_value=0.0,
        max_value=2.0,
        value=CUSTO_PADRAO_POR_OPERACAO * 100,
        step=0.01,
        format="%.2f",
        key="ranking_custo",
    )
    extras = col_extras.number_input(
        "Outras ideias que você já testou (opcional)",
        min_value=0,
        max_value=10_000,
        value=0,
        step=10,
        key="ranking_extras",
        help=ajuda_do("Data snooping (ir pescando resultados)"),
    )
    tabela, resultados = calcular_ranking(
        dados, custo_percentual / 100, taxa_livre_de_risco, int(extras)
    )
    st.caption(f"{len(tabela) + int(extras)} tentativas contadas.")

    exibicao = tabela.copy()
    for coluna in exibicao.columns:
        if coluna != "Grupo":
            exibicao[coluna] = [formatar_metrica(coluna, v) for v in exibicao[coluna]]
    st.dataframe(exibicao, width="stretch")
    st.caption(
        "**Chance de não ser sorte:** Sharpe deflacionado (acima de 95% é convincente). "
        "**p-valor (acaso):** fatia de posições sem relação com o preço que fez igual ou "
        "melhor (abaixo de 5% é convincente)."
    )

    if tabela["Retorno anualizado"].notna().any():
        mostrar_grafico(
            graficos.criar_grafico_risco_retorno(
                tabela, destaque=ESTRATEGIA_DE_REFERENCIA
            )
        )
    else:  # o gráfico é de retorno ao ano, que não existe com menos de ~1 ano
        st.info(f"Gráfico de risco e retorno: {MOTIVO_SEM_ANUALIZAR}")
    padrao = [ESTRATEGIA_DE_REFERENCIA] + [
        n for n in tabela.index if n != ESTRATEGIA_DE_REFERENCIA
    ][:2]
    escolhidas = st.multiselect(
        "Curvas de capital",
        list(tabela.index),
        default=padrao,
        key="ranking_curvas",
    )
    if escolhidas:
        mostrar_grafico(
            graficos.criar_grafico_curvas_de_capital(
                {n: resultados[n].curva_de_capital for n in escolhidas},
                10_000.0,
                destaque=escolhidas[0],
            )
        )


def pagina_ranking():
    cabecalho_da_pagina("ranking")
    c = carregar_contexto()
    secao_ranking(c.dados, c.taxa_livre_de_risco)
