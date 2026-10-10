"""TickerLab: interface do app. Só mostra; os cálculos ficam em src/."""

import plotly.express as px
import streamlit as st

from src import indicadores as ind
from src.dados import DadosIndisponiveisError, baixar_dados, normalizar_ticker

st.set_page_config(page_title="TickerLab", layout="wide")
st.title("TickerLab")
st.caption("Análise de ações para estudo. Não é recomendação de investimento.")

# --- Passo 1: entradas ------------------------------------------------------
ticker = st.text_input("Ticker", value="PETR4.SA")
periodo = st.selectbox("Período", ["6mo", "1y", "2y", "5y"], index=2)

# --- Passo 2: baixar os dados (a lógica fica em src/dados.py) -----------------
@st.cache_data(ttl=3600, show_spinner="Baixando dados...")
def carregar_dados(ticker, periodo):
    """Guarda o download por 1 hora para não consultar o Yahoo a cada clique."""
    return baixar_dados(ticker, periodo)


try:
    # normaliza antes: "petr4" e "PETR4.SA" devem usar a mesma entrada do cache
    dados = carregar_dados(normalizar_ticker(ticker), periodo)
except DadosIndisponiveisError as erro:
    st.error(str(erro))
    st.stop()
fechamento = dados["Close"]

# --- Passo 3: calcular com as funções de src/indicadores.py -------------------
retorno = ind.calcular_retorno_diario(fechamento)
retorno_acumulado = ind.calcular_retorno_acumulado(retorno)
volatilidade = ind.calcular_volatilidade_anual(retorno)
drawdown = ind.calcular_drawdown(fechamento)

# --- Passo 4: números principais --------------------------------------------
# TODO: crie 3 colunas com st.columns(3) e, em cada uma, um st.metric:
#   retorno total (último valor do retorno acumulado), volatilidade anual
#   e maior queda (menor valor do drawdown). Formate como porcentagem.
colunas = st.columns(3)
colunas[0].metric("Retorno total", f"{retorno_acumulado.iloc[-1]:.2%}")
colunas[1].metric("Volatilidade anual", f"{volatilidade:.2%}")
colunas[2].metric("Maior queda", f"{drawdown.min():.2%}")
# --- Passo 5: gráfico de preço ----------------------------------------------
# TODO: px.line(fechamento) e st.plotly_chart(figura, width="stretch")
figura = px.line(fechamento)
st.plotly_chart(figura, width="stretch")
