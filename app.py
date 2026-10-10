"""TickerLab: interface do app. Só mostra; os cálculos ficam em src/."""

import plotly.express as px
import streamlit as st
import yfinance as yf

from src import indicadores as ind

st.set_page_config(page_title="TickerLab", layout="wide")
st.title("TickerLab")
st.caption("Análise de ações para estudo. Não é recomendação de investimento.")

# --- Passo 1: entradas ------------------------------------------------------
ticker = st.text_input("Ticker", value="PETR4.SA")
periodo = st.selectbox("Período", ["6mo", "1y", "2y", "5y"], index=2)

# --- Passo 2: baixar os dados (já pronto; vira src/dados.py mais adiante) ----
dados = yf.download(ticker, period=periodo, auto_adjust=True, progress=False)
if dados is None or dados.empty:
    st.error(
        f"Não encontrei dados para {ticker}. Confira o ticker (B3 termina em .SA)."
    )
    st.stop()
dados.columns = dados.columns.droplevel("Ticker")
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
# TODO: px.line(fechamento) e st.plotly_chart(figura, use_container_width=True)
figura = px.line(fechamento)
st.plotly_chart(figura, use_container_width=True)
