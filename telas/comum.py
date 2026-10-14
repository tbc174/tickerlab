"""Núcleo compartilhado das telas: contexto do topo, dados, favoritos, taxa e formatação.

Saiu do `app.py` na divisão em `telas/` (Master v3, Fase E; PR E1), sem mudar comportamento.
Regra: **nenhum estado mutável no módulo**. O `app.py` roda do zero a cada clique (as variáveis
dele são de cada sessão), mas um módulo importado roda uma vez por processo (as variáveis dele são
de todos os usuários ao mesmo tempo). Por isso o menu de páginas fica na sessão (`PAGINAS_DO_MENU`).
"""

import logging
from dataclasses import dataclass
from urllib.parse import urlencode

import pandas as pd
import streamlit as st

from src import catalogo, graficos, marca
from src import indicadores as ind
from src import parametros as research_parametros
from src import presets as research_presets
from src.analises import MIN_DIAS_PARA_ANALISE, aviso_da_origem
from src.banco.conexao import obter_engine
from src.banco.dados_do_usuario import (
    carregar_preferencias,
    presets_atuais,
    salvar_favoritos,
    salvar_preferencias,
)
from src.cdi import CDIIndisponivelError, baixar_cdi, calcular_taxa_anual_do_cdi
from src.conteudo import carregar_glossario, proteger_cifrao
from src.dados import DadosIndisponiveisError, baixar_dados, normalizar_ticker
from src.formatos import formatar_pct
from src.link import alternar_favorito, montar_parametros
from src.moedas import TICKER_DO_DOLAR, converter_para_reais, moeda_do_ticker
from src.paginas import GRUPO_MAIS, GRUPO_TOPO, pagina
from src.planos import PLANO_DO_MODO_LOCAL, conferir_favoritos, limites_do


@st.cache_data(ttl=3600, show_spinner="Baixando dados...")
def _carregar_dados_em_cache(ticker, periodo, forcar_exemplo):
    """Guarda o download por 1 hora para não consultar o Yahoo a cada clique."""
    return baixar_dados(ticker, periodo, forcar_exemplo)


def carregar_dados_na_moeda(ticker, periodo):
    """Dados do ticker na moeda dele, sem "Converter para reais" (variação sem o câmbio)."""
    exemplo = bool(st.session_state.get("usar_exemplo", False))
    return _carregar_dados_em_cache(normalizar_ticker(ticker), periodo, exemplo)


def carregar_dados(ticker, periodo):
    """Dados do ticker; com a opção do topo marcada, usa os dados de exemplo guardados.

    Com "Converter para reais", ativos cotados em dólar (EUA, S&P 500, Bitcoin) são
    multiplicados pelo câmbio do dia. Se o câmbio falhar, o ativo segue em dólar e a marca
    `attrs["cambio_falhou"]` avisa a tela.
    """
    return carregar_dados_de(ticker, periodo, bool(st.session_state.get("em_reais")))


def carregar_dados_de(ticker, periodo, em_reais):
    """Como `carregar_dados`, com o "Converter para reais" dado (o de uma simulação salva)."""
    ticker = normalizar_ticker(ticker)
    exemplo = bool(st.session_state.get("usar_exemplo", False))
    dados = _carregar_dados_em_cache(ticker, periodo, exemplo)
    if em_reais and moeda_do_ticker(ticker) == "USD":
        try:
            cambio = _carregar_dados_em_cache(TICKER_DO_DOLAR, periodo, exemplo)[
                "Close"
            ]
            return converter_para_reais(dados, cambio)
        except (DadosIndisponiveisError, ValueError) as erro:
            logging.getLogger(__name__).warning(
                "Câmbio indisponível para converter %s: %s", ticker, erro
            )
            dados = dados.copy()
            dados.attrs = {**dados.attrs, "cambio_falhou": True}
    return dados


@st.cache_data
def obter_glossario():
    """Lê o glossário uma vez só; o arquivo não muda enquanto o app roda."""
    return carregar_glossario()


def ajuda_do(termo):
    """Texto do glossário para o "?" de um campo (com o cifrão protegido)."""
    return proteger_cifrao(obter_glossario().get(termo))


def paleta_da_sessao():
    """A paleta do tema que o navegador desta pessoa está usando (claro ou escuro). Lida a cada
    execução, nunca guardada no módulo: cada sessão tem o próprio tema."""
    return marca.paleta_do_tema(st.context.theme.type)


def mostrar_grafico(figura):
    """Gráfico do Plotly com a interação padrão do app (zoom, linha-guia, duplo clique), nas cores
    do tema de quem está vendo."""
    figura = graficos.no_tema(figura, paleta_da_sessao())
    st.plotly_chart(figura, width="stretch", config=graficos.CONFIG_PLOTLY)


def plano_atual():
    """O plano de quem está usando o app (sem contas, no modo local, vale o mais amplo)."""
    usuario = st.session_state.get("usuario")
    return usuario.plano if usuario is not None else PLANO_DO_MODO_LOCAL


log_da_conta = logging.getLogger("tickerlab.conta")


def salvar_na_conta(usuario):
    """Grava favoritos e preferências só quando o usuário muda alguma coisa."""
    if usuario is None:
        return
    atual = {
        "favoritos": list(st.session_state["favoritos"]),
        "preferencias": {
            "ticker": st.session_state["ticker"],
            "periodo": st.session_state["periodo"],
            "taxa": st.session_state["taxa"],
            "em_reais": bool(st.session_state.get("em_reais")),
        },
    }
    antes = st.session_state.get("conta_snapshot")
    if (
        antes is None
    ):  # primeira vez na sessão: o que veio da conta ou do link não é mudança
        st.session_state["conta_snapshot"] = atual
        return
    if atual == antes:
        return
    try:
        with obter_engine().begin() as conexao:
            if atual["favoritos"] != antes["favoritos"]:
                salvar_favoritos(
                    conexao, usuario.id, atual["favoritos"], plano=usuario.plano
                )
            if atual["preferencias"] != antes["preferencias"]:
                # mescla com o que já está guardado (ex.: a configuração do Report Studio)
                guardadas = carregar_preferencias(conexao, usuario.id)
                salvar_preferencias(
                    conexao, usuario.id, {**guardadas, **atual["preferencias"]}
                )
        st.session_state["conta_snapshot"] = atual
    except Exception:
        log_da_conta.exception("Falha ao salvar os dados da conta")
        st.toast("Não consegui salvar as suas escolhas na conta agora.")


MODOS_DA_TAXA = ("Zero", "CDI (Banco Central)", "Digitar")


def _alternar_favorito_atual():
    try:
        favoritos = st.session_state["favoritos"]
        ticker = normalizar_ticker(st.session_state["ticker"])
        if ticker not in favoritos:
            conferir_favoritos(plano_atual(), len(favoritos), len(favoritos) + 1)
        st.session_state["favoritos"] = alternar_favorito(favoritos, ticker)
        st.session_state.pop("erro_favorito", None)
    except ValueError as erro:
        st.session_state["erro_favorito"] = str(erro)


def _ir_para_favorito():
    escolhido = st.session_state.get("favorito_escolhido")
    if escolhido and escolhido != "—":
        st.session_state["ticker"] = escolhido
    st.session_state["favorito_escolhido"] = "—"


PERIODOS_DO_TOPO = {"6mo": "6 meses", "1y": "1 ano", "2y": "2 anos", "5y": "5 anos"}


ROTULOS_CURTOS_DO_PERIODO = {"6mo": "6M", "1y": "1A", "2y": "2A", "5y": "5A"}


NOMES_DOS_MODOS_DA_TAXA = {
    "Zero": "Nenhum (zero)",
    "CDI (Banco Central)": "CDI (Banco Central)",
    "Digitar": "Digitar um valor",
}


def mostrar_favoritos():
    """Botão de favoritar o ativo atual e atalho para ir a um favorito (ficam na sua conta)."""
    favoritos = st.session_state["favoritos"]
    atual = normalizar_ticker(st.session_state["ticker"])
    limites = limites_do(plano_atual())
    with st.popover(
        f"Meus favoritos ({len(favoritos)})", icon=":material/star:", width="stretch"
    ):
        st.button(
            f"Tirar {atual} dos favoritos"
            if atual in favoritos
            else f"Favoritar {atual}",
            on_click=_alternar_favorito_atual,
            key="botao_favorito",
            width="stretch",
        )
        if favoritos:
            st.selectbox(
                "Ir para um favorito",
                ["—", *favoritos],
                key="favorito_escolhido",
                on_change=_ir_para_favorito,
            )
        else:
            st.caption("Você ainda não tem favoritos. Favorite o ativo que está vendo.")
        st.caption(
            f"{len(favoritos)} de {limites.favoritos} favoritos no plano {limites.nome}."
        )
        if st.session_state.get("erro_favorito"):
            st.warning(st.session_state["erro_favorito"])


def mostrar_link(ticker, periodo, modo):
    """Grava a escolha atual na URL do navegador e mostra o texto do link."""
    parametros = montar_parametros(
        normalizar_ticker(ticker),
        periodo,
        modo,
        bool(st.session_state.get("em_reais")),
        bool(st.session_state.get("usar_exemplo")),
        st.session_state["favoritos"],
    )
    st.query_params.from_dict(parametros)
    st.markdown("**Link desta tela**")
    st.caption(
        "O endereço na barra do navegador já guarda o ativo, o período e as opções "
        "escolhidas aqui. Copie-o para abrir a mesma tela depois ou mandar para alguém."
    )
    st.code("?" + urlencode(parametros), language=None)


def marcar_feito(acao):
    """Anota uma ação feita nesta sessão (o tutorial e a lista de tarefas leem daqui)."""
    st.session_state.setdefault("tutorial_feitos", set()).add(acao)


def _resolver_o_ticker():
    """Um código digitado vira o símbolo do catálogo (petr4 → PETR4.SA), sem trocar de ativo."""
    marcar_feito("escolheu_ativo")
    st.session_state["ticker"] = (
        catalogo.resolver(st.session_state.get("ticker")) or "PETR4.SA"
    )


def lembrar_recente(ticker):
    """Guarda os últimos ativos analisados nesta sessão (só na memória, não vai para o banco)."""
    recentes = [t for t in st.session_state.get("recentes", []) if t != ticker]
    st.session_state["recentes"] = [ticker, *recentes][:6]


def mostrar_controles():
    """Campos do ativo, no topo das páginas de análise.

    Em cima só o essencial (ativo, período, favoritos); o resto fica em "Opções avançadas".
    Devolve (ticker, período, modo da taxa, taxa digitada).
    """
    with st.container(border=True):
        col_ativo, col_periodo, col_favoritos = st.columns(
            [3, 2, 2], vertical_alignment="bottom"
        )
        ticker = col_ativo.selectbox(
            "Ativo",
            catalogo.opcoes(st.session_state.get("ticker")),
            format_func=catalogo.rotulo,
            key="ticker",
            placeholder="Busque código ou empresa…",
            accept_new_options=True,  # um código fora da lista também vale
            on_change=_resolver_o_ticker,
            help="Digite o código (PETR4, AAPL) ou o nome da empresa (Petrobras) e escolha "
            "na lista. Ações da B3, BDRs, FIIs, ETFs, ações dos EUA, índices e cripto.",
        )
        periodo = col_periodo.segmented_control(
            "Período",
            list(PERIODOS_DO_TOPO),
            format_func=ROTULOS_CURTOS_DO_PERIODO.get,
            key="periodo",
            required=True,  # sempre um período escolhido (clicar no ativo não o desmarca)
            help="Quanto tempo de histórico olhar para trás: 6 meses, 1 ano, 2 anos ou 5 anos.",
        )
        with col_favoritos:
            mostrar_favoritos()
        with st.expander("Opções avançadas"):
            col_taxa, col_valor = st.columns(2)
            modo = col_taxa.selectbox(
                "Rendimento sem risco (taxa livre de risco)",
                MODOS_DA_TAXA,
                format_func=NOMES_DOS_MODOS_DA_TAXA.get,
                key="taxa",
                help=ajuda_do("CDI"),
            )
            taxa_digitada = 0.0
            if modo == "Digitar":
                taxa_digitada = (
                    col_valor.number_input(
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
            st.checkbox(
                "Converter ativos em dólar para reais (R$)",
                key="em_reais",
                help="Multiplica os preços de ações americanas, do S&P 500 e do Bitcoin pelo "
                "dólar do dia. Ações da B3 e o Ibovespa já estão em reais. Assim a comparação "
                "inclui o efeito do câmbio, como para quem investe daqui.",
            )
            st.checkbox(
                "Usar dados de exemplo (sem internet)",
                key="usar_exemplo",
                help="Cópias de 5 anos de 13 tickers, tiradas em 09/10/2026, guardadas no "
                "projeto. O app também as usa sozinho se o Yahoo Finance falhar.",
            )
            st.divider()
            mostrar_link(ticker, periodo, modo)
    salvar_na_conta(st.session_state.get("usuario"))
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


def parametros_em_vigor(ticker):
    """Os parâmetros do Research que valem para este ativo (padrão do sistema, seu padrão ou do
    ativo). Se os guardados não combinarem mais, volta aos padrões (a página Parâmetros explica)."""
    try:
        return research_presets.resolver(
            _presets_guardados(st.session_state.get("usuario")), ticker=ticker
        )
    except ValueError:
        return research_presets.resolver([])


def avisar_parametros(resolucao, chaves):
    """Uma linha dizendo quais dos seus parâmetros esta tela está usando (só se houver algum)."""
    nomes = {p.chave: p.rotulo for p in research_parametros.PARAMETROS}
    usados = [
        f"{nomes[c]} {_formatar_parametro(c, resolucao[c])} "
        f"({resolucao.efetivos[c].nome_da_origem.lower()})"
        for c in chaves
        if resolucao.origem(c) != research_presets.SISTEMA
    ]
    if usados:
        st.caption("Usando os seus parâmetros: " + "; ".join(usados) + ".")
        st.page_link(
            PAGINAS_DO_MENU["parametros"],
            label="Mudar na página Parâmetros",
            icon=":material/tune:",
        )


CHAVE_DAS_PAGINAS_DO_MENU = "_paginas_do_menu"


class _PaginasDoMenu:
    """Chave -> `st.Page` do menu DESTA sessão, preenchido por `montar_navegacao()`.

    Antes era um dicionário no topo do `app.py`, recriado a cada clique (de cada sessão). Num módulo
    seria um só para todos os usuários (o menu de quem é administrador tem uma página a mais), então
    as páginas ficam no `st.session_state`; o `app.py` chama `recomecar()` a cada execução, como o
    `PAGINAS_DO_MENU = {}` fazia.
    """

    def recomecar(self) -> None:
        st.session_state[CHAVE_DAS_PAGINAS_DO_MENU] = {}

    def __getitem__(self, chave: str) -> st.Page:
        return st.session_state[CHAVE_DAS_PAGINAS_DO_MENU][chave]

    def __setitem__(self, chave: str, pagina: st.Page) -> None:
        st.session_state.setdefault(CHAVE_DAS_PAGINAS_DO_MENU, {})[chave] = pagina


PAGINAS_DO_MENU = _PaginasDoMenu()


@dataclass
class Contexto:
    """O ativo escolhido e tudo o que as páginas de análise precisam para trabalhar."""

    ticker: str
    periodo: str
    dados: pd.DataFrame
    fechamento: pd.Series
    retorno: pd.Series
    taxa_livre_de_risco: float
    cdi_diario: pd.Series | None


def mensagem_de_dados_indisponiveis(ticker, erro):
    """Diz a causa provável e o que fazer (blueprint, SEARCH-05): ativo existente que não
    carregou é problema de conexão, não "ativo não encontrado"."""
    simbolo = normalizar_ticker(ticker)
    if st.session_state.get("usar_exemplo") or not simbolo:
        return str(erro)
    if catalogo.esta_no_catalogo(simbolo):
        return (
            f"{catalogo.rotulo(simbolo)}: o ativo existe, mas os preços não chegaram agora "
            "(o Yahoo Finance pode estar fora do ar ou lento). Tente de novo em alguns minutos, "
            "ou marque **Usar dados de exemplo** em Opções avançadas."
        )
    return (
        f"Não encontrei **{simbolo}** no catálogo nem dados para ele no Yahoo Finance. "
        "Confira o código ou busque pelo nome da empresa e escolha na lista."
    )


def carregar_contexto():
    """Mostra os campos do ativo e carrega os dados. Se algo faltar, avisa e para a página."""
    ticker, periodo, modo_da_taxa, taxa_digitada = mostrar_controles()
    try:
        # normaliza antes: "petr4" e "PETR4.SA" devem usar a mesma entrada do cache
        dados = carregar_dados(normalizar_ticker(ticker), periodo)
    except DadosIndisponiveisError as erro:
        st.error(mensagem_de_dados_indisponiveis(ticker, erro))
        st.stop()
    if dados.attrs.get("moeda") == "BRL":
        st.caption(
            "Preços convertidos para reais (R\\$) pelo dólar do dia (USDBRL=X): o retorno "
            "inclui a variação do câmbio."
        )
    if dados.attrs.get("cambio_falhou"):
        st.warning(
            "Não consegui o câmbio para converter este ativo: os preços seguem em dólar. "
            "Tente de novo mais tarde."
        )
    aviso = aviso_da_origem(
        dados.attrs.get("origem") or "atual", dados.attrs.get("ate")
    )
    if aviso:
        st.warning(aviso)
    fechamento = dados["Close"]
    retorno = ind.calcular_retorno_diario(fechamento)
    taxa_livre_de_risco, cdi_diario = resolver_taxa_livre_de_risco(
        modo_da_taxa, taxa_digitada, dados.index
    )
    if cdi_diario is not None:
        st.caption(
            f"CDI no período: {formatar_pct(taxa_livre_de_risco)} ao ano "
            "(usado como taxa livre de risco)."
        )
    if retorno.dropna().size < MIN_DIAS_PARA_ANALISE:
        st.warning(
            f"Só há {retorno.dropna().size} dias de dados para este ticker. "
            f"São necessários pelo menos {MIN_DIAS_PARA_ANALISE} para calcular os números. "
            "Tente um período mais longo."
        )
        st.stop()
    lembrar_recente(normalizar_ticker(ticker))
    return Contexto(
        ticker=normalizar_ticker(ticker),
        periodo=periodo,
        dados=dados,
        fechamento=fechamento,
        retorno=retorno,
        taxa_livre_de_risco=taxa_livre_de_risco,
        cdi_diario=cdi_diario,
    )


def cabecalho_da_pagina(chave):
    """O molde de toda página: grupo (olho), ícone e título, selo Pro e para que ela serve."""
    p = pagina(chave)
    if p.grupo not in (GRUPO_TOPO, GRUPO_MAIS):  # sem "olho" para o topo e o Mais
        grupo = p.grupo.removesuffix(" (Pro)")
        st.markdown(f'<div class="tl-olho">{grupo}</div>', unsafe_allow_html=True)
    selo = " :blue-badge[Pro]" if p.e_pro else ""
    st.markdown(f"## {p.icone} {p.titulo}{selo}")
    st.caption(p.descricao)


# O rascunho fica nos campos (chaves "rp_..."); só "Salvar" grava uma versão nova. A chave de cada
# campo leva a versão salva: depois de salvar, os campos renascem com os valores guardados.
ROTULOS_DAS_OPCOES = {
    "zero": "Zero",
    "cdi": "CDI (Banco Central)",
    "simples": "Simples",
    "exponencial": "Exponencial",
    "diario": "Diário",
    "semanal": "Semanal",
    "sob_demanda": "Sob demanda",
    "diaria": "Diária",
    "gatilhos": "Só quando um gatilho acontecer",
    "web": "No site",
    "pdf": "Em PDF",
    "^BVSP": "Ibovespa (^BVSP)",
    "^GSPC": "S&P 500 (^GSPC)",
    "^IXIC": "Nasdaq (^IXIC)",
    "resultados": "Resultados",
    "proventos": "Proventos",
    "eventos": "Eventos",
    "risco": "Risco",
    "tecnica": "Técnica",
    "valuation": "Valuation",
    "fundamentos": "Fundamentos",
    "participacoes": "Participações",
}


def _presets_guardados(usuario):
    """Os presets em vigor: da conta, ou desta sessão no modo local (sem login)."""
    if usuario is None:
        return list(st.session_state.get("presets_locais", []))
    try:
        with obter_engine().connect() as conexao:
            return presets_atuais(conexao, usuario.id)
    except Exception:
        logging.getLogger(__name__).exception("Falha ao ler os parâmetros")
        st.warning("Não consegui ler os seus parâmetros agora; mostrando os padrões.")
        return []


def _formatar_parametro(chave, valor):
    if isinstance(valor, tuple):
        return ", ".join(ROTULOS_DAS_OPCOES.get(v, v) for v in valor) or "—"
    if isinstance(valor, float):
        return f"{valor:g}".replace(".", ",")
    return ROTULOS_DAS_OPCOES.get(valor, str(valor))


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
