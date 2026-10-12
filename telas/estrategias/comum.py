"""O que várias páginas de estratégias usam: a estratégia de referência, as explicações e o custo.

Saiu do `app.py` sem mudar comportamento (Master v3, Fase E). Regra de `telas/`: nenhum estado
mutável no módulo (um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import pandas as pd
import streamlit as st

from src.backtest import CUSTO_PADRAO_POR_OPERACAO
from src.conteudo import carregar_estrategias
from src.estrategias import ESTRATEGIAS
from src.metricas import resumir_desempenho
from telas.comum import formatar_metrica, formatar_pct

ESTRATEGIA_DE_REFERENCIA = "Comprar e segurar"


@st.cache_data
def obter_estrategias():
    """Lê as explicações das estratégias uma vez só."""
    return carregar_estrategias()


def _escolher_estrategia_simples(chave):
    return st.selectbox(
        "Estratégia (com os parâmetros padrão)",
        list(ESTRATEGIAS),
        index=list(ESTRATEGIAS).index(ESTRATEGIA_DE_REFERENCIA),
        format_func=lambda n: f"{ESTRATEGIAS[n].grupo} · {n}",
        key=f"{chave}_estrategia",
    )


def _custo_do_experimento(chave):
    return (
        st.number_input(
            "Custo por operação (%)",
            0.0,
            2.0,
            CUSTO_PADRAO_POR_OPERACAO * 100,
            0.01,
            format="%.2f",
            key=f"{chave}_custo",
        )
        / 100
    )


def _tabela_de_resultados(resultados, taxa_livre_de_risco, extras=None):
    linhas = {}
    for rotulo, r in resultados.items():
        numeros = resumir_desempenho(
            r.retorno, r.posicao, r.operacoes, taxa_livre_de_risco
        )
        linha = {
            "Retorno total": formatar_metrica(
                "Retorno total", numeros["Retorno total"]
            ),
            "Índice de Sharpe": formatar_metrica("Sharpe", numeros["Índice de Sharpe"]),
            "Maior queda": formatar_metrica("Maior queda", numeros["Maior queda"]),
            "Exposição média": formatar_pct(numeros["Exposição média"]),
        }
        if extras and rotulo in extras:
            linha.update(extras[rotulo])
        linhas[rotulo] = linha
    return pd.DataFrame(linhas).T
