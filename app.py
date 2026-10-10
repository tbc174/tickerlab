"""TickerLab: interface do app. Só mostra; os cálculos ficam em src/."""

import pandas as pd
import streamlit as st

from src import graficos
from src import indicadores as ind
from src.backtest import CUSTO_PADRAO_POR_OPERACAO, executar_backtest
from src.comparacao import (
    ATALHOS,
    ATALHOS_PADRAO,
    MAX_ATIVOS,
    NOMES_AMIGAVEIS,
    alinhar_fechamentos,
    escolher_ativos,
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
from src.indicadores import NOMES_DOS_MESES
from src.metricas import calcular_intervalo_do_sharpe, resumir_desempenho
from src.protecoes import Protecoes, aplicar_protecoes
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

    aba_tt, aba_wf, aba_mapa = st.tabs(
        ["Treino e teste", "Walk-forward", "Mapa de parâmetros"]
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


def secao_backtest(dados, taxa_livre_de_risco):
    st.subheader("Backtest: e se eu tivesse seguido esta regra?")
    st.caption(
        "Simulação com dados do passado. A decisão tomada no fim de cada dia só vale a partir "
        "do dia seguinte, para a simulação não usar o futuro."
    )
    with st.container(border=True):
        nome, parametros = escolher_estrategia()
        col_custo, col_capital = st.columns(2)
        custo_percentual = col_custo.number_input(
            "Custo por operação (%)",
            min_value=0.0,
            max_value=2.0,
            value=CUSTO_PADRAO_POR_OPERACAO * 100,
            step=0.01,
            format="%.2f",
            help="Corretagem, taxas e a diferença entre o preço pedido e o executado, "
            "cobrados em cada compra e em cada venda.",
        )
        capital_inicial = col_capital.number_input(
            "Capital inicial (R\\$)", min_value=100.0, value=10_000.0, step=1_000.0
        )
        protecoes = escolher_protecoes()

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
        resultado.retorno,
        resultados[ESTRATEGIA_DE_REFERENCIA].retorno,
        capital_inicial,
    )

    st.warning(
        "Cuidado: o passado não garante o futuro. Uma regra que funcionou aqui pode ter sido "
        "ajustada ao acaso (*overfitting*); o app usa só ativos que existem hoje (*viés de "
        "sobrevivência*); e os custos reais podem ser maiores que os simulados."
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

aba_geral, aba_risco, aba_mensal, aba_comparar, aba_backtest = st.tabs(
    ["Visão geral", "Risco", "Retorno mensal", "Comparar", "Backtest"]
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
    secao_backtest(dados, taxa_livre_de_risco)

st.divider()
st.caption(
    "TickerLab é um projeto educacional. Os dados vêm do Yahoo Finance e podem ter atraso "
    "ou erros. Rentabilidade passada não garante resultado futuro."
)
