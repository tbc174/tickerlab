"""TickerLab: interface do app. Só mostra; os cálculos ficam em src/."""

import numpy as np
import pandas as pd
import streamlit as st

from src import aprendizado, graficos
from src import indicadores as ind
from src.acaso import (
    calcular_comprimento_minimo,
    calcular_pbo,
    calcular_sharpe_deflacionado,
    simular_monte_carlo,
    testar_contra_o_acaso,
)
from src.backtest import CUSTO_PADRAO_POR_OPERACAO, executar_backtest
from src.carteiras import (
    ESTRATEGIAS_DE_CARTEIRA,
    MAX_ATIVOS_NA_CARTEIRA,
    MIN_ATIVOS_NA_CARTEIRA,
    simular_carteira,
)
from src.cdi import (
    CDIIndisponivelError,
    baixar_cdi,
    calcular_taxa_anual_do_cdi,
    curva_do_cdi,
)
from src.comparacao import (
    ATALHOS,
    ATALHOS_PADRAO,
    MAX_ATIVOS,
    NOMES_AMIGAVEIS,
    alinhar_fechamentos,
    escolher_ativos,
    interpretar_tickers,
    montar_tabela_comparativa,
    rebasear_para_100,
)
from src.conteudo import (
    carregar_estrategias,
    carregar_glossario,
    descrever_pior_drawdown,
    proteger_cifrao,
)
from src.dados import DadosIndisponiveisError, baixar_dados, normalizar_ticker
from src.estilo import CSS_DO_APP
from src.estrategias import ESTRATEGIAS, gerar_posicao
from src.experimentos import (
    REGRAS_DE_REBALANCEAMENTO,
    calcular_retorno_da_noite_com_custo,
    comparar_dentro_e_fora,
    comparar_janelas,
    resumir_janelas,
    resumir_noite_e_dia,
    separar_noite_e_dia,
    simular_aporte_unico_e_dca,
    simular_rebalanceamento,
    simular_virada_do_mes,
)
from src.imposto import aplicar_imposto
from src.indicadores import NOMES_DOS_MESES
from src.metricas import (
    calcular_intervalo_do_sharpe,
    calcular_kelly,
    calcular_omega,
    resumir_desempenho,
)
from src.pares import MAX_ATIVOS_PARA_PARES, procurar_pares, simular_par
from src.protecoes import Protecoes, aplicar_protecoes
from src.ranking import montar_ranking
from src.regimes import (
    REGIMES_DE_TENDENCIA,
    REGIMES_DE_VOLATILIDADE,
    aplicar_disjuntor_de_drawdown,
    classificar_regimes_de_tendencia,
    classificar_regimes_de_volatilidade,
    filtrar_por_regime,
    gerir_pela_variancia,
    resumir_por_regime,
    varrer_disjuntor,
)
from src.validacao import (
    avaliar_treino_e_teste,
    calcular_retornos_dos_candidatos,
    data_de_corte,
    executar_walk_forward,
    montar_candidatos,
    montar_mapa_de_sharpe,
    parametros_numericos,
)

MIN_DIAS_PARA_ANALISE = 20  # com menos retornos que isso, os números não dizem nada
JANELAS_VOLATILIDADE = [20, 60, 120]  # dias
JANELAS_MEDIAS = [20, 50, 200]  # dias
ESPERAS_DEPOIS_DO_STOP = {
    "Só com um sinal novo da estratégia": None,
    "Esperar 5 dias úteis": 5,
    "Esperar 20 dias úteis": 20,
    "Esperar 60 dias úteis": 60,
}
PERIODOS_DAS_VELAS = {"3 meses": 63, "6 meses": 126, "1 ano": 252, "Tudo": None}
ESTRATEGIA_DE_REFERENCIA = "Comprar e segurar"
METRICAS_EM_PORCENTAGEM_COM_SINAL = {
    "Retorno total",
    "Retorno anualizado",
    "Expectativa por operação",
}
METRICAS_EM_PORCENTAGEM = {
    "Chance de não ser sorte",
    "Volatilidade anual",
    "Maior queda",
    "Exposição média",
    "Taxa de acerto",
}
METRICAS_INTEIRAS = {"Dias debaixo d'água (máx.)", "Operações"}

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


@st.cache_data
def obter_estrategias():
    """Lê as explicações das estratégias uma vez só."""
    return carregar_estrategias()


def formatar_metrica(nome, valor):
    """Escolhe o formato de cada métrica do backtest (porcentagem, razão ou contagem)."""
    if pd.isna(valor):
        return "—"
    if nome in METRICAS_EM_PORCENTAGEM_COM_SINAL:
        return formatar_pct(valor, com_sinal=True)
    if nome in METRICAS_EM_PORCENTAGEM:
        return formatar_pct(valor)
    if nome in METRICAS_INTEIRAS:
        return f"{int(valor)}"
    return f"{valor:.2f}".replace(".", ",")


def formatar_pct(valor, com_sinal=False):
    """Porcentagem no estilo brasileiro (vírgula); vazio vira um traço."""
    if pd.isna(valor):
        return "—"
    texto = f"{valor:+.2%}" if com_sinal else f"{valor:.2%}"
    return texto.replace(".", ",")


def ajuda_do(termo):
    """Texto do glossário para o "?" de um campo (com o cifrão protegido)."""
    return proteger_cifrao(obter_glossario().get(termo))


def mostrar_metrica(coluna, rotulo, valor, termo_do_glossario):
    """Um número com o "?" que explica o termo, usando o texto do glossário."""
    coluna.metric(rotulo, valor, help=ajuda_do(termo_do_glossario))


def mostrar_grafico(figura):
    """Gráfico do Plotly com a interação padrão do app (zoom, linha-guia, duplo clique)."""
    st.plotly_chart(figura, width="stretch", config=graficos.CONFIG_PLOTLY)


# --- Cabeçalho e entradas -----------------------------------------------------
def mostrar_cabecalho():
    st.title("TickerLab")
    st.caption("Análise de ações para estudo. Não é recomendação de investimento.")


MODOS_DA_TAXA = ("Zero", "CDI (Banco Central)", "Digitar")


def ler_entradas():
    """Campos do topo da página. Devolve (ticker, período, modo da taxa, taxa digitada)."""
    with st.container(border=True):
        col_ticker, col_periodo, col_taxa = st.columns(3)
        ticker = col_ticker.text_input("Ticker", value="PETR4.SA")
        periodo = col_periodo.selectbox("Período", ["6mo", "1y", "2y", "5y"], index=2)
        modo = col_taxa.selectbox(
            "Taxa livre de risco",
            MODOS_DA_TAXA,
            help=ajuda_do("CDI"),
        )
        taxa_digitada = 0.0
        if modo == "Digitar":
            taxa_digitada = (
                col_taxa.number_input(
                    "Taxa (% ao ano)",
                    min_value=0.0,
                    max_value=50.0,
                    value=0.0,
                    step=0.5,
                    help="Quanto renderia um investimento sem risco. Entra no cálculo "
                    "do Índice de Sharpe.",
                )
                / 100
            )
    return ticker, periodo, modo, taxa_digitada


@st.cache_data(ttl=86_400, show_spinner="Buscando o CDI no Banco Central...")
def obter_cdi(inicio, fim):
    """Guarda o CDI por um dia: ele só muda uma vez por dia útil."""
    return baixar_cdi(inicio, fim)


def resolver_taxa_livre_de_risco(modo, taxa_digitada, indice):
    """Devolve (taxa anual, CDI diário ou None). Se o CDI falhar, cai para zero e avisa."""
    if modo == "Digitar":
        return taxa_digitada, None
    if modo == "CDI (Banco Central)":
        try:
            cdi_diario = obter_cdi(indice[0], indice[-1])
            return calcular_taxa_anual_do_cdi(cdi_diario, indice), cdi_diario
        except (CDIIndisponivelError, ValueError) as erro:
            st.warning(f"{erro} Usei taxa livre de risco zero.")
    return 0.0, None


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
        help=ajuda_do("Gráfico de velas (candlestick)"),
    )
    medias_escolhidas = col_medias.multiselect(
        "Médias móveis (dias)",
        JANELAS_MEDIAS,
        placeholder="Escolha uma ou mais médias",
        help=ajuda_do("Média móvel"),
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
        help=ajuda_do("Volatilidade móvel"),
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
    st.subheader("Retorno por mês e ano", help=ajuda_do("Sazonalidade"))
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


def formatar_tabela_comparativa(tabela):
    """Troca os números da tabela comparativa por textos no formato brasileiro."""
    exibicao = pd.DataFrame(index=[NOMES_AMIGAVEIS.get(t, t) for t in tabela.index])
    for coluna in ("Retorno total", "Retorno anualizado"):
        exibicao[coluna] = [formatar_pct(v, com_sinal=True) for v in tabela[coluna]]
    for coluna in ("Volatilidade anual", "Maior queda"):
        exibicao[coluna] = [formatar_pct(v) for v in tabela[coluna]]
    exibicao["Índice de Sharpe"] = [
        "—" if pd.isna(v) else f"{v:.2f}".replace(".", ",")
        for v in tabela["Índice de Sharpe"]
    ]
    return exibicao


def secao_comparar(principal, periodo, taxa_livre_de_risco):
    st.subheader("Comparar ativos", help=ajuda_do("Base 100"))
    st.caption(
        f"O ativo principal é {NOMES_AMIGAVEIS.get(principal, principal)} (troque lá em cima). "
        "Escolha com o que compará-lo ou digite outros tickers."
    )
    col_atalhos, col_extra = st.columns([3, 2])
    atalhos_escolhidos = col_atalhos.multiselect(
        "Comparar com",
        list(ATALHOS),
        default=ATALHOS_PADRAO,
        placeholder="Escolha índices ou ativos",
    )
    texto_extra = col_extra.text_input(
        "Outros tickers (separados por vírgula)", placeholder="Ex.: VALE3, AAPL"
    )

    tickers, ignorados = escolher_ativos(
        principal, [ATALHOS[nome] for nome in atalhos_escolhidos], texto_extra
    )
    if ignorados:
        st.warning(
            f"O limite é de {MAX_ATIVOS} ativos por comparação. "
            f"Ficaram de fora: {', '.join(ignorados)}."
        )
    if len(tickers) < 2:
        st.info("Escolha pelo menos um ativo para comparar.")
        return

    fechamentos, sem_dados = {}, []
    for ticker in tickers:
        try:
            fechamentos[ticker] = carregar_dados(ticker, periodo)["Close"]
        except DadosIndisponiveisError:
            sem_dados.append(ticker)
    if sem_dados:
        st.warning(
            f"Não encontrei dados para: {', '.join(sem_dados)}. "
            "Eles ficaram de fora da comparação."
        )
    if principal not in fechamentos or len(fechamentos) < 2:
        st.info("Não há ativos suficientes com dados para comparar.")
        return

    alinhado, descartados = alinhar_fechamentos(fechamentos)
    if len(alinhado) <= MIN_DIAS_PARA_ANALISE:
        st.warning(
            f"Só há {len(alinhado)} dias em comum entre esses ativos, e são necessários "
            f"mais de {MIN_DIAS_PARA_ANALISE}. Tente um período mais longo ou outros ativos."
        )
        return

    mostrar_grafico(
        graficos.criar_grafico_comparacao(
            rebasear_para_100(alinhado), principal, NOMES_AMIGAVEIS
        )
    )
    st.markdown("**Números no mesmo período**")
    st.dataframe(
        formatar_tabela_comparativa(
            montar_tabela_comparativa(alinhado, taxa_livre_de_risco)
        ),
        width="stretch",
    )
    st.caption(
        f"Comparação feita em {len(alinhado)} dias em comum. "
        f"{descartados} dias foram descartados porque algum ativo não tinha preço neles "
        "(feriados diferentes), sem preencher nem estimar nada. Por isso os números daqui podem "
        "diferir um pouco dos das outras abas, que usam todos os dias do ativo. "
        "As moedas diferentes "
        "(R\\$ e US\\$) não atrapalham, porque comparamos a variação percentual, não os preços."
    )


def escolher_estrategia():
    """Menu da estratégia e controles dos parâmetros, gerados a partir do registro."""
    nome = st.selectbox(
        "Estratégia",
        list(ESTRATEGIAS),
        format_func=lambda n: f"{ESTRATEGIAS[n].grupo} · {n}",
    )
    parametros = {}
    if ESTRATEGIAS[nome].parametros:
        colunas = st.columns(min(len(ESTRATEGIAS[nome].parametros), 3))
        for posicao, p in enumerate(ESTRATEGIAS[nome].parametros):
            coluna = colunas[posicao % len(colunas)]
            chave = f"parametro_{nome}_{p.nome}"
            if p.opcoes:
                parametros[p.nome] = coluna.selectbox(
                    p.rotulo,
                    p.opcoes,
                    index=p.opcoes.index(p.padrao),
                    key=chave,
                    help=p.ajuda or None,
                )
            else:
                parametros[p.nome] = coluna.slider(
                    p.rotulo,
                    p.minimo,
                    p.maximo,
                    p.padrao,
                    p.passo,
                    key=chave,
                    help=p.ajuda or None,
                )
    return nome, parametros


def _opcao_com_valor(
    coluna, chave, rotulo, rotulo_do_valor, padrao, minimo, maximo, termo
):
    """Uma caixa para ligar a proteção e, se ligada, o campo do valor. Devolve o valor ou None."""
    if not coluna.checkbox(rotulo, key=f"liga_{chave}", help=ajuda_do(termo)):
        return None
    return coluna.number_input(
        rotulo_do_valor,
        min_value=minimo,
        max_value=maximo,
        value=padrao,
        step=0.5,
        key=f"valor_{chave}",
    )


def escolher_protecoes():
    """Controles das proteções de risco (todas desligadas por padrão)."""
    with st.expander("Proteções de risco (opcional)"):
        st.caption(
            "Uma camada extra por cima da estratégia. Depois de um stop, a estratégia só volta "
            "a comprar quando mandar sair e depois entrar de novo (um sinal novo)."
        )
        col1, col2, col3 = st.columns(3)
        stop_loss = _opcao_com_valor(
            col1,
            "stop_loss",
            "Stop-loss",
            "Sair se cair (%)",
            8.0,
            1.0,
            50.0,
            "Stop-loss",
        )
        take_profit = _opcao_com_valor(
            col2,
            "take_profit",
            "Take-profit",
            "Sair se subir (%)",
            15.0,
            1.0,
            200.0,
            "Take-profit",
        )
        stop_movel = _opcao_com_valor(
            col3,
            "stop_movel",
            "Stop móvel",
            "Sair se cair da máxima (%)",
            10.0,
            1.0,
            50.0,
            "Stop móvel",
        )
        col4, col5, col6 = st.columns(3)
        stop_atr = _opcao_com_valor(
            col4,
            "stop_atr",
            "Stop por ATR",
            "Distância (x ATR)",
            2.0,
            0.5,
            6.0,
            "Stop por ATR",
        )
        risco = None
        if stop_atr is not None:
            risco = _opcao_com_valor(
                col5,
                "risco",
                "Risco por operação",
                "Capital arriscado (%)",
                1.0,
                0.5,
                10.0,
                "Risco por operação",
            )
        alvo = _opcao_com_valor(
            col6,
            "alvo_vol",
            "Alvo de volatilidade",
            "Volatilidade anual (%)",
            15.0,
            5.0,
            50.0,
            "Alvo de volatilidade",
        )
        espera = st.selectbox(
            "Depois de um stop, voltar a comprar...",
            list(ESPERAS_DEPOIS_DO_STOP),
            key="espera_depois_do_stop",
            help="Estratégias que nunca mandam sair (como comprar e segurar) só voltam se "
            "houver uma espera.",
        )
    return Protecoes(
        stop_loss=None if stop_loss is None else stop_loss / 100,
        take_profit=None if take_profit is None else take_profit / 100,
        stop_movel=None if stop_movel is None else stop_movel / 100,
        stop_atr=stop_atr,
        risco_por_operacao=None if risco is None else risco / 100,
        alvo_de_volatilidade=None if alvo is None else alvo / 100,
        dias_de_espera=ESPERAS_DEPOIS_DO_STOP[espera],
    )


@st.cache_data(show_spinner="Testando as combinações de parâmetros...")
def calcular_candidatos(dados, nome, candidatos, custo, protecoes):
    return calcular_retornos_dos_candidatos(dados, nome, candidatos, custo, protecoes)


def _texto_dos_parametros(parametros, rotulos):
    if not parametros:
        return "nenhum (ficou em caixa)"
    return ", ".join(f"{rotulos.get(k, k)} = {v}" for k, v in parametros.items())


def _curva_a_partir_de(retorno):
    return (1 + retorno).cumprod()


def secao_validacao(
    dados,
    nome,
    parametros,
    custo,
    protecoes,
    taxa_livre_de_risco,
    retorno_do_usuario,
    retorno_de_referencia,
    capital_inicial,
    operacoes,
    posicao_desejada,
):
    """Treino/teste, walk-forward e mapa de parâmetros: o resultado se sustenta fora do passado?"""
    st.divider()
    st.subheader("Isto se sustenta? Validação fora da amostra")
    st.caption(
        "Um backtest sempre parece bom quando os parâmetros foram escolhidos olhando os "
        "mesmos dados. Aqui a escolha é feita num pedaço do histórico e conferida em outro."
    )
    numericos = parametros_numericos(nome)
    if not numericos:
        st.info(
            "Esta estratégia não tem números para ajustar, então não há o que validar."
        )
        return
    rotulos = {p.nome: p.rotulo for p in numericos}
    livres = st.multiselect(
        "Parâmetros que podem variar na validação (até 2)",
        [p.nome for p in numericos],
        default=[p.nome for p in numericos][:2],
        format_func=lambda n: rotulos[n],
        max_selections=2,
        key=f"validacao_livres_{nome}",
        help="O app testa vários valores destes parâmetros. Os outros ficam como você "
        "configurou acima.",
    )
    if not livres:
        st.info("Escolha pelo menos um parâmetro para variar.")
        return
    candidatos = montar_candidatos(nome, parametros, livres)
    try:
        retornos, validos = calcular_candidatos(
            dados, nome, candidatos, custo, protecoes
        )
    except ValueError as erro:
        st.error(str(erro))
        return
    st.caption(f"{len(validos)} combinações testadas.")

    def sharpe(r):
        return ind.calcular_indice_sharpe(r, taxa_livre_de_risco)

    aba_tt, aba_wf, aba_mapa, aba_acaso, aba_sorte = st.tabs(
        [
            "Treino e teste",
            "Walk-forward",
            "Mapa de parâmetros",
            "Monte Carlo e acaso",
            "Sorte na escolha",
        ]
    )

    with aba_tt:
        fracao = st.slider(
            "Parte do histórico usada para escolher (treino)",
            50,
            90,
            70,
            5,
            format="%d%%",
            key=f"validacao_fracao_{nome}",
            help=ajuda_do("Treino e teste"),
        )
        try:
            corte = data_de_corte(retornos.index, fracao / 100)
            tt = avaliar_treino_e_teste(retornos, validos, corte, taxa_livre_de_risco)
        except ValueError as erro:
            st.info(str(erro))
        else:
            teste = retorno_do_usuario.loc[retorno_do_usuario.index >= corte]
            referencia = retorno_de_referencia.loc[retorno_de_referencia.index >= corte]
            st.markdown(
                f"Treino até **{(corte - pd.Timedelta(days=1)):%d/%m/%Y}**; teste a partir de "
                f"**{corte:%d/%m/%Y}**. Melhor combinação no treino: "
                f"**{_texto_dos_parametros(tt.melhor_do_treino, rotulos)}**."
            )
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(
                "Sharpe da melhor, no treino",
                formatar_metrica("Sharpe", tt.sharpe_no_treino),
                help="O número bonito: foi escolhido justamente por ser o maior.",
            )
            c2.metric(
                "Esta mesma, no teste",
                formatar_metrica("Sharpe", tt.sharpe_no_teste),
                help="O número de verdade: período que a escolha nunca viu.",
            )
            c3.metric(
                "Sua configuração, no teste",
                formatar_metrica("Sharpe", sharpe(teste)),
            )
            c4.metric(
                "Comprar e segurar, no teste",
                formatar_metrica("Sharpe", sharpe(referencia)),
            )
            if tt.sharpe_no_teste < tt.sharpe_no_treino:
                st.caption(
                    "O Sharpe caiu do treino para o teste. Uma queda é normal: parte do "
                    "resultado do treino foi sorte. Quanto maior a queda, mais a escolha "
                    "estava ajustada ao passado."
                )
            else:
                st.caption(
                    "O Sharpe subiu do treino para o teste. Isso quase sempre quer dizer que "
                    "o período de teste foi mais favorável (por exemplo, uma tendência de "
                    "alta), e não que a estratégia ficou melhor. Compare com comprar e segurar."
                )
            curvas = {
                "Melhor do treino": _curva_a_partir_de(tt.retorno_no_teste),
                "Sua configuração": _curva_a_partir_de(teste),
                "Comprar e segurar": _curva_a_partir_de(referencia),
            }
            mostrar_grafico(
                graficos.criar_grafico_curvas_de_capital(
                    curvas, capital_inicial, destaque="Melhor do treino"
                )
            )

    with aba_wf:
        col_a, col_b = st.columns(2)
        dias_treino = col_a.slider(
            "Janela de treino (dias úteis)",
            126,
            1008,
            504,
            21,
            key=f"validacao_treino_{nome}",
            help=ajuda_do("Walk-forward"),
        )
        dias_teste = col_b.slider(
            "Janela de teste (dias úteis)",
            21,
            252,
            126,
            21,
            key=f"validacao_teste_{nome}",
        )
        try:
            wf = executar_walk_forward(
                retornos, validos, dias_treino, dias_teste, taxa_livre_de_risco
            )
        except ValueError as erro:
            st.info(str(erro))
        else:
            fora = wf.retorno_fora_da_amostra
            referencia = retorno_de_referencia.loc[fora.index]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(
                "Sharpe fora da amostra",
                formatar_metrica("Sharpe", wf.sharpe_fora_da_amostra),
            )
            c2.metric(
                "Sharpe médio no treino",
                formatar_metrica("Sharpe", wf.sharpe_medio_no_treino),
            )
            c3.metric(
                "Eficiência",
                formatar_metrica("Sharpe", wf.eficiencia),
                help="Sharpe de fora dividido pelo Sharpe médio de treino. Perto de 1: o "
                "ajuste se sustentou. Perto de 0 ou negativo: era sorte.",
            )
            c4.metric(
                "Comprar e segurar, no mesmo período",
                formatar_metrica("Sharpe", sharpe(referencia)),
            )
            mostrar_grafico(
                graficos.criar_grafico_curvas_de_capital(
                    {
                        "Walk-forward (só dias de teste)": _curva_a_partir_de(fora),
                        "Comprar e segurar": _curva_a_partir_de(referencia),
                    },
                    capital_inicial,
                    destaque="Walk-forward (só dias de teste)",
                )
            )
            janelas = wf.janelas.copy()
            for coluna in ("Começo do treino", "Começo do teste", "Fim do teste"):
                janelas[coluna] = janelas[coluna].dt.strftime("%d/%m/%Y")
            janelas["Parâmetros escolhidos"] = [
                _texto_dos_parametros(p, rotulos)
                for p in janelas["Parâmetros escolhidos"]
            ]
            for coluna in ("Sharpe no treino", "Sharpe no teste"):
                janelas[coluna] = [
                    formatar_metrica("Sharpe", v) for v in janelas[coluna]
                ]
            with st.expander(f"Ver as {len(janelas)} janelas"):
                st.dataframe(janelas, width="stretch", hide_index=True)

    with aba_mapa:
        st.caption(
            "Sharpe de cada combinação no período inteiro. Procure uma região grande e "
            "verde, não um quadradinho isolado."
        )
        segundo = livres[1] if len(livres) > 1 else None
        mapa = montar_mapa_de_sharpe(
            retornos, validos, livres[0], segundo, taxa_livre_de_risco
        )
        mostrar_grafico(
            graficos.criar_mapa_de_calor_de_parametros(
                mapa,
                rotulos[livres[0]],
                rotulos[segundo] if segundo else None,
                escolhido=(
                    parametros[livres[0]],
                    parametros[segundo] if segundo else "",
                ),
            )
        )
        valores = pd.Series(mapa.to_numpy(dtype=float).ravel()).dropna()
        if not valores.empty:
            st.caption(
                f"Mediana do Sharpe na grade: {formatar_metrica('Sharpe', valores.median())}; "
                f"melhor: {formatar_metrica('Sharpe', valores.max())}. "
                f"{formatar_pct((valores > 0).mean())} das combinações têm Sharpe positivo. "
                "O quadrado azul marca a sua configuração atual (se ela estiver na grade)."
            )

    with aba_acaso:
        st.markdown("**Monte Carlo: e se as operações tivessem vindo em outra ordem?**")
        st.caption(ajuda_do("Monte Carlo (das operações)"))
        if len(operacoes) < 5:
            st.info(
                "Com menos de 5 operações, o Monte Carlo não diz nada. Tente um período maior ou outros parâmetros."
            )
        else:
            mc = simular_monte_carlo(operacoes["retorno"])
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(
                "Retorno típico (mediana)",
                formatar_pct(
                    float(pd.Series(mc.retornos_finais).median()), com_sinal=True
                ),
            )
            c2.metric(
                "Faixa de 90% dos casos",
                f"{formatar_pct(float(pd.Series(mc.retornos_finais).quantile(0.05)), com_sinal=True)} a "
                f"{formatar_pct(float(pd.Series(mc.retornos_finais).quantile(0.95)), com_sinal=True)}",
            )
            c3.metric("Chance de prejuízo", formatar_pct(mc.probabilidade_de_prejuizo))
            c4.metric(
                "Queda máxima no pior caso comum",
                formatar_pct(float(pd.Series(mc.quedas_maximas).quantile(0.05))),
                help="Em 95% das simulações a maior queda foi menor que esta.",
            )
            mostrar_grafico(
                graficos.criar_grafico_cone_monte_carlo(
                    mc.percentis_da_curva, mc.curva_observada
                )
            )
        st.divider()
        st.markdown(
            "**Teste contra o acaso: a regra bate posições sem relação com o preço?**"
        )
        st.caption(ajuda_do("Teste contra o acaso"))
        try:
            teste = testar_contra_o_acaso(
                dados["Close"], posicao_desejada, custo, taxa_livre_de_risco
            )
        except ValueError as erro:
            st.info(str(erro))
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric(
                "Sharpe da estratégia", formatar_metrica("Sharpe", teste.sharpe_real)
            )
            c2.metric(
                "Sharpe mediano ao acaso",
                formatar_metrica(
                    "Sharpe", float(pd.Series(teste.sharpes_ao_acaso).median())
                ),
            )
            c3.metric(
                "p-valor",
                formatar_metrica("Sharpe", teste.p_valor),
                help="Fatia das versões ao acaso que fez igual ou melhor. Abaixo de 0,05 "
                "é difícil atribuir o resultado só ao acaso.",
            )
            mostrar_grafico(
                graficos.criar_histograma_do_acaso(
                    teste.sharpes_ao_acaso, teste.sharpe_real
                )
            )
            if teste.p_valor >= 0.05:
                st.caption(
                    "Muitas versões ao acaso fizeram igual ou melhor. Em ativos que subiram "
                    "bastante, quase qualquer posição comprada ganha, e a regra não se destaca."
                )

    with aba_sorte:
        st.markdown(
            "**Sharpe deflacionado: o melhor de muitas tentativas vale quanto?**"
        )
        st.caption(ajuda_do("Sharpe deflacionado"))
        extras = st.number_input(
            "Outras combinações que você já testou antes (opcional)",
            min_value=0,
            max_value=10_000,
            value=0,
            step=10,
            key=f"validacao_extras_{nome}",
            help="Cada combinação testada em outras estratégias ou ativos também conta como "
            "uma tentativa. Quanto mais tentativas, maior o Sharpe que só a sorte já daria.",
        )
        melhor_coluna = retornos.apply(
            lambda r: ind.calcular_indice_sharpe(r, taxa_livre_de_risco)
        ).idxmax()
        try:
            dsr = calcular_sharpe_deflacionado(
                retornos[melhor_coluna], retornos, int(extras), taxa_livre_de_risco
            )
        except ValueError as erro:
            st.info(str(erro))
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Tentativas contadas", f"{dsr.tentativas}")
            c2.metric(
                "Sharpe do melhor candidato",
                formatar_metrica("Sharpe", dsr.sharpe_anual),
            )
            c3.metric(
                "Sharpe que a sorte já daria",
                formatar_metrica("Sharpe", dsr.sharpe_anual_por_sorte),
            )
            c4.metric(
                "Chance de não ser sorte",
                formatar_pct(dsr.probabilidade),
                help="Probabilidade do Sharpe deflacionado. Acima de 95%: convincente.",
            )
            st.caption(
                f"Melhor candidato: {_texto_dos_parametros(validos[int(melhor_coluna)], rotulos)}. "
                "Este Sharpe usa a média dos retornos diários, por isso pode diferir um pouco "
                "do Sharpe mostrado nas outras telas."
            )
        st.divider()
        st.markdown("**PBO: escolher a melhor do treino costuma funcionar?**")
        st.caption(ajuda_do("PBO (probabilidade de overfitting)"))
        try:
            pbo = calcular_pbo(retornos)
        except ValueError as erro:
            st.info(str(erro))
        else:
            c1, c2 = st.columns(2)
            c1.metric("PBO", formatar_pct(pbo.probabilidade))
            c2.metric("Divisões treino/teste testadas", f"{pbo.combinacoes}")
            st.caption(
                "Abaixo de 50%, a melhor do treino tende a continuar acima da mediana "
                "fora dele. Perto ou acima de 50%, a escolha vira sorte. Combinações da "
                "mesma estratégia são parecidas, então o PBO costuma ser baixo: ele mede a "
                "escolha entre variações, não se a estratégia vale a pena."
            )


def _experimento_aporte(dados):
    st.markdown("**Aporte único ou parcelado?**")
    st.caption(
        "Investir tudo de uma vez ou dividir em parcelas mensais no mesmo ativo? "
        "O dinheiro que espera para ser investido fica parado, sem render."
    )
    fechamento = dados["Close"]
    c1, c2, c3 = st.columns(3)
    total = c1.number_input(
        "Valor total (R\\$)",
        min_value=100.0,
        value=12_000.0,
        step=1_000.0,
        key="exp_total",
    )
    parcelas = c2.slider("Parcelas mensais", 2, 24, 12, key="exp_parcelas")
    horizonte = c3.slider(
        "Horizonte das janelas (dias úteis)", 63, 504, 252, 21, key="exp_horizonte"
    )
    try:
        caminho = simular_aporte_unico_e_dca(fechamento, total, parcelas)
        janelas = comparar_janelas(fechamento, parcelas, horizonte)
    except ValueError as erro:
        st.info(
            f"{erro} Tente menos parcelas, um horizonte maior ou um período mais longo."
        )
        return
    resumo = resumir_janelas(janelas)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric(
        "Aporte único vence em",
        formatar_pct(resumo["Aporte único vence"]),
        help="Fatia das datas de início em que investir tudo de uma vez terminou na frente.",
    )
    k2.metric(
        "Mediana: aporte único",
        formatar_pct(resumo["Mediana do aporte único"], com_sinal=True),
    )
    k3.metric(
        "Mediana: parcelado",
        formatar_pct(resumo["Mediana do parcelado"], com_sinal=True),
    )
    k4.metric(
        "Pior caso (único | parcelado)",
        f"{formatar_pct(resumo['Pior caso do aporte único'])} | "
        f"{formatar_pct(resumo['Pior caso do parcelado'])}",
    )
    st.caption(
        f"{int(resumo['Janelas'])} datas de início, cada uma acompanhada por {horizonte} dias úteis. "
        "As janelas se sobrepõem, então não são testes independentes: com poucos anos de dados, "
        "pense nelas como uma ilustração. "
        + (ajuda_do("DCA (aportes parcelados)") or "")
    )
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            {n: caminho[n] / total for n in caminho.columns},
            total,
            destaque="Aporte único",
        )
    )
    mostrar_grafico(graficos.criar_grafico_diferenca_das_janelas(janelas["Diferença"]))


def _experimento_rebalanceamento(dados, periodo, taxa_livre_de_risco):
    st.markdown("**Rebalanceamento: vale a pena voltar aos pesos?**")
    st.caption(ajuda_do("Rebalanceamento"))
    c1, c2, c3, c4 = st.columns(4)
    segundo = c1.text_input("Segundo ativo", value="^GSPC", key="exp_segundo")
    peso = c2.slider("Peso do ativo principal (%)", 10, 90, 50, 5, key="exp_peso")
    faixa = c3.slider("Faixa (pontos percentuais)", 1, 20, 5, key="exp_faixa")
    custo_percentual = c4.number_input(
        "Custo por operação (%)",
        0.0,
        2.0,
        CUSTO_PADRAO_POR_OPERACAO * 100,
        0.01,
        format="%.2f",
        key="exp_custo_rebalancear",
    )
    ticker_segundo = normalizar_ticker(segundo)
    if not ticker_segundo:
        st.info("Digite o segundo ativo.")
        return
    try:
        outro = carregar_dados(ticker_segundo, periodo)["Close"]
    except DadosIndisponiveisError as erro:
        st.warning(str(erro))
        return
    principal_nome = "Principal"
    alinhado, _ = alinhar_fechamentos(
        {principal_nome: dados["Close"], ticker_segundo: outro}
    )
    if len(alinhado) < 60 or list(alinhado.columns) != [principal_nome, ticker_segundo]:
        st.warning("Não há dias suficientes em comum entre os dois ativos.")
        return
    resultados = {}
    for regra in REGRAS_DE_REBALANCEAMENTO:
        resultados[regra if regra != "Por faixa" else f"Por faixa ({faixa} pontos)"] = (
            simular_rebalanceamento(
                alinhado, peso / 100, regra, faixa / 100, custo_percentual / 100
            )
        )
    linhas = {}
    for rotulo, r in resultados.items():
        numeros = resumir_desempenho(r.retorno, None, None, taxa_livre_de_risco)
        linhas[rotulo] = {
            "Retorno total": formatar_metrica(
                "Retorno total", numeros["Retorno total"]
            ),
            "Índice de Sharpe": formatar_metrica("Sharpe", numeros["Índice de Sharpe"]),
            "Maior queda": formatar_metrica("Maior queda", numeros["Maior queda"]),
            "Rebalanceamentos": str(r.rebalanceamentos),
            "Giro (x o capital)": f"{r.giro:.1f}".replace(".", ","),
        }
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            {n: r.curva_de_capital for n, r in resultados.items()},
            10_000.0,
            destaque=next(iter(resultados)),
        )
    )
    st.dataframe(pd.DataFrame(linhas).T, width="stretch")
    st.caption(
        f"Carteira com {peso}% no ativo principal e {100 - peso}% em {ticker_segundo}. "
        "Sem rebalancear, quem sobe vai ficando com mais peso. Rebalancear costuma reduzir "
        "o risco, mas cada ajuste custa; o efeito no retorno depende de os ativos "
        "se alternarem na liderança."
    )


def _experimento_noite_e_dia(dados, taxa_livre_de_risco):
    st.markdown("**Noite × dia: de onde vem o retorno?**")
    st.caption(ajuda_do("Retorno da noite e do dia"))
    try:
        partes = separar_noite_e_dia(dados)
    except ValueError as erro:
        st.info(str(erro))
        return
    custo_percentual = st.number_input(
        "Custo por operação (%) para quem só fica comprado à noite",
        0.0,
        2.0,
        CUSTO_PADRAO_POR_OPERACAO * 100,
        0.01,
        format="%.2f",
        key="exp_custo_noite",
    )
    resumo = resumir_noite_e_dia(partes, taxa_livre_de_risco)
    tabela = pd.DataFrame(
        {
            rotulo: {
                "Retorno total": formatar_metrica(
                    "Retorno total", linha["Retorno total"]
                ),
                "Média por dia": formatar_pct(linha["Média por dia"], com_sinal=True),
                "Índice de Sharpe": formatar_metrica(
                    "Sharpe", linha["Índice de Sharpe"]
                ),
                "Dias de alta": formatar_pct(linha["Dias de alta"]),
            }
            for rotulo, linha in resumo.iterrows()
        }
    )
    st.dataframe(tabela, width="stretch")
    liquido = calcular_retorno_da_noite_com_custo(partes, custo_percentual / 100)
    curvas = {
        "Total (comprar e segurar)": (
            1 + (1 + partes["Noite"]) * (1 + partes["Dia"]) - 1
        ).cumprod(),
        "Só a noite": (1 + partes["Noite"]).cumprod(),
        "Só o dia": (1 + partes["Dia"]).cumprod(),
        "Só a noite, com custos": (1 + liquido).cumprod(),
    }
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            curvas, 10_000.0, destaque="Total (comprar e segurar)"
        )
    )
    st.caption(
        "Os dados vêm do ativo e do período escolhidos lá em cima. "
        "A curva com custos mostra o que sobra de quem compra no fechamento e vende na abertura "
        "todo dia: são duas operações por dia."
    )


def _experimento_virada_do_mes(dados, taxa_livre_de_risco):
    st.markdown("**Virada do mês: comprado só em torno da troca de mês**")
    st.caption(ajuda_do("Virada do mês"))
    c1, c2, c3 = st.columns(3)
    antes = c1.slider("Últimos dias do mês", 0, 5, 1, key="exp_antes")
    depois = c2.slider("Primeiros dias do mês seguinte", 0, 5, 3, key="exp_depois")
    custo_percentual = c3.number_input(
        "Custo por operação (%)",
        0.0,
        2.0,
        CUSTO_PADRAO_POR_OPERACAO * 100,
        0.01,
        format="%.2f",
        key="exp_custo_virada",
    )
    fechamento = dados["Close"]
    try:
        resultado, marcados = simular_virada_do_mes(
            fechamento, antes, depois, custo_percentual / 100
        )
        dentro_e_fora = comparar_dentro_e_fora(
            ind.calcular_retorno_diario(fechamento).fillna(0.0), marcados
        )
    except ValueError as erro:
        st.info(str(erro))
        return
    referencia = executar_backtest(
        fechamento, pd.Series(1.0, index=fechamento.index), custo_percentual / 100
    )
    numeros = resumir_desempenho(
        resultado.retorno, resultado.posicao, resultado.operacoes, taxa_livre_de_risco
    )
    numeros_referencia = resumir_desempenho(
        referencia.retorno,
        referencia.posicao,
        referencia.operacoes,
        taxa_livre_de_risco,
    )
    cartoes = st.columns(4)
    for coluna, metrica in zip(
        cartoes, ["Retorno total", "Índice de Sharpe", "Maior queda", "Exposição média"]
    ):
        coluna.metric(
            metrica,
            formatar_metrica(metrica, numeros[metrica]),
            delta=f"{formatar_metrica(metrica, numeros_referencia[metrica])} em comprar e segurar",
            delta_color="off",
            delta_arrow="off",
        )
    desejada = marcados.shift(-1, fill_value=False).astype(float)
    try:
        acaso = testar_contra_o_acaso(
            fechamento, desejada, custo_percentual / 100, taxa_livre_de_risco
        )
        st.caption(
            f"Teste contra o acaso: p-valor de {formatar_metrica('Sharpe', acaso.p_valor)}. "
            "Abaixo de 0,05, poucas posições sem relação com o preço fariam igual."
        )
    except ValueError as erro:
        st.caption(str(erro))
    st.caption(
        f"Média por dia dentro da virada: {formatar_pct(dentro_e_fora['Média por dia (dentro)'], com_sinal=True)}; "
        f"fora: {formatar_pct(dentro_e_fora['Média por dia (fora)'], com_sinal=True)}. "
        f"({int(dentro_e_fora['Dias dentro'])} dias dentro e {int(dentro_e_fora['Dias fora'])} fora.)"
    )
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            {
                "Só na virada do mês": resultado.curva_de_capital,
                "Comprar e segurar": referencia.curva_de_capital,
            },
            10_000.0,
            destaque="Só na virada do mês",
        )
    )


def secao_experimentos(dados, periodo, taxa_livre_de_risco):
    st.subheader("Experimentos: perguntas clássicas com os seus dados")
    st.caption(
        "Cada experimento responde com o ativo e o período escolhidos lá em cima. "
        "O resultado vale para eles, não para o mercado em geral."
    )
    aba_aporte, aba_rebalancear, aba_noite, aba_virada = st.tabs(
        ["Aporte único × parcelado", "Rebalanceamento", "Noite × dia", "Virada do mês"]
    )
    with aba_aporte:
        _experimento_aporte(dados)
    with aba_rebalancear:
        _experimento_rebalanceamento(dados, periodo, taxa_livre_de_risco)
    with aba_noite:
        _experimento_noite_e_dia(dados, taxa_livre_de_risco)
    with aba_virada:
        _experimento_virada_do_mes(dados, taxa_livre_de_risco)


CORES_DOS_REGIMES = {
    "Calmo": graficos.COR_ALTA,
    "Agitado": graficos.COR_QUEDA,
    "Alta": graficos.COR_ALTA,
    "Baixa": graficos.COR_QUEDA,
}


def _escolher_regimes(chave, fechamento):
    """Controles do tipo de regime; devolve (regimes, nomes possíveis, descrição)."""
    criterio = st.radio(
        "Como separar os regimes",
        ["Volatilidade (calmo × agitado)", "Tendência (alta × baixa)"],
        horizontal=True,
        key=f"{chave}_criterio",
        help=ajuda_do("Regime de mercado"),
    )
    if criterio.startswith("Volatilidade"):
        c1, c2 = st.columns(2)
        janela = c1.slider(
            "Janela da volatilidade (dias)", 5, 60, 20, 1, key=f"{chave}_jan_vol"
        )
        percentil = c2.slider(
            "Agitado acima do percentil",
            0.3,
            0.9,
            0.5,
            0.05,
            key=f"{chave}_percentil",
            help="0,5 = a mediana: metade dos dias, em média, é chamada de agitada.",
        )
        regimes = classificar_regimes_de_volatilidade(fechamento, janela, percentil)
        return regimes, REGIMES_DE_VOLATILIDADE, f"volatilidade de {janela} dias"
    janela = st.slider("Média móvel (dias)", 20, 300, 200, 10, key=f"{chave}_jan_tend")
    regimes = classificar_regimes_de_tendencia(fechamento, janela)
    return regimes, REGIMES_DE_TENDENCIA, f"preço contra a média de {janela} dias"


def _tabela_de_regimes(resumo):
    exibicao = pd.DataFrame(index=resumo.index)
    exibicao["Dias"] = resumo["Dias"].astype(int)
    exibicao["% do tempo"] = [formatar_pct(v) for v in resumo["% do tempo"]]
    exibicao["Retorno médio por dia"] = [
        formatar_pct(v, com_sinal=True) for v in resumo["Retorno médio por dia"]
    ]
    exibicao["Retorno anualizado"] = [
        formatar_pct(v, com_sinal=True) for v in resumo["Retorno anualizado"]
    ]
    exibicao["Volatilidade anual"] = [
        formatar_pct(v) for v in resumo["Volatilidade anual"]
    ]
    exibicao["Índice de Sharpe"] = [
        formatar_metrica("Sharpe", v) for v in resumo["Índice de Sharpe"]
    ]
    exibicao["Pior dia"] = [formatar_pct(v) for v in resumo["Pior dia"]]
    return exibicao


def _regimes_do_ativo(dados, taxa_livre_de_risco):
    st.markdown("**Como o ativo se comporta em cada regime**")
    fechamento = dados["Close"]
    regimes, nomes, descricao = _escolher_regimes("reg_ativo", fechamento)
    try:
        resumo = resumir_por_regime(
            ind.calcular_retorno_diario(fechamento).fillna(0.0),
            regimes,
            taxa_livre_de_risco,
        )
    except ValueError as erro:
        st.info(str(erro))
        return
    mostrar_grafico(
        graficos.criar_grafico_regimes(
            fechamento, regimes, {n: CORES_DOS_REGIMES[n] for n in nomes}
        )
    )
    st.dataframe(_tabela_de_regimes(resumo), width="stretch")
    st.caption(
        f"Regime pelo critério: {descricao}. Cada dia é contado no regime da véspera, "
        "que é o que dava para saber antes do pregão. Se a volatilidade for bem maior no "
        "regime agitado e o retorno não compensar, fugir dele pode valer a pena; a próxima "
        "aba testa isso com uma estratégia."
    )


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


def _filtro_por_regime(dados, taxa_livre_de_risco):
    st.markdown("**Operar só em certos regimes**")
    fechamento = dados["Close"]
    nome = _escolher_estrategia_simples("reg_filtro")
    custo = _custo_do_experimento("reg_filtro")
    regimes, nomes, descricao = _escolher_regimes("reg_filtro", fechamento)
    ficar_em = st.multiselect(
        "Ficar comprado nos regimes",
        list(nomes),
        default=[nomes[0]],
        key=f"reg_filtro_ficar_em_{nomes[0]}",
    )
    usar_variancia = st.checkbox(
        "Comparar também a variância gerida (posição menor quando a variância sobe)",
        key="reg_filtro_variancia",
        help=ajuda_do("Variância gerida"),
    )
    try:
        posicao = gerar_posicao(nome, dados)
        filtrada = filtrar_por_regime(posicao, regimes, tuple(ficar_em))
        rotulo_filtrado = f"{nome} só em {' e '.join(ficar_em).lower()}"
        resultados = {
            nome: executar_backtest(fechamento, posicao, custo),
            rotulo_filtrado: executar_backtest(fechamento, filtrada, custo),
        }
        if usar_variancia:
            resultados[f"{nome} com variância gerida"] = executar_backtest(
                fechamento, gerir_pela_variancia(fechamento, posicao), custo
            )
        if nome != ESTRATEGIA_DE_REFERENCIA:
            resultados[ESTRATEGIA_DE_REFERENCIA] = executar_backtest(
                fechamento, pd.Series(1.0, index=fechamento.index), custo
            )
    except ValueError as erro:
        st.info(str(erro))
        return
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            {n: r.curva_de_capital for n, r in resultados.items()},
            10_000.0,
            destaque=rotulo_filtrado,
        )
    )
    st.dataframe(
        _tabela_de_resultados(resultados, taxa_livre_de_risco), width="stretch"
    )
    st.caption(
        f"Regimes pelo critério: {descricao}. A decisão do fim do dia vale a partir do dia "
        "seguinte e os limites dos regimes usam só o passado. Filtrar costuma reduzir o risco "
        "e a exposição; se o Sharpe também melhora ou se só se perdeu retorno depende do "
        "ativo e do período, e uma única janela de dados não prova nada."
    )


def _disjuntor(dados, taxa_livre_de_risco):
    st.markdown("**Disjuntor de drawdown: se a estratégia cair demais, para**")
    st.caption(ajuda_do("Disjuntor de drawdown"))
    fechamento = dados["Close"]
    nome = _escolher_estrategia_simples("reg_disj")
    c1, c2, c3 = st.columns(3)
    limite = c1.slider("Dispara com queda de (%)", 3, 40, 15, 1, key="reg_disj_limite")
    pausa = c2.slider("Pausa (dias)", 1, 126, 21, 1, key="reg_disj_pausa")
    with c3:
        custo = _custo_do_experimento("reg_disj")
    try:
        posicao = gerar_posicao(nome, dados)
        disjuntor = aplicar_disjuntor_de_drawdown(
            fechamento, posicao, limite / 100, pausa, custo
        )
        com = executar_backtest(fechamento, disjuntor.posicao, custo)
        sem = executar_backtest(fechamento, posicao, custo)
        varredura = varrer_disjuntor(
            fechamento,
            posicao,
            [0.05, 0.10, 0.20, 0.30],
            [10, 21, 63],
            custo,
            taxa_livre_de_risco,
        )
    except ValueError as erro:
        st.info(str(erro))
        return
    rotulo_com = f"{nome} com disjuntor"
    resultados = {rotulo_com: com, f"{nome} sem disjuntor": sem}
    extras = {
        rotulo_com: {"Disparos": str(len(disjuntor.acionamentos))},
        f"{nome} sem disjuntor": {"Disparos": "0"},
    }
    mostrar_grafico(
        graficos.criar_grafico_disjuntor(
            {n: r.curva_de_capital for n, r in resultados.items()},
            10_000.0,
            rotulo_com,
            disjuntor.acionamentos,
        )
    )
    st.dataframe(
        _tabela_de_resultados(resultados, taxa_livre_de_risco, extras),
        width="stretch",
    )
    st.caption(
        f"O disjuntor ficou {disjuntor.dias_parado} dias travado em caixa. Depois da pausa "
        "o topo é refeito, senão ele dispararia de novo pela mesma queda."
    )
    with st.expander(
        "E se o limite e a pausa fossem outros? (cuidado: é pescar resultado)"
    ):
        exibicao = pd.DataFrame(index=varredura.index)
        exibicao["Retorno total"] = [
            formatar_pct(v, com_sinal=True) for v in varredura["Retorno total"]
        ]
        exibicao["Índice de Sharpe"] = [
            formatar_metrica("Sharpe", v) for v in varredura["Índice de Sharpe"]
        ]
        exibicao["Maior queda"] = [formatar_pct(v) for v in varredura["Maior queda"]]
        exibicao["Disparos"] = varredura["Acionamentos"].astype(int)
        st.dataframe(exibicao, width="stretch")
        st.caption(
            "São 13 linhas testadas no mesmo passado: escolher a melhor é o data snooping "
            "de que falamos na aba Backtest. Olhe o padrão (quanto a queda máxima diminui "
            "e quanto o retorno perde), não o campeão."
        )


def secao_regimes(dados, taxa_livre_de_risco):
    st.subheader("Regimes e disjuntor: o mercado muda de humor")
    st.caption(
        "O mesmo ativo tem fases calmas e fases agitadas. Aqui você vê como ele se "
        "comporta em cada uma, testa uma estratégia que só opera em certas fases e um "
        "disjuntor que a desliga depois de uma queda grande."
    )
    aba_ativo, aba_filtro, aba_disjuntor = st.tabs(
        ["Regimes do ativo", "Estratégia por regime", "Disjuntor de drawdown"]
    )
    with aba_ativo:
        _regimes_do_ativo(dados, taxa_livre_de_risco)
    with aba_filtro:
        _filtro_por_regime(dados, taxa_livre_de_risco)
    with aba_disjuntor:
        _disjuntor(dados, taxa_livre_de_risco)


@st.cache_data(show_spinner="Treinando o modelo (só com o passado de cada data)...")
def calcular_previsoes_do_sinal(dados, tipo, alvo, stop, prazo, mascara_bytes=None):
    """Treino com janela que expande; guardado em cache porque leva alguns segundos."""
    if tipo == "dia":
        conjunto = aprendizado.rotular_proximo_dia(dados)
    else:
        conjunto = aprendizado.rotular_barreira_tripla(dados, alvo, stop, prazo)
    mascara = None
    if mascara_bytes is not None:
        sinal = np.frombuffer(mascara_bytes, dtype=bool)
        mascara = sinal[conjunto.posicao]
    return conjunto, aprendizado.prever_fora_da_amostra(conjunto, mascara=mascara)


def _tabela_de_avaliacao(r):
    return pd.DataFrame(
        {
            "Modelo": [
                formatar_pct(r["Acurácia do modelo"]),
                formatar_metrica("Sharpe", r["AUC"]),
                formatar_metrica("Sharpe", r["Brier do modelo"]),
            ],
            "Previsão ingênua": [
                formatar_pct(r["Acurácia ingênua"]),
                "0,50",
                formatar_metrica("Sharpe", r["Brier ingênuo"]),
            ],
        },
        index=[
            "Acurácia (acertos)",
            "AUC (0,5 = acaso)",
            "Erro de Brier (menor é melhor)",
        ],
    )


def _veredito(r):
    z = r["Diferença em erros-padrão"]
    if z >= 2:
        return (
            f"O modelo acertou {formatar_pct(r['Acurácia do modelo'] - r['Acurácia ingênua'], com_sinal=True)} "
            f"a mais que a previsão ingênua, a {formatar_metrica('Sharpe', z)} erros-padrão. "
            "Isso é raro: desconfie antes de comemorar e confira em outro período e outro ativo."
        )
    return (
        f"A diferença para a previsão ingênua foi de {formatar_metrica('Sharpe', z)} "
        "erros-padrão: dentro do que o acaso produz. O modelo não mostrou saber algo "
        "que o preço passado não esconda."
    )


def _ml_sinal_do_dia(dados, taxa_livre_de_risco):
    st.markdown("**Um modelo consegue prever se amanhã sobe?**")
    st.caption(
        "Regressão logística com 8 variáveis simples (retornos, volatilidade, amplitude, "
        "volume, distância da média). Treina só com o passado de cada data, numa janela que "
        "cresce, e é comparada com a previsão ingênua: sempre apostar no lado mais comum."
    )
    c1, c2 = st.columns(2)
    limiar = c1.slider(
        "Compra se a probabilidade passar de", 0.45, 0.65, 0.5, 0.01, key="ml_limiar"
    )
    with c2:
        custo = _custo_do_experimento("ml_dia")
    try:
        conjunto, previsoes = calcular_previsoes_do_sinal(dados, "dia", 0, 0, 0)
        r = aprendizado.avaliar_previsoes(conjunto.y, previsoes, limiar)
    except ValueError as erro:
        st.info(str(erro))
        return
    st.dataframe(_tabela_de_avaliacao(r), width="stretch")
    st.caption(f"{int(r['Previsões'])} previsões fora da amostra. " + _veredito(r))

    fechamento = dados["Close"]
    posicao = aprendizado.posicao_a_partir_das_probabilidades(
        previsoes["p"], fechamento.index, limiar
    )
    inicio = previsoes["p"].first_valid_index()
    teste = fechamento.loc[inicio:]
    resultados = {
        "Modelo (sinal do dia)": executar_backtest(teste, posicao.loc[inicio:], custo),
        ESTRATEGIA_DE_REFERENCIA: executar_backtest(
            teste, pd.Series(1.0, index=teste.index), custo
        ),
    }
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            {n: x.curva_de_capital for n, x in resultados.items()},
            10_000.0,
            destaque="Modelo (sinal do dia)",
        )
    )
    st.dataframe(
        _tabela_de_resultados(resultados, taxa_livre_de_risco), width="stretch"
    )
    try:
        acaso = testar_contra_o_acaso(
            teste, posicao.loc[inicio:], custo, taxa_livre_de_risco
        )
        st.caption(
            f"Teste contra o acaso: p-valor de {formatar_metrica('Sharpe', acaso.p_valor)}. "
            "Abaixo de 0,05, poucas posições sem relação com o preço fariam igual."
        )
    except ValueError as erro:
        st.caption(str(erro))
    st.caption(
        "Só vale o período de teste (depois do primeiro treino). Comprar e segurar é medido "
        "no mesmo período, para a comparação ser justa."
    )


def _ml_barreira_e_meta(dados, taxa_livre_de_risco):
    st.markdown("**Barreira tripla, validação com expurgo e meta-rotulagem**")
    st.caption(ajuda_do("Barreira tripla"))
    c1, c2, c3 = st.columns(3)
    alvo = c1.slider("Alvo (%)", 1, 10, 3, 1, key="ml_alvo")
    stop = c2.slider("Stop (%)", 1, 10, 3, 1, key="ml_stop")
    prazo = c3.slider("Prazo (dias)", 3, 40, 10, 1, key="ml_prazo")
    try:
        conjunto, previsoes = calcular_previsoes_do_sinal(
            dados, "barreira", alvo / 100, stop / 100, prazo
        )
        com = aprendizado.validar_com_expurgo(conjunto, 5, prazo, expurgar=True)
        sem = aprendizado.validar_com_expurgo(conjunto, 5, prazo, expurgar=False)
        r = aprendizado.avaliar_previsoes(conjunto.y, previsoes)
    except ValueError as erro:
        st.info(str(erro))
        return
    st.markdown(
        "*Quanto o modelo acerta se bate o alvo antes do stop (treino que expande)*"
    )
    st.dataframe(_tabela_de_avaliacao(r), width="stretch")
    st.caption(
        f"Em {formatar_pct(r['Fração de 1'])} dos dias o alvo veio antes do stop. "
        + _veredito(r)
    )
    st.markdown("*Validação cruzada em 5 blocos, com e sem expurgo*")
    st.dataframe(
        pd.DataFrame(
            {
                "k-fold comum": [
                    formatar_pct(sem["Acurácia do modelo"]),
                    formatar_metrica("Sharpe", sem["AUC"]),
                ],
                "Com expurgo e embargo": [
                    formatar_pct(com["Acurácia do modelo"]),
                    formatar_metrica("Sharpe", com["AUC"]),
                ],
            },
            index=["Acurácia", "AUC"],
        ),
        width="stretch",
    )
    st.caption(
        "Como cada rótulo olha os próximos dias, exemplos vizinhos do treino e do teste "
        "compartilham o mesmo futuro. O expurgo tira do treino o que encosta no teste e o "
        "embargo deixa uma folga depois dele. Uma diferença grande entre as colunas indica vazamento."
    )

    st.markdown("*Meta-rotulagem: o modelo filtra os sinais de uma regra simples*")
    nome = _escolher_estrategia_simples("ml_meta")
    limiar = st.slider(
        "Age se a probabilidade de sucesso passar de",
        0.4,
        0.7,
        0.5,
        0.01,
        key="ml_meta_limiar",
    )
    custo = _custo_do_experimento("ml_meta")
    fechamento = dados["Close"]
    try:
        base = gerar_posicao(nome, dados)
        sinal = (base > 0).to_numpy()
        conjunto_meta, previsoes_meta = calcular_previsoes_do_sinal(
            dados, "barreira", alvo / 100, stop / 100, prazo, sinal.tobytes()
        )
    except ValueError as erro:
        st.info(str(erro))
        return
    aceitos = previsoes_meta["p"] > limiar
    avaliados = previsoes_meta["p"].notna()
    if avaliados.sum() < 30:
        st.info(
            "Há poucos sinais da regra para treinar o modelo. Use outra regra ou um período maior."
        )
        return
    taxa_geral = conjunto_meta.y[avaliados].mean()
    taxa_aceitos = conjunto_meta.y[aceitos].mean() if aceitos.any() else float("nan")
    meta = base.where(base.index.isin(aceitos[aceitos].index), 0.0)
    inicio = previsoes_meta["p"].first_valid_index()
    teste = fechamento.loc[inicio:]
    resultados = {
        f"{nome} + meta-modelo": executar_backtest(teste, meta.loc[inicio:], custo),
        nome: executar_backtest(teste, base.loc[inicio:], custo),
    }
    if nome != ESTRATEGIA_DE_REFERENCIA:
        resultados[ESTRATEGIA_DE_REFERENCIA] = executar_backtest(
            teste, pd.Series(1.0, index=teste.index), custo
        )
    st.caption(
        f"Dos {int(avaliados.sum())} sinais avaliados, o alvo veio primeiro em "
        f"{formatar_pct(taxa_geral)}; nos {int(aceitos.sum())} que o modelo aceitou, em "
        f"{formatar_pct(taxa_aceitos)}."
    )
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            {n: x.curva_de_capital for n, x in resultados.items()},
            10_000.0,
            destaque=f"{nome} + meta-modelo",
        )
    )
    st.dataframe(
        _tabela_de_resultados(resultados, taxa_livre_de_risco), width="stretch"
    )


def _ml_volatilidade(dados, taxa_livre_de_risco):
    st.markdown("**Prever a volatilidade (mais fácil que prever o preço)**")
    st.caption(
        "Regressão linear do log da volatilidade futura nas volatilidades de 5, 20 e 60 dias "
        "(estilo HAR), treinada só com o passado. A base de comparação é dizer que os próximos "
        "dias serão iguais aos últimos 20."
    )
    c1, c2, c3 = st.columns(3)
    horizonte = c1.slider("Prever os próximos (dias)", 5, 42, 21, 1, key="ml_horizonte")
    alvo = c2.slider("Alvo de volatilidade (% ao ano)", 5, 40, 15, 1, key="ml_alvo_vol")
    with c3:
        custo = _custo_do_experimento("ml_vol")
    try:
        r = aprendizado.prever_volatilidade(dados, horizonte)
    except ValueError as erro:
        st.info(str(erro))
        return
    m = r.metricas
    cartoes = st.columns(3)
    cartoes[0].metric(
        "Erro do modelo (log)",
        formatar_metrica("Sharpe", m["Erro do modelo (log)"]),
        delta=f"{formatar_metrica('Sharpe', m['Erro ingênuo (log)'])} na previsão ingênua",
        delta_color="off",
        delta_arrow="off",
    )
    cartoes[1].metric(
        "Melhora sobre a ingênua",
        formatar_pct(m["Melhora sobre o ingênuo"], com_sinal=True),
    )
    cartoes[2].metric(
        "Correlação com o que veio",
        formatar_metrica("Sharpe", m["Correlação do modelo"]),
        delta=f"{formatar_metrica('Sharpe', m['Correlação ingênua'])} na ingênua",
        delta_color="off",
        delta_arrow="off",
    )
    mostrar_grafico(
        graficos.criar_grafico_volatilidade_prevista(r.prevista, r.ingenua, r.realizada)
    )
    fechamento = dados["Close"]
    inicio = r.prevista.index[0]
    teste = fechamento.loc[inicio:]
    posicoes = {
        "Alvo com a volatilidade prevista": aprendizado.posicao_pelo_alvo_de_volatilidade(
            r.prevista, fechamento.index, alvo / 100
        ),
        "Alvo com a volatilidade dos últimos 20 dias": aprendizado.posicao_pelo_alvo_de_volatilidade(
            r.ingenua, fechamento.index, alvo / 100
        ),
    }
    resultados = {
        n: executar_backtest(teste, p.loc[inicio:], custo) for n, p in posicoes.items()
    }
    resultados[ESTRATEGIA_DE_REFERENCIA] = executar_backtest(
        teste, pd.Series(1.0, index=teste.index), custo
    )
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            {n: x.curva_de_capital for n, x in resultados.items()},
            10_000.0,
            destaque="Alvo com a volatilidade prevista",
        )
    )
    st.dataframe(
        _tabela_de_resultados(resultados, taxa_livre_de_risco), width="stretch"
    )
    st.caption(
        "A volatilidade é persistente (dias agitados vêm em sequência), por isso é bem mais "
        "previsível que o sinal do preço. O erro do modelo costuma cair em relação aos "
        "últimos 20 dias porque ele corrige o nível (a volatilidade tende a voltar à média), "
        "mas a correlação com o que veio quase não melhora. Sem alavancagem (no máximo 100%)."
    )


def secao_aprendizado(dados, taxa_livre_de_risco):
    st.subheader("Aprendizado de máquina honesto")
    st.warning(
        "Aprendizado de máquina aumenta muito o risco de overfitting. Aqui o modelo sempre "
        "treina só com o passado e é medido contra uma previsão ingênua. É normal ele não vencer."
    )
    aba_dia, aba_barreira, aba_vol = st.tabs(
        ["Sinal do dia", "Barreira tripla e meta-rotulagem", "Volatilidade"]
    )
    with aba_dia:
        _ml_sinal_do_dia(dados, taxa_livre_de_risco)
    with aba_barreira:
        _ml_barreira_e_meta(dados, taxa_livre_de_risco)
    with aba_vol:
        _ml_volatilidade(dados, taxa_livre_de_risco)


PARES_PADRAO = "ITUB4, BBDC4, BBAS3, PETR4, PETR3"


def _tabela_de_pares(tabela):
    exibicao = pd.DataFrame(index=tabela.index)
    exibicao["Correlação"] = [
        formatar_metrica("Sharpe", v) for v in tabela["Correlação"]
    ]
    exibicao["Beta"] = [formatar_metrica("Sharpe", v) for v in tabela["Beta"]]
    exibicao["ADF no treino"] = [
        formatar_metrica("Sharpe", v) for v in tabela["ADF no treino"]
    ]
    exibicao["Meia-vida (dias)"] = [
        "—" if not np.isfinite(v) else f"{v:.0f}" for v in tabela["Meia-vida (dias)"]
    ]
    exibicao["Ligado no treino?"] = [
        "Sim" if v else "Não" for v in tabela["Cointegrado no treino"]
    ]
    exibicao["ADF no teste"] = [
        formatar_metrica("Sharpe", v) for v in tabela["ADF no teste"]
    ]
    exibicao["Continuou no teste?"] = [
        "Sim" if v else "Não" for v in tabela["Continuou no teste"]
    ]
    return exibicao


def secao_pares(periodo, taxa_livre_de_risco):
    st.subheader("Pairs trading: apostar que dois ativos voltam a andar juntos")
    st.caption(ajuda_do("Pairs trading"))
    st.warning(
        "Este é um desafio educativo. A perna vendida exige aluguel de ações, que tem custo e "
        "nem sempre está disponível; esse custo não entra na simulação. Resultado do passado "
        "não garante nada."
    )
    with st.container(border=True):
        texto = st.text_input(
            f"Ativos (2 a {MAX_ATIVOS_PARA_PARES}, separados por vírgula)",
            value=PARES_PADRAO,
            key="pares_ativos",
            help="O app testa todos os pares possíveis da lista.",
        )
        c1, c2 = st.columns(2)
        fracao = c1.slider(
            "Parte do período usada para estimar (treino)",
            0.3,
            0.8,
            0.5,
            0.05,
            key="pares_treino",
            help="A relação entre os ativos é estimada só nesta parte; a negociação acontece no resto.",
        )
        custo = (
            c2.number_input(
                "Custo por operação (%)",
                0.0,
                2.0,
                CUSTO_PADRAO_POR_OPERACAO * 100,
                0.01,
                format="%.2f",
                key="pares_custo",
            )
            / 100
        )
    tickers = interpretar_tickers(texto)
    if not 2 <= len(tickers) <= MAX_ATIVOS_PARA_PARES:
        st.info(
            f"Escolha de 2 a {MAX_ATIVOS_PARA_PARES} ativos (agora são {len(tickers)})."
        )
        return
    fechamentos, sem_dados = {}, []
    for ticker in tickers:
        try:
            fechamentos[ticker] = carregar_dados(ticker, periodo)["Close"]
        except DadosIndisponiveisError:
            sem_dados.append(ticker)
    if sem_dados:
        st.warning(
            f"Não encontrei dados para: {', '.join(sem_dados)}. Eles ficaram de fora."
        )
    if len(fechamentos) < 2:
        st.info("Não há ativos suficientes com dados.")
        return
    alinhado, _ = alinhar_fechamentos(fechamentos)
    try:
        tabela = procurar_pares(alinhado, fracao)
    except ValueError as erro:
        st.info(str(erro))
        return
    st.markdown("**Todos os pares da lista**")
    st.dataframe(_tabela_de_pares(tabela), width="stretch")
    sobreviventes = int(tabela["Cointegrado no treino"].sum())
    continuaram = int(
        (tabela["Cointegrado no treino"] & tabela["Continuou no teste"]).sum()
    )
    st.caption(
        f"{len(tabela)} pares testados; {sobreviventes} pareceram ligados no treino e "
        f"{continuaram} continuaram ligados no teste. ADF abaixo de −3,34 indica relação "
        "(valor aproximado de Engle-Granger a 5%). Ao testar muitos pares, uns 5% parecem "
        "ligados só por sorte: por isso a conferência no teste."
    )

    par = st.selectbox("Par para simular", list(tabela.index), key="pares_escolhido")
    a, b = par.split(" × ")
    c1, c2, c3, c4 = st.columns(4)
    entrada = c1.slider(
        "Entra com |z| acima de", 1.0, 3.0, 2.0, 0.1, key="pares_entrada"
    )
    saida = c2.slider("Sai com |z| abaixo de", 0.0, 1.0, 0.5, 0.1, key="pares_saida")
    stop = c3.slider("Stop com |z| acima de", 3.0, 6.0, 4.0, 0.5, key="pares_stop")
    janela = c4.slider("Janela do z-score (dias)", 20, 120, 60, 5, key="pares_janela")
    try:
        r = simular_par(
            alinhado[a], alinhado[b], fracao, entrada, saida, stop, janela, custo
        )
    except ValueError as erro:
        st.info(str(erro))
        return
    bt = r.backtest
    numeros = resumir_desempenho(
        bt.retorno, bt.posicao, bt.operacoes, taxa_livre_de_risco
    )
    cartoes = st.columns(4)
    for coluna, metrica in zip(
        cartoes, ["Retorno total", "Índice de Sharpe", "Maior queda", "Operações"]
    ):
        coluna.metric(metrica, formatar_metrica(metrica, numeros[metrica]))
    meia = r.treino.meia_vida
    st.caption(
        f"Relação estimada no treino: log {a} = {formatar_metrica('Sharpe', r.treino.beta)} × log {b} + constante. "
        f"Meia-vida do spread no treino: {'sem volta' if not np.isfinite(meia) else f'{meia:.0f} dias'}. "
        f"ADF: {formatar_metrica('Sharpe', r.treino.adf)} no treino e "
        f"{formatar_metrica('Sharpe', r.teste.adf)} no teste "
        f"({'a relação continuou' if r.teste.cointegrado else 'a relação NÃO se confirmou no teste'})."
    )
    mostrar_grafico(
        graficos.criar_grafico_z_do_par(r.z, r.lado, entrada, stop, r.inicio_do_teste)
    )
    teste_a = alinhado[a].loc[r.inicio_do_teste :]
    teste_b = alinhado[b].loc[r.inicio_do_teste :]
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            {
                f"Par {a} × {b}": bt.curva_de_capital,
                f"Comprar e segurar {a}": teste_a / teste_a.iloc[0],
                f"Comprar e segurar {b}": teste_b / teste_b.iloc[0],
            },
            10_000.0,
            destaque=f"Par {a} × {b}",
        )
    )
    st.caption(
        "O par é neutro ao mercado: não depende de os preços subirem. Compare o retorno e a "
        "queda com os dois ativos sozinhos, no mesmo período de teste. Se o ADF do teste não "
        "confirma a relação, o lucro (se houve) provavelmente foi sorte."
    )


ATIVOS_PADRAO_DA_CARTEIRA = "PETR4, VALE3, ITUB4, WEGE3, ABEV3"


def _controles_da_estrategia(estrategia, chave):
    """Sliders dos parâmetros de uma estratégia de carteira."""
    valores = {}
    if estrategia.parametros:
        colunas = st.columns(min(len(estrategia.parametros), 3))
        for posicao, p in enumerate(estrategia.parametros):
            valores[p.nome] = colunas[posicao % len(colunas)].slider(
                p.rotulo,
                p.minimo,
                p.maximo,
                p.padrao,
                p.passo,
                key=f"{chave}_{p.nome}",
                help=p.ajuda or None,
            )
    return valores


def secao_carteira(periodo, taxa_livre_de_risco, cdi_diario):
    st.subheader("Carteira: várias ações ao mesmo tempo")
    st.caption(
        "Cada estratégia decide no último pregão do mês quanto colocar em cada ativo; o que "
        "não está nos ativos fica em caixa. Entre uma decisão e outra, os pesos variam com os "
        "preços, como numa carteira de verdade."
    )
    with st.container(border=True):
        texto = st.text_input(
            f"Ativos ({MIN_ATIVOS_NA_CARTEIRA} a {MAX_ATIVOS_NA_CARTEIRA}, separados por vírgula)",
            value=ATIVOS_PADRAO_DA_CARTEIRA,
            key="carteira_ativos",
            help="O primeiro ativo da lista é o canário da estratégia de mesmo nome.",
        )
        nome = st.selectbox(
            "Estratégia", list(ESTRATEGIAS_DE_CARTEIRA), key="carteira_estrategia"
        )
        parametros = _controles_da_estrategia(
            ESTRATEGIAS_DE_CARTEIRA[nome], f"carteira_{nome}"
        )
        col_custo, col_caixa = st.columns(2)
        custo_percentual = col_custo.number_input(
            "Custo por operação (%)",
            min_value=0.0,
            max_value=2.0,
            value=CUSTO_PADRAO_POR_OPERACAO * 100,
            step=0.01,
            format="%.2f",
            key="carteira_custo",
            help=ajuda_do("Custo de operação"),
        )
        caixa_rende_cdi = col_caixa.checkbox(
            "O dinheiro parado rende o CDI",
            key="carteira_caixa_cdi",
            help=ajuda_do("CDI"),
        )

    tickers = interpretar_tickers(texto)
    if not MIN_ATIVOS_NA_CARTEIRA <= len(tickers) <= MAX_ATIVOS_NA_CARTEIRA:
        st.info(
            f"Escolha de {MIN_ATIVOS_NA_CARTEIRA} a {MAX_ATIVOS_NA_CARTEIRA} ativos "
            f"(agora são {len(tickers)})."
        )
        return
    fechamentos, sem_dados = {}, []
    for ticker in tickers:
        try:
            fechamentos[ticker] = carregar_dados(ticker, periodo)["Close"]
        except DadosIndisponiveisError:
            sem_dados.append(ticker)
    if sem_dados:
        st.warning(
            f"Não encontrei dados para: {', '.join(sem_dados)}. Eles ficaram de fora."
        )
    if len(fechamentos) < MIN_ATIVOS_NA_CARTEIRA:
        st.info("Não há ativos suficientes com dados.")
        return
    alinhado, descartados = alinhar_fechamentos(fechamentos)
    if len(alinhado) < 60:
        st.warning(
            f"Só há {len(alinhado)} dias em comum entre os ativos. Tente um período mais longo."
        )
        return

    retorno_do_caixa = None
    if caixa_rende_cdi:
        try:
            cdi = cdi_diario
            if cdi is None:
                cdi = obter_cdi(alinhado.index[0], alinhado.index[-1])
            retorno_do_caixa = (
                curva_do_cdi(cdi, alinhado.index).pct_change().fillna(0.0)
            )
        except CDIIndisponivelError as erro:
            st.warning(f"{erro} O dinheiro parado ficou sem render.")

    custo = custo_percentual / 100
    try:
        principal = simular_carteira(
            nome, alinhado, custo, retorno_do_caixa, **parametros
        )
        referencia = simular_carteira(
            "Pesos iguais (referência)", alinhado, custo, retorno_do_caixa
        )
    except ValueError as erro:
        st.error(str(erro))
        return

    explicacao = obter_estrategias().get(nome)
    if explicacao:
        with st.expander("Como funciona esta estratégia", expanded=True):
            st.markdown(proteger_cifrao(explicacao))

    carteiras = {nome: principal}
    if nome != "Pesos iguais (referência)":
        carteiras["Pesos iguais (referência)"] = referencia
    numeros = {
        rotulo: resumir_desempenho(r.retorno, r.exposicao, None, taxa_livre_de_risco)
        for rotulo, r in carteiras.items()
    }
    sem_estrategia = pd.Series(1.0, index=alinhado.index)
    for ativo in alinhado.columns:
        retorno_do_ativo = ind.calcular_retorno_diario(alinhado[ativo])
        numeros[f"{NOMES_AMIGAVEIS.get(ativo, ativo)} (comprar e segurar)"] = (
            resumir_desempenho(
                retorno_do_ativo, sem_estrategia, None, taxa_livre_de_risco
            )
        )

    cartoes = st.columns(4)
    for coluna, metrica in zip(
        cartoes, ["Retorno total", "Índice de Sharpe", "Maior queda", "Exposição média"]
    ):
        coluna.metric(
            metrica,
            formatar_metrica(metrica, numeros[nome][metrica]),
            delta=(
                f"{formatar_metrica(metrica, numeros['Pesos iguais (referência)'][metrica])} "
                "em pesos iguais"
                if nome != "Pesos iguais (referência)"
                else None
            ),
            delta_color="off",
            delta_arrow="off",
        )
    anos = len(alinhado) / ind.DIAS_POR_ANO
    st.caption(
        f"Giro de {formatar_pct(principal.giro / anos)} do capital por ano "
        "(tudo o que foi comprado e vendido, dividido pelos anos do período)."
    )

    curvas = {rotulo: r.curva_de_capital for rotulo, r in carteiras.items()}
    escolhidos = st.multiselect(
        "Mostrar também (comprar e segurar)",
        list(alinhado.columns),
        key="carteira_ativos_no_grafico",
    )
    for ativo in escolhidos:
        curvas[f"{NOMES_AMIGAVEIS.get(ativo, ativo)} (comprar e segurar)"] = (
            alinhado[ativo] / alinhado[ativo].iloc[0]
        )
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(curvas, 10_000.0, destaque=nome)
    )
    mostrar_grafico(graficos.criar_grafico_pesos(principal.pesos))

    st.markdown("**Números lado a lado**")
    st.dataframe(
        pd.DataFrame(
            {
                rotulo: {m: formatar_metrica(m, v) for m, v in valores.items()}
                for rotulo, valores in numeros.items()
            }
        ),
        width="stretch",
    )
    st.caption(
        f"Feito em {len(alinhado)} dias em comum ({descartados} descartados por feriados "
        "diferentes). Cuidado: a lista de ativos foi escolhida hoje, entre empresas que "
        "sobreviveram (*viés de sobrevivência*), e com poucos ativos o resultado depende "
        "muito de quais você escolheu."
    )


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

    mostrar_grafico(
        graficos.criar_grafico_risco_retorno(tabela, destaque=ESTRATEGIA_DE_REFERENCIA)
    )
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


def escolher_custos():
    """Custo por operação em %: um número só ou separado em corretagem, taxas e slippage."""
    modo = st.radio(
        "Custos",
        ["Um número só", "Detalhados"],
        horizontal=True,
        key="backtest_modo_custos",
        help=ajuda_do("Custo de operação"),
    )
    if modo == "Um número só":
        return st.number_input(
            "Custo por operação (%)",
            min_value=0.0,
            max_value=2.0,
            value=CUSTO_PADRAO_POR_OPERACAO * 100,
            step=0.01,
            format="%.2f",
            help="Corretagem, taxas e a diferença entre o preço pedido e o executado, "
            "cobrados em cada compra e em cada venda.",
        )
    c1, c2, c3 = st.columns(3)
    corretagem = c1.number_input(
        "Corretagem (%)", 0.0, 1.0, 0.0, 0.01, format="%.2f", key="custo_corretagem"
    )
    taxas = c2.number_input(
        "Taxas e emolumentos (%)",
        0.0,
        1.0,
        0.03,
        0.01,
        format="%.2f",
        key="custo_taxas",
        help="Taxas da bolsa e da liquidação. Os valores variam: confira na sua corretora.",
    )
    slippage = c3.number_input(
        "Slippage (%)",
        0.0,
        1.0,
        0.02,
        0.01,
        format="%.2f",
        key="custo_slippage",
        help="Diferença entre o preço que você via e o preço em que a ordem foi executada.",
    )
    total = corretagem + taxas + slippage
    st.caption(
        f"Custo total: {f'{total:.2f}'.replace('.', ',')}% em cada compra e em cada venda."
    )
    return total


def secao_backtest(dados, taxa_livre_de_risco, cdi_diario=None):
    st.subheader("Backtest: e se eu tivesse seguido esta regra?")
    st.caption(
        "Simulação com dados do passado. A decisão tomada no fim de cada dia só vale a partir "
        "do dia seguinte, para a simulação não usar o futuro."
    )
    with st.container(border=True):
        nome, parametros = escolher_estrategia()
        custo_percentual = escolher_custos()
        capital_inicial = st.number_input(
            "Capital inicial (R\\$)", min_value=100.0, value=10_000.0, step=1_000.0
        )
        protecoes = escolher_protecoes()
        col_imposto, col_cdi = st.columns(2)
        descontar_imposto = col_imposto.checkbox(
            "Descontar imposto de renda (simplificado)",
            key="backtest_imposto",
            help=ajuda_do("Imposto de renda (simplificado)"),
        )
        mostrar_cdi = False
        if cdi_diario is None:
            mostrar_cdi = col_cdi.checkbox(
                "Mostrar o CDI como referência",
                key="backtest_mostrar_cdi",
                help=ajuda_do("CDI"),
            )

    fechamento = dados["Close"]
    try:
        posicao = gerar_posicao(nome, dados, **parametros)
        posicao_protegida = aplicar_protecoes(dados, posicao, protecoes)
    except ValueError as erro:
        st.error(str(erro))
        return
    tem_stop = any(
        v is not None
        for v in (
            protecoes.stop_loss,
            protecoes.take_profit,
            protecoes.stop_movel,
            protecoes.stop_atr,
        )
    )
    if (
        nome == ESTRATEGIA_DE_REFERENCIA
        and tem_stop
        and protecoes.dias_de_espera is None
    ):
        st.info(
            "Comprar e segurar nunca manda sair, então depois de um stop ela não teria um "
            "sinal novo para voltar e ficaria fora do mercado até o fim. Para ver o efeito "
            'do stop com reentrada, escolha uma espera em "Depois de um stop".'
        )
    custo = custo_percentual / 100
    com_protecao = protecoes.alguma_ligada()
    nome_principal = f"{nome} + proteções" if com_protecao else nome

    # todas as simulações, na ordem em que aparecem nos gráficos e na tabela
    resultados = {
        nome_principal: executar_backtest(fechamento, posicao_protegida, custo)
    }
    if com_protecao:
        resultados[f"{nome} (sem proteções)"] = executar_backtest(
            fechamento, posicao, custo
        )
    if nome != ESTRATEGIA_DE_REFERENCIA:
        resultados[ESTRATEGIA_DE_REFERENCIA] = executar_backtest(
            fechamento, gerar_posicao(ESTRATEGIA_DE_REFERENCIA, dados), custo
        )
    resultados_brutos = resultados
    impostos = {}
    if descontar_imposto:
        resultados = {}
        for rotulo, r in resultados_brutos.items():
            impostos[rotulo] = aplicar_imposto(r, capital_inicial)
            resultados[rotulo] = impostos[rotulo].resultado
    resultado = resultados[nome_principal]

    explicacao = obter_estrategias().get(nome)
    if explicacao:
        with st.expander("Como funciona esta estratégia", expanded=True):
            st.markdown(proteger_cifrao(explicacao))

    if resultado.operacoes.empty:
        st.info(
            "A estratégia não fez nenhuma operação neste período. Algumas regras precisam de "
            "mais histórico (por exemplo, uma média de 200 dias): tente um período maior."
        )

    if nome != ESTRATEGIA_DE_REFERENCIA and not resultado.operacoes.empty:
        primeira_entrada = resultado.operacoes.iloc[0]["entrada"]
        dias_parada = (primeira_entrada - fechamento.index[0]).days
        dias_totais = (fechamento.index[-1] - fechamento.index[0]).days
        if dias_parada > 0.15 * dias_totais:
            st.caption(
                f"Atenção: a estratégia só entrou no mercado em {primeira_entrada:%d/%m/%Y}. "
                "Antes disso ficou em caixa (falta de histórico ou de sinal), então ela e "
                "comprar e segurar não ficaram expostas pelo mesmo tempo."
            )

    numeros = {
        rotulo: resumir_desempenho(
            r.retorno, r.posicao, r.operacoes, taxa_livre_de_risco
        )
        for rotulo, r in resultados.items()
    }
    numeros_principal = numeros[nome_principal]
    numeros_referencia = numeros.get(ESTRATEGIA_DE_REFERENCIA, numeros_principal)

    cartoes = st.columns(4)
    for coluna, metrica in zip(
        cartoes, ["Retorno total", "Índice de Sharpe", "Maior queda", "Operações"]
    ):
        comparacao = (
            f"{formatar_metrica(metrica, numeros_referencia[metrica])} em {ESTRATEGIA_DE_REFERENCIA.lower()}"
            if nome != ESTRATEGIA_DE_REFERENCIA
            else None
        )
        coluna.metric(
            metrica,
            formatar_metrica(metrica, numeros_principal[metrica]),
            delta=comparacao,
            delta_color="off",
            delta_arrow="off",
            help=ajuda_do(
                {"Retorno total": "Retorno acumulado", "Maior queda": "Drawdown"}.get(
                    metrica, metrica
                )
            ),
        )

    sharpe, minimo, maximo = calcular_intervalo_do_sharpe(
        resultado.retorno, taxa_livre_de_risco
    )
    if not pd.isna(sharpe):
        medido, baixo, alto = (
            formatar_metrica("Sharpe", v) for v in (sharpe, minimo, maximo)
        )
        st.caption(
            f"O Sharpe medido é {medido}, mas com estes dados ele pode estar entre "
            f"{baixo} e {alto} (intervalo de ~95%). Com poucos anos de dados, "
            "o Sharpe é muito incerto: não compare estratégias por diferenças pequenas."
        )

    curvas = {rotulo: r.curva_de_capital for rotulo, r in resultados.items()}
    if mostrar_cdi:
        try:
            cdi_diario = obter_cdi(fechamento.index[0], fechamento.index[-1])
        except CDIIndisponivelError as erro:
            st.warning(str(erro))
    if cdi_diario is not None:
        curva_cdi = curva_do_cdi(cdi_diario, fechamento.index)
        curvas["CDI"] = curva_cdi
        rendimento = float(resultado.curva_de_capital.iloc[-1] - 1)
        st.caption(
            f"O CDI rendeu {formatar_pct(curva_cdi.iloc[-1] - 1, com_sinal=True)} no período; "
            f"a estratégia, {formatar_pct(rendimento, com_sinal=True)}. "
            + (
                "Ela ficou acima do CDI."
                if rendimento > curva_cdi.iloc[-1] - 1
                else "Ela não bateu o CDI."
            )
        )
    mostrar_grafico(
        graficos.criar_grafico_curvas_de_capital(
            curvas, capital_inicial, destaque=nome_principal
        )
    )

    col_quedas, col_preco = st.columns(2)
    with col_quedas:
        mostrar_grafico(
            graficos.criar_grafico_quedas_comparadas(curvas, destaque=nome_principal)
        )
    with col_preco:
        mostrar_grafico(
            graficos.criar_grafico_operacoes_no_preco(fechamento, resultado.operacoes)
        )

    st.markdown("**Números lado a lado**")
    tabela = pd.DataFrame(
        {
            rotulo: {m: formatar_metrica(m, v) for m, v in valores.items()}
            for rotulo, valores in numeros.items()
        }
    )
    st.dataframe(tabela, width="stretch")

    with st.expander("Mais números: Ômega, Kelly e quanto histórico seria preciso"):
        retorno_principal = resultado.retorno
        omega = calcular_omega(retorno_principal)
        kelly = calcular_kelly(retorno_principal)
        dias_minimos = calcular_comprimento_minimo(
            retorno_principal, 0.95, 0.0, taxa_livre_de_risco
        )
        c1, c2, c3 = st.columns(3)
        c1.metric(
            "Ômega",
            "—" if pd.isna(omega) else formatar_metrica("Sharpe", omega),
            help=ajuda_do("Ômega"),
        )
        c2.metric(
            "Meio Kelly (fração do capital)",
            "—" if pd.isna(kelly) else formatar_pct(kelly / 2),
            help=ajuda_do("Critério de Kelly"),
        )
        if pd.isna(dias_minimos):
            texto_dias = "—"
        elif dias_minimos == float("inf"):
            texto_dias = "nunca (Sharpe não passa de zero)"
        else:
            texto_dias = f"{dias_minimos / ind.DIAS_POR_ANO:.1f} anos".replace(".", ",")
        c3.metric(
            "Histórico para 95% de confiança",
            texto_dias,
            help=ajuda_do("Comprimento mínimo do histórico"),
        )
        anos = f"{len(retorno_principal) / ind.DIAS_POR_ANO:.1f}".replace(".", ",")
        st.caption(
            f"Os dados disponíveis têm {anos} anos. O Kelly é muito sensível ao erro de "
            "estimativa e acima de 100% pediria alavancagem: trate-o como curiosidade, "
            "não como recomendação."
        )

    if descontar_imposto:
        pago = impostos[nome_principal]
        valor = f"{pago.imposto_total:,.2f}".replace(",", "X").replace(".", ",")
        valor = valor.replace("X", ".")
        st.caption(
            f"Imposto pago por {nome_principal}: R\\$ {valor}. "
            "Regras simplificadas da B3 (15% sobre o lucro do mês, isento até R\\$ 20 mil "
            "vendidos no mês); não é orientação tributária. Comprar e segurar só paga "
            "imposto quando vende."
        )
        if not pago.meses.empty:
            with st.expander("Ver o imposto mês a mês"):
                mensal = pago.meses.copy()
                for coluna in mensal.columns[1:]:
                    mensal[coluna] = [f"{v:,.2f}" for v in mensal[coluna]]
                st.dataframe(mensal, width="stretch", hide_index=True)

    if not resultado.operacoes.empty:
        with st.expander(f"Ver as {len(resultado.operacoes)} operações"):
            operacoes = resultado.operacoes.copy()
            operacoes["entrada"] = operacoes["entrada"].dt.strftime("%d/%m/%Y")
            operacoes["saida"] = operacoes["saida"].dt.strftime("%d/%m/%Y")
            operacoes["retorno"] = [
                formatar_pct(v, com_sinal=True) for v in operacoes["retorno"]
            ]
            operacoes["aberta"] = operacoes["aberta"].map({True: "sim", False: "não"})
            operacoes.columns = [
                "Primeiro dia",
                "Último dia",
                "Dias",
                "Retorno",
                "Em aberto",
            ]
            st.dataframe(operacoes, width="stretch", hide_index=True)

    secao_validacao(
        dados,
        nome,
        parametros,
        custo,
        protecoes,
        taxa_livre_de_risco,
        resultados_brutos[nome_principal].retorno,
        resultados_brutos[ESTRATEGIA_DE_REFERENCIA].retorno,
        capital_inicial,
        resultado.operacoes,
        posicao_protegida,
    )

    st.warning(
        "Cuidado: o passado não garante o futuro. Uma regra que funcionou aqui pode ter sido "
        "ajustada ao acaso (*overfitting*); o app usa só ativos que existem hoje (*viés de "
        "sobrevivência*); e os custos reais podem ser maiores que os simulados."
    )


# --- Página -----------------------------------------------------------------
mostrar_cabecalho()
ticker, periodo, modo_da_taxa, taxa_digitada = ler_entradas()

try:
    # normaliza antes: "petr4" e "PETR4.SA" devem usar a mesma entrada do cache
    dados = carregar_dados(normalizar_ticker(ticker), periodo)
except DadosIndisponiveisError as erro:
    st.error(str(erro))
    st.stop()
fechamento = dados["Close"]
retorno = ind.calcular_retorno_diario(fechamento)
taxa_livre_de_risco, cdi_diario = resolver_taxa_livre_de_risco(
    modo_da_taxa, taxa_digitada, dados.index
)
if cdi_diario is not None:
    st.caption(
        f"CDI no período: {formatar_pct(taxa_livre_de_risco)} ao ano (usado como taxa livre de risco)."
    )

if retorno.dropna().size < MIN_DIAS_PARA_ANALISE:
    st.warning(
        f"Só há {retorno.dropna().size} dias de dados para este ticker. "
        f"São necessários pelo menos {MIN_DIAS_PARA_ANALISE} para calcular os números. "
        "Tente um período mais longo."
    )
    st.stop()

(
    aba_geral,
    aba_risco,
    aba_mensal,
    aba_comparar,
    aba_backtest,
    aba_ranking,
    aba_carteira,
    aba_experimentos,
    aba_regimes,
    aba_aprendizado,
    aba_pares,
) = st.tabs(
    [
        "Visão geral",
        "Risco",
        "Retorno mensal",
        "Comparar",
        "Backtest",
        "Ranking",
        "Carteira",
        "Experimentos",
        "Regimes",
        "Aprendizado de máquina",
        "Pares",
    ]
)
with aba_geral:
    secao_painel_de_numeros(fechamento, retorno, taxa_livre_de_risco)
    st.divider()
    secao_preco(dados)
with aba_risco:
    secao_risco(fechamento, retorno)
with aba_mensal:
    secao_retorno_mensal(retorno)
with aba_comparar:
    secao_comparar(normalizar_ticker(ticker), periodo, taxa_livre_de_risco)
with aba_backtest:
    secao_backtest(dados, taxa_livre_de_risco, cdi_diario)
with aba_ranking:
    secao_ranking(dados, taxa_livre_de_risco)
with aba_carteira:
    secao_carteira(periodo, taxa_livre_de_risco, cdi_diario)
with aba_experimentos:
    secao_experimentos(dados, periodo, taxa_livre_de_risco)
with aba_regimes:
    secao_regimes(dados, taxa_livre_de_risco)
with aba_aprendizado:
    secao_aprendizado(dados, taxa_livre_de_risco)
with aba_pares:
    secao_pares(periodo, taxa_livre_de_risco)

st.divider()
st.caption(
    "TickerLab é um projeto educacional. Os dados vêm do Yahoo Finance e podem ter atraso "
    "ou erros. Rentabilidade passada não garante resultado futuro."
)
