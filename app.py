"""TickerLab: interface do app. Só mostra; os cálculos ficam em src/."""

import pandas as pd
import streamlit as st

from src import graficos
from src import indicadores as ind
from src.conteudo import carregar_glossario, descrever_pior_drawdown
from src.dados import DadosIndisponiveisError, baixar_dados, normalizar_ticker
from src.estilo import CSS_DO_APP
from src.indicadores import NOMES_DOS_MESES

MIN_DIAS_PARA_ANALISE = 20  # com menos retornos que isso, os números não dizem nada
JANELAS_VOLATILIDADE = [20, 60, 120]  # dias
JANELAS_MEDIAS = [20, 50, 200]  # dias
PERIODOS_DAS_VELAS = {"3 meses": 63, "6 meses": 126, "1 ano": 252, "Tudo": None}

st.set_page_config(page_title="TickerLab", layout="wide")
st.markdown(f"<style>{CSS_DO_APP}</style>", unsafe_allow_html=True)


# --- Ajudantes --------------------------------------------------------------
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


def mostrar_grafico(figura):
    """Gráfico do Plotly com a interação padrão do app (zoom, linha-guia, duplo clique)."""
    st.plotly_chart(figura, width="stretch", config=graficos.CONFIG_PLOTLY)


# --- Cabeçalho e entradas -----------------------------------------------------
def mostrar_cabecalho():
    st.title("TickerLab")
    st.caption("Análise de ações para estudo. Não é recomendação de investimento.")


def ler_entradas():
    """Campos do topo da página. Devolve (ticker, período, taxa livre de risco)."""
    with st.container(border=True):
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
    return ticker, periodo, taxa_percentual / 100


# --- Seções -----------------------------------------------------------------
def secao_painel_de_numeros(fechamento, retorno, taxa_livre_de_risco):
    st.subheader("Painel de números")
    st.caption("Passe o mouse no ? de cada número para ver o que ele significa.")

    retorno_acumulado = ind.calcular_retorno_acumulado(retorno)
    drawdown = ind.calcular_drawdown(fechamento)
    data_melhor, melhor_dia = ind.encontrar_melhor_dia(retorno)
    data_pior, pior_dia = ind.encontrar_pior_dia(retorno)

    st.markdown("**Retorno e risco**")
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

    st.markdown("**Consistência e dias extremos**")
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


def secao_preco(dados):
    st.subheader("Preço")
    col_tipo, col_medias = st.columns([1, 2])
    tipo_do_grafico = col_tipo.radio(
        "Tipo de gráfico",
        ["Linha", "Velas"],
        horizontal=True,
        help=obter_glossario().get("Gráfico de velas (candlestick)"),
    )
    medias_escolhidas = col_medias.multiselect(
        "Médias móveis (dias)",
        JANELAS_MEDIAS,
        placeholder="Escolha uma ou mais médias",
        help=obter_glossario().get("Média móvel"),
    )
    dias_visiveis = None
    if tipo_do_grafico == "Velas":
        # com muitos dias as velas ficam finas demais; começa mostrando os últimos meses
        periodo_velas = st.radio(
            "Velas: período mostrado",
            list(PERIODOS_DAS_VELAS),
            index=1,
            horizontal=True,
            help="Cada vela é um dia. Com muitos dias elas ficam finas; use o zoom ou "
            "troque o período para ver os detalhes.",
        )
        dias_visiveis = PERIODOS_DAS_VELAS[periodo_velas]
    mostrar_grafico(
        graficos.criar_grafico_preco(
            dados,
            tipo_do_grafico.lower(),
            tuple(sorted(medias_escolhidas)),
            dias_visiveis,
        )
    )
    st.caption(
        "Dica: arraste sobre o gráfico para dar zoom numa área e clique duas vezes para "
        "voltar ao início. Os botões 1M a Tudo trocam o período e, ao passar o mouse, "
        "a barra de ferramentas tem zoom, mover e exportar como imagem."
    )


def secao_risco(fechamento, retorno):
    st.subheader("Risco ao longo do tempo")
    janela = st.radio(
        "Janela da volatilidade (dias)",
        JANELAS_VOLATILIDADE,
        horizontal=True,
        help=obter_glossario().get("Volatilidade móvel"),
    )
    drawdown = ind.calcular_drawdown(fechamento)
    pior_drawdown = ind.encontrar_pior_drawdown(fechamento)
    st.markdown(descrever_pior_drawdown(pior_drawdown))

    col_drawdown, col_volatilidade = st.columns(2)
    with col_drawdown:
        mostrar_grafico(graficos.criar_grafico_drawdown(drawdown, pior_drawdown))
    volatilidade_movel = ind.calcular_volatilidade_movel(retorno, janela)
    with col_volatilidade:
        if volatilidade_movel.dropna().empty:
            st.info(
                f"O período é curto demais para uma janela de {janela} dias. "
                "Escolha uma janela menor ou um período maior."
            )
        else:
            mostrar_grafico(
                graficos.criar_grafico_volatilidade(volatilidade_movel, janela)
            )


def secao_retorno_mensal(retorno):
    st.subheader("Retorno por mês e ano", help=obter_glossario().get("Sazonalidade"))
    retorno_mensal = ind.calcular_retorno_mensal(retorno)
    tabela_mensal = ind.montar_tabela_retornos(retorno_mensal)
    (mes_melhor, valor_melhor), (mes_pior, valor_pior) = (
        ind.encontrar_melhor_e_pior_mes(retorno_mensal)
    )

    colunas = st.columns(3)
    mostrar_metrica(
        colunas[0],
        f"Melhor mês ({NOMES_DOS_MESES[mes_melhor.month - 1]}/{mes_melhor.year})",
        formatar_pct(valor_melhor, com_sinal=True),
        "Retorno mensal",
    )
    mostrar_metrica(
        colunas[1],
        f"Pior mês ({NOMES_DOS_MESES[mes_pior.month - 1]}/{mes_pior.year})",
        formatar_pct(valor_pior, com_sinal=True),
        "Retorno mensal",
    )
    mostrar_metrica(
        colunas[2],
        "Meses de alta",
        formatar_pct(ind.calcular_percentual_dias_positivos(retorno_mensal)),
        "Retorno mensal",
    )
    st.write("")  # respiro entre os cartões e o mapa
    mostrar_grafico(graficos.criar_mapa_de_calor_mensal(tabela_mensal))
    st.caption(
        "O primeiro e o último mês do período podem estar incompletos. "
        "A última linha mostra a média de cada mês ao longo dos anos "
        "(com poucos anos de dados, isso pode ser só coincidência)."
    )


# --- Página -----------------------------------------------------------------
mostrar_cabecalho()
ticker, periodo, taxa_livre_de_risco = ler_entradas()

try:
    # normaliza antes: "petr4" e "PETR4.SA" devem usar a mesma entrada do cache
    dados = carregar_dados(normalizar_ticker(ticker), periodo)
except DadosIndisponiveisError as erro:
    st.error(str(erro))
    st.stop()
fechamento = dados["Close"]
retorno = ind.calcular_retorno_diario(fechamento)

if retorno.dropna().size < MIN_DIAS_PARA_ANALISE:
    st.warning(
        f"Só há {retorno.dropna().size} dias de dados para este ticker. "
        f"São necessários pelo menos {MIN_DIAS_PARA_ANALISE} para calcular os números. "
        "Tente um período mais longo."
    )
    st.stop()

aba_geral, aba_risco, aba_mensal = st.tabs(["Visão geral", "Risco", "Retorno mensal"])
with aba_geral:
    secao_painel_de_numeros(fechamento, retorno, taxa_livre_de_risco)
    st.divider()
    secao_preco(dados)
with aba_risco:
    secao_risco(fechamento, retorno)
with aba_mensal:
    secao_retorno_mensal(retorno)

st.divider()
st.caption(
    "TickerLab é um projeto educacional. Os dados vêm do Yahoo Finance e podem ter atraso "
    "ou erros. Rentabilidade passada não garante resultado futuro."
)
