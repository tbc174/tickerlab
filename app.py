"""TickerLab: interface do app. Só mostra; os cálculos ficam em src/."""

import pandas as pd
import plotly.express as px
import streamlit as st

from src import indicadores as ind
from src.conteudo import carregar_glossario
from src.dados import DadosIndisponiveisError, baixar_dados, normalizar_ticker

MIN_DIAS_PARA_ANALISE = 20  # com menos retornos que isso, os números não dizem nada

st.set_page_config(page_title="TickerLab", layout="wide")
st.title("TickerLab")
st.caption("Análise de ações para estudo. Não é recomendação de investimento.")


@st.cache_data(ttl=3600, show_spinner="Baixando dados...")
def carregar_dados(ticker, periodo):
    """Guarda o download por 1 hora para não consultar o Yahoo a cada clique."""
    return baixar_dados(ticker, periodo)


@st.cache_data
def obter_glossario():
    """Lê o glossário uma vez só; o arquivo não muda enquanto o app roda."""
    return carregar_glossario()


def formatar_pct(valor, com_sinal=False):
    """Porcentagem no estilo brasileiro (vírgula); vazio vira um traço."""
    if pd.isna(valor):
        return "—"
    texto = f"{valor:+.2%}" if com_sinal else f"{valor:.2%}"
    return texto.replace(".", ",")


def mostrar_metrica(coluna, rotulo, valor, termo_do_glossario):
    """Um número com o "?" que explica o termo, usando o texto do glossário."""
    ajuda = obter_glossario().get(termo_do_glossario)
    coluna.metric(rotulo, valor, help=ajuda)


# --- Entradas ---------------------------------------------------------------
col_ticker, col_periodo, col_taxa = st.columns(3)
ticker = col_ticker.text_input("Ticker", value="PETR4.SA")
periodo = col_periodo.selectbox("Período", ["6mo", "1y", "2y", "5y"], index=2)
taxa_percentual = col_taxa.number_input(
    "Taxa livre de risco (% ao ano)",
    min_value=0.0,
    max_value=50.0,
    value=0.0,
    step=0.5,
    help="Quanto renderia um investimento sem risco, como o Tesouro Selic. "
    "Entra no cálculo do Índice de Sharpe. Deixe em 0 para ignorá-la.",
)
taxa_livre_de_risco = taxa_percentual / 100

# --- Dados ------------------------------------------------------------------
try:
    # normaliza antes: "petr4" e "PETR4.SA" devem usar a mesma entrada do cache
    dados = carregar_dados(normalizar_ticker(ticker), periodo)
except DadosIndisponiveisError as erro:
    st.error(str(erro))
    st.stop()
fechamento = dados["Close"]

# --- Cálculos (funções de src/indicadores.py) -------------------------------
retorno = ind.calcular_retorno_diario(fechamento)

if retorno.dropna().size < MIN_DIAS_PARA_ANALISE:
    st.warning(
        f"Só há {retorno.dropna().size} dias de dados para este ticker. "
        f"São necessários pelo menos {MIN_DIAS_PARA_ANALISE} para calcular os números. "
        "Tente um período mais longo."
    )
    st.stop()

retorno_acumulado = ind.calcular_retorno_acumulado(retorno)
drawdown = ind.calcular_drawdown(fechamento)
data_melhor, melhor_dia = ind.encontrar_melhor_dia(retorno)
data_pior, pior_dia = ind.encontrar_pior_dia(retorno)

# --- Painel de números --------------------------------------------------------
st.subheader("Painel de números")
st.caption("Passe o mouse no ? de cada número para ver o que ele significa.")

linha1 = st.columns(4)
mostrar_metrica(
    linha1[0],
    "Retorno total",
    formatar_pct(retorno_acumulado.iloc[-1], com_sinal=True),
    "Retorno acumulado",
)
mostrar_metrica(
    linha1[1],
    "Retorno anualizado",
    formatar_pct(ind.calcular_retorno_anualizado(retorno), com_sinal=True),
    "Retorno anualizado",
)
mostrar_metrica(
    linha1[2],
    "Volatilidade anual",
    formatar_pct(ind.calcular_volatilidade_anual(retorno)),
    "Volatilidade",
)
mostrar_metrica(
    linha1[3],
    "Maior queda (drawdown)",
    formatar_pct(drawdown.min()),
    "Drawdown",
)

linha2 = st.columns(5)
sharpe = ind.calcular_indice_sharpe(retorno, taxa_livre_de_risco)
mostrar_metrica(
    linha2[0],
    "Índice de Sharpe",
    "—" if pd.isna(sharpe) else f"{sharpe:.2f}".replace(".", ","),
    "Índice de Sharpe",
)
mostrar_metrica(
    linha2[1],
    f"Melhor dia ({data_melhor:%d/%m/%Y})",
    formatar_pct(melhor_dia, com_sinal=True),
    "Melhor e pior dia",
)
mostrar_metrica(
    linha2[2],
    f"Pior dia ({data_pior:%d/%m/%Y})",
    formatar_pct(pior_dia, com_sinal=True),
    "Melhor e pior dia",
)
mostrar_metrica(
    linha2[3],
    "Dias de alta",
    formatar_pct(ind.calcular_percentual_dias_positivos(retorno)),
    "Dias de alta",
)
mostrar_metrica(
    linha2[4],
    "Perda de um dia ruim (VaR 95%)",
    formatar_pct(ind.calcular_var_historico(retorno)),
    "Perda de um dia ruim (VaR)",
)

# --- Gráfico de preço -------------------------------------------------------
st.subheader("Preço de fechamento")
figura = px.line(fechamento)
st.plotly_chart(figura, width="stretch")
