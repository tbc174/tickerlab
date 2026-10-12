"""TickerLab: interface do app. Só mostra; os cálculos ficam em src/."""

import logging

import streamlit as st

from src import (
    catalogo,
    marca,
    relatorios,
    tutorial,
)
from src import indicadores as ind
from src import presets as research_presets
from src.banco.conexao import obter_engine
from src.banco.dados_do_usuario import (
    carregar_preferencias,
    salvar_preferencias,
)
from src.dados import normalizar_ticker
from src.estilo import CSS_DO_APP
from src.exportacao import (
    converter_para_csv,
    montar_tabela_de_precos,
)
from src.link import ler_parametros
from src.logs import configurar_logs
from src.paginas import (
    GRUPOS,
    PAGINA_INICIAL,
    pagina,
    paginas_do_grupo,
)
from src.planos import (
    limites_do,
    pode_usar,
)
from telas.analise import (
    pagina_comparar,
    pagina_correlacao,
    pagina_retorno_mensal,
    pagina_risco,
    secao_painel_de_numeros,
    secao_preco,
    secao_tendencia_e_volume,
)
from telas.comum import (
    PAGINAS_DO_MENU,
    PERIODOS_DO_TOPO,
    _alternar_favorito_atual,
    avisar_parametros,
    cabecalho_da_pagina,
    carregar_contexto,
    formatar_pct,
    marcar_feito,
    parametros_em_vigor,
    plano_atual,
)
from telas.conta.admin import pagina_admin
from telas.conta.assinatura import (
    mostrar_conta,
    mostrar_retorno_do_pagamento,
    pagina_planos,
)
from telas.conta.entrada import obter_usuario_logado
from telas.conta.meus_dados import pagina_meus_dados
from telas.conta.textos_legais import pagina_privacidade, pagina_termos
from telas.dados_da_conta import carregar_da_conta, pagina_simulacoes
from telas.estrategias.aprendizado import pagina_aprendizado
from telas.estrategias.backtest import pagina_backtest
from telas.estrategias.carteira import pagina_carteira
from telas.estrategias.experimentos import pagina_experimentos
from telas.estrategias.pares import pagina_pares
from telas.estrategias.ranking import pagina_ranking
from telas.estrategias.regimes import pagina_regimes
from telas.guia import pagina_guia
from telas.momentum import pagina_momentum
from telas.relatorios.biblioteca import mostrar_biblioteca
from telas.relatorios.estudio import (
    _aplicar_secoes,
    atalho_para_o_relatorio,
    mostrar_estudio,
)
from telas.research.acontecimentos import pagina_research
from telas.research.alertas import pagina_alertas
from telas.research.donos import pagina_donos
from telas.research.fundamentos import pagina_fundamentos
from telas.research.minha_carteira import pagina_carteira_research
from telas.research.newsletter import pagina_newsletter
from telas.research.parametros import pagina_parametros
from telas.research.por_dentro import pagina_por_dentro
from telas.trade import pagina_trade

# o mesmo logger do telas/comum.py (o nome fixo faz o Python devolver o mesmo objeto)
log_da_conta = logging.getLogger("tickerlab.conta")

configurar_logs()
st.set_page_config(
    page_title="TickerLab", page_icon=str(marca.ARQUIVO_DO_ICONE), layout="wide"
)
st.markdown(f"<style>{CSS_DO_APP}</style>", unsafe_allow_html=True)
# símbolo + "TickerLab" no canto do menu (clicar volta ao Início); só o símbolo se faltar espaço
st.logo(str(marca.ARQUIVO_DA_ASSINATURA), size="large")


# --- Cabeçalho e entradas -----------------------------------------------------


def preparar_estado_inicial():
    """Valores iniciais dos campos do topo; na primeira visita, lê os da URL (link compartilhado)."""
    padroes = {"ticker": "PETR4.SA", "periodo": "2y", "taxa": "Zero", "favoritos": []}
    for chave, valor in padroes.items():
        st.session_state.setdefault(chave, valor)
    if not st.session_state.get("url_lida"):
        st.session_state["url_lida"] = True
        lidos = ler_parametros(dict(st.query_params))
        for chave in (
            "ticker",
            "periodo",
            "taxa",
            "em_reais",
            "usar_exemplo",
            "favoritos",
        ):
            if chave in lidos:
                st.session_state[chave] = lidos[chave]


def acoes_feitas():
    feitos = set(st.session_state.get("tutorial_feitos", set()))
    if st.session_state.get("favoritos"):
        feitos.add("salvou_favorito")
    return feitos


# --- Páginas ----------------------------------------------------------------
PAGINAS_DO_MENU.recomecar()  # o menu desta sessão, refeito a cada execução (telas/comum.py)
PREFIXOS_QUE_SOBREVIVEM_A_TROCA_DE_PAGINA = (
    "backtest_",
    "parametro_",
    "custo_",
    "liga_",
    "valor_",
    "espera_depois_do_stop",
    "carteira_",
    "pares_",
    "validacao_",
    "exp_",
    "corr_",
    "momentum_",
    "reg_",
    "ml_",
    "ranking_",
    "relatorio_",  # Report Studio (os botões usam "estudio_", que não pode ser reatribuído)
)
CAMPOS_DO_TOPO_QUE_SOBREVIVEM = (
    "ticker",
    "periodo",
    "taxa",
    "em_reais",
    "usar_exemplo",
)


def manter_estado():
    """Evita que o Streamlit esqueça os campos ao trocar de página.

    Ele apaga o valor de todo campo que não aparece na página atual. Reatribuir o valor a cada
    execução o mantém (só vale para campos com `key`).
    """
    for chave in list(st.session_state.keys()):
        if chave in CAMPOS_DO_TOPO_QUE_SOBREVIVEM or chave.startswith(
            PREFIXOS_QUE_SOBREVIVEM_A_TROCA_DE_PAGINA
        ):
            st.session_state[chave] = st.session_state[chave]


def mostrar_topo(usuario):
    """A conta (ou o aviso de modo local) à direita; a marca fica no canto do menu."""
    _, col_conta = st.columns([5, 2], vertical_alignment="center")
    with col_conta:
        if usuario is not None:
            mostrar_conta(usuario)
        else:
            st.markdown(":gray-badge[Modo local · sem login]")


def _analisar_o_ativo_do_inicio():
    simbolo = catalogo.resolver(st.session_state.get("ativo_do_inicio"))
    if simbolo:
        st.session_state["ticker"] = simbolo
        st.session_state["ir_para_visao_geral"] = True
        marcar_feito("escolheu_ativo")


def _analisar_o_atalho(chave):
    simbolo = st.session_state.get(chave)
    if simbolo:
        st.session_state["ticker"] = simbolo
        st.session_state["ir_para_visao_geral"] = True
        marcar_feito("escolheu_ativo")


# --- Tutorial por objetivo (blueprint, seção 4) ---------------------------------------------
def _guardar_na_conta(chave, valor):
    """Grava uma preferência na conta, sem apagar as outras (sem conta, fica só na sessão)."""
    usuario = st.session_state.get("usuario")
    if usuario is None:
        return
    try:
        with obter_engine().begin() as conexao:
            atuais = carregar_preferencias(conexao, usuario.id)
            salvar_preferencias(conexao, usuario.id, {**atuais, chave: valor})
    except Exception:
        logging.getLogger(__name__).exception("Falha ao salvar a preferência %s", chave)


def _preparar_o_estudio(tipo, modelo=relatorios.EXECUTIVO):
    st.session_state["tipo_de_relatorio"] = tipo
    st.session_state["relatorio_modelo"] = modelo
    _aplicar_secoes(tipo, relatorios.secoes_do_modelo(tipo, modelo))
    st.session_state.pop("relatorio_gerado", None)


def _comecar_tutorial(objetivo):
    st.session_state["tutorial"] = {"objetivo": objetivo, "passo": 0}
    if objetivo == tutorial.CARTEIRA:
        _preparar_o_estudio(relatorios.MINHA_CARTEIRA, relatorios.COMPLETO)
        st.session_state["tutorial_ir_para"] = "relatorio"
    elif objetivo == tutorial.RELATORIO:
        _preparar_o_estudio(relatorios.ATIVO)
        st.session_state["tutorial_ir_para"] = "relatorio"


def _encerrar_tutorial(concluiu):
    st.session_state.pop("tutorial", None)
    st.session_state["tutorial_visto"] = True
    _guardar_na_conta("tutorial_visto", True)
    if concluiu:
        st.toast(
            "Tutorial concluído. Dá para reabrir na página inicial.",
            icon=":material/school:",
        )


def _reabrir_tutorial():
    st.session_state["tutorial_visto"] = False
    st.session_state.pop("tutorial", None)
    st.session_state.pop("checklist_escondido", None)


def _andar_no_tutorial(passo):
    estado = st.session_state["tutorial"]
    total = len(tutorial.passos(estado["objetivo"]))
    novo = estado["passo"] + passo
    if novo >= total:
        _encerrar_tutorial(concluiu=True)
        return
    estado["passo"] = max(0, novo)
    atual = tutorial.passo_atual(estado["objetivo"], estado["passo"])
    if (
        atual.chave == "gere"
    ):  # o passo do relatório já abre o estúdio no modelo Executivo
        _preparar_o_estudio(relatorios.ATIVO)
        st.session_state["tutorial_ir_para"] = "relatorio"


def _ir_pelo_tutorial(chave_da_pagina):
    if (
        chave_da_pagina == "relatorio"
        and st.session_state.get("tutorial", {}).get("objetivo") == tutorial.ANALISAR
    ):
        _preparar_o_estudio(relatorios.ATIVO)
    st.session_state["tutorial_ir_para"] = chave_da_pagina


def _explicar_dois_numeros(c):
    """A mini-lição do passo "Leia dois números", com os números do ativo aberto."""
    total = float(ind.calcular_retorno_acumulado(c.retorno).iloc[-1])
    queda = float(ind.calcular_drawdown(c.fechamento).min())
    rotulo = PERIODOS_DO_TOPO.get(c.periodo, c.periodo)
    st.markdown(
        f"- **Retorno total ({formatar_pct(total, com_sinal=True)}):** quem comprou {c.ticker} no "
        f"primeiro dia dos últimos {rotulo} e vendeu no último teria essa variação, antes de "
        "impostos e custos.\n"
        f"- **Maior queda ({formatar_pct(queda)}):** em algum momento, quem tinha "
        "comprado no topo chegou a ver esse prejuízo no papel. É uma medida do susto, não "
        "do resultado final.\n\n"
        "Os dois descrevem o **passado**: não dizem o que vai acontecer."
    )


def mostrar_tutorial(pagina_atual, c=None):
    """A faixa do tutorial: passo atual, progresso, o que falta e os botões (sem bloquear a
    tela: a pessoa continua usando tudo normalmente)."""
    destino = st.session_state.pop("tutorial_ir_para", None)
    if destino and destino != pagina_atual:
        st.switch_page(PAGINAS_DO_MENU[destino])
    estado = st.session_state.get("tutorial")
    if not estado:
        return
    objetivo = tutorial.OBJETIVOS[estado["objetivo"]]
    roteiro = tutorial.passos(objetivo.chave)
    passo = tutorial.passo_atual(objetivo.chave, estado["passo"])
    feitos = acoes_feitas()
    cumprido = tutorial.pode_continuar(passo, feitos)
    with st.container(border=True, key="tl-tutorial"):
        st.caption(
            f"Tutorial · {objetivo.nome_do_roteiro} · passo {estado['passo'] + 1} de "
            f"{len(roteiro)}"
        )
        st.progress((estado["passo"] + 1) / len(roteiro))
        st.markdown(f"**{passo.titulo}**")
        st.markdown(passo.texto)
        if passo.chave == "explore" and c is not None and pagina_atual == "visao_geral":
            if st.button(
                "Mostrar como ler", icon=":material/lightbulb:", key="tut_ler"
            ):
                marcar_feito("leu_os_numeros")
                cumprido = True
            if "leu_os_numeros" in acoes_feitas():
                _explicar_dois_numeros(c)
        if passo.chave == "pronto" and objetivo.chave == tutorial.ANALISAR:
            col_fav, col_outro = st.columns(2)
            ticker = normalizar_ticker(st.session_state.get("ticker", ""))
            if ticker not in st.session_state.get("favoritos", []):
                col_fav.button(
                    f"Adicionar {ticker} aos favoritos",
                    icon=":material/star:",
                    key="tut_favoritar",
                    on_click=_alternar_favorito_atual,
                )
            col_outro.button(
                "Analisar outro ativo",
                icon=":material/search:",
                key="tut_outro",
                on_click=_ir_pelo_tutorial,
                args=("inicio",),
            )
        if not cumprido:
            st.caption(f"Falta: {passo.pendente}")
            if passo.pagina != pagina_atual:
                st.button(
                    f"Ir para {pagina(passo.pagina).titulo}",
                    icon=":material/arrow_forward:",
                    key="tut_ir",
                    on_click=_ir_pelo_tutorial,
                    args=(passo.pagina,),
                )
        col_voltar, col_seguir, col_pular = st.columns([1, 1, 1])
        col_voltar.button(
            "Voltar",
            icon=":material/arrow_back:",
            key="tut_voltar",
            disabled=estado["passo"] == 0,
            on_click=_andar_no_tutorial,
            args=(-1,),
            width="stretch",
        )
        ultimo = estado["passo"] == len(roteiro) - 1
        col_seguir.button(
            "Concluir" if ultimo else "Continuar",
            type="primary",
            icon=":material/check:" if ultimo else ":material/arrow_forward:",
            key="tut_seguir",
            disabled=not cumprido,
            on_click=_andar_no_tutorial,
            args=(1,),
            width="stretch",
        )
        col_pular.button(
            "Pular tutorial",
            key="tut_pular",
            on_click=_encerrar_tutorial,
            args=(False,),
            width="stretch",
        )
    destino = st.session_state.pop("tutorial_ir_para", None)
    if destino and destino != pagina_atual:
        st.switch_page(PAGINAS_DO_MENU[destino])


def mostrar_portas_de_entrada():
    """'O que você quer fazer hoje?': três objetivos, não três níveis técnicos."""
    st.subheader("O que você quer fazer hoje?")
    for i, (coluna, objetivo) in enumerate(
        zip(st.columns(3), tutorial.OBJETIVOS.values(), strict=True)
    ):
        with coluna, st.container(border=True, height=176, key=f"tl-cartao-porta-{i}"):
            st.markdown(f"#### {objetivo.icone} {objetivo.titulo}")
            st.caption(objetivo.descricao)
            st.button(
                "Começar",
                key=f"tut_porta_{objetivo.chave}",
                icon=":material/play_arrow:",
                on_click=_comecar_tutorial,
                args=(objetivo.chave,),
            )
    st.button(
        "Pular: já sei usar",
        key="tut_pular_portas",
        on_click=_encerrar_tutorial,
        args=(False,),
        type="tertiary",
    )


def mostrar_lista_de_tarefas():
    """Três primeiras ações, discretas; some quando tudo foi feito ou quando a pessoa esconde."""
    if st.session_state.get("checklist_escondido"):
        return
    feitos = acoes_feitas()
    if not tutorial.tarefas_pendentes(feitos):
        return
    with st.container(border=True, key="tl-primeiros-passos"):
        col_titulo, col_esconder = st.columns([4, 1], vertical_alignment="center")
        col_titulo.markdown(
            f"**Primeiros passos** · {len(tutorial.TAREFAS) - len(tutorial.tarefas_pendentes(feitos))} "
            f"de {len(tutorial.TAREFAS)}"
        )
        if col_esconder.button("Esconder", key="tut_esconder", type="tertiary"):
            st.session_state["checklist_escondido"] = True
            st.rerun()
        for tarefa in tutorial.TAREFAS:
            if tarefa.chave in feitos:
                st.markdown(f":material/check_circle: ~~{tarefa.rotulo}~~")
            else:
                st.page_link(
                    PAGINAS_DO_MENU[tarefa.pagina],
                    label=tarefa.rotulo,
                    icon=":material/radio_button_unchecked:",
                )


def pagina_inicio():
    if st.session_state.pop("ir_para_visao_geral", False):
        st.switch_page(PAGINAS_DO_MENU["visao_geral"])
    mostrar_tutorial("inicio")
    st.markdown(
        '<div class="tl-olho">Ações da B3 e dos EUA</div>', unsafe_allow_html=True
    )
    st.markdown(
        '<div class="tl-hero">Entenda uma ação antes de investir.</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        "Retorno, risco e testes de estratégia **no passado**, com custos e cada número "
        "explicado em português: passe o mouse no **?**."
    )
    col_ativo, col_analisar, col_guia = st.columns(
        [3, 1, 1], vertical_alignment="bottom"
    )
    col_ativo.selectbox(
        "Busque código ou empresa",
        catalogo.simbolos(),
        index=None,
        format_func=catalogo.rotulo,
        key="ativo_do_inicio",
        placeholder="PETR4, Petrobras, AAPL, Ibovespa…",
        accept_new_options=True,
        on_change=_analisar_o_ativo_do_inicio,
        help="Escolha na lista para abrir a análise. Não precisa saber o sufixo .SA.",
    )
    col_analisar.button(
        "Analisar ativo",
        type="primary",
        key="comecar",
        width="stretch",
        on_click=_analisar_o_ativo_do_inicio,
    )
    recentes = st.session_state.get("recentes", [])
    st.pills(
        "Recentes" if recentes else "Experimente",
        recentes or list(catalogo.EXEMPLOS),
        format_func=lambda s: catalogo.rotulo(s).split(" · ")[0],
        key="atalho_do_inicio",
        on_change=_analisar_o_atalho,
        args=("atalho_do_inicio",),
    )
    col_guia.page_link(
        PAGINAS_DO_MENU["guia"], label="Ver o guia", icon=":material/menu_book:"
    )

    if not st.session_state.get("tutorial") and not st.session_state.get(
        "tutorial_visto"
    ):
        mostrar_portas_de_entrada()
    mostrar_lista_de_tarefas()

    st.subheader("O que dá para fazer")
    cartoes = [
        (
            ":material/dashboard:",
            "Analisar ativo",
            "Retorno, risco e comportamento de uma ação, índice ou cripto.",
            "visao_geral",
            None,
        ),
        (
            ":material/history:",
            "Testar estratégia",
            "Repita uma regra de compra e venda no passado, com custos.",
            "backtest",
            None,
        ),
        (
            ":material/picture_as_pdf:",
            "Gerar relatório",
            "Um PDF com os números, os gráficos e cada termo explicado.",
            "relatorio",
            None,
        ),
        (
            ":material/account_balance_wallet:",
            "Minha carteira (B3)",
            "Envie a planilha da Área do Investidor e veja concentração e risco.",
            "relatorio",
            relatorios.MINHA_CARTEIRA,
        ),
    ]
    for i, (coluna, (icone, titulo, texto, destino, tipo)) in enumerate(
        zip(st.columns(4), cartoes, strict=True)
    ):
        with coluna, st.container(border=True, height=196, key=f"tl-cartao-{i}"):
            st.markdown(f"#### {icone} {titulo}")
            st.caption(texto)
            if tipo is None:
                st.page_link(
                    PAGINAS_DO_MENU[destino],
                    label="Abrir",
                    icon=":material/arrow_forward:",
                )
            else:
                atalho_para_o_relatorio(tipo, rotulo="Abrir", chave=f"inicio_{tipo}")

    st.subheader("Como o TickerLab trabalha")
    principios = [
        ("Sem olhar o futuro", "A decisão de um dia só vale no dia seguinte."),
        ("Com custos", "Corretagem, impostos e o CDI entram em todo teste."),
        ("Honesto", "O app mostra quando uma estratégia não funciona."),
        ("Explicado", "Cada termo técnico vem com uma explicação em português."),
    ]
    for coluna, (titulo, texto) in zip(st.columns(4), principios, strict=True):
        coluna.markdown(
            f'<div class="tl-principio"><b>{titulo}</b>{texto}</div>',
            unsafe_allow_html=True,
        )

    if st.session_state.get("usuario") is not None:
        limites = limites_do(plano_atual())
        st.divider()
        st.info(
            f"Você está no plano **{limites.nome}**. "
            "Veja o que cada plano inclui em **Planos e assinatura**."
        )
        st.page_link(
            PAGINAS_DO_MENU["planos"],
            label="Planos e assinatura",
            icon=":material/workspace_premium:",
        )
    if st.session_state.get("tutorial_visto") and not st.session_state.get("tutorial"):
        st.button(
            "Reabrir o tutorial",
            icon=":material/school:",
            key="tut_reabrir",
            type="tertiary",
            on_click=_reabrir_tutorial,
        )


# --- Funções das páginas (as que ainda não saíram para telas/) -----------------------------


def pagina_relatorio():
    cabecalho_da_pagina("relatorio")
    c = carregar_contexto()
    # o lugar da faixa fica no topo, mas ela é desenhada no fim: assim já enxerga o que o
    # estúdio acabou de fazer (prévia pronta, carteira carregada) e libera o "Continuar"
    lugar_do_tutorial = st.container()
    usuario = st.session_state.get("usuario")
    limites = limites_do(plano_atual())
    aba_estudio, aba_biblioteca = st.tabs(
        [":material/edit_document: Estúdio", ":material/folder_open: Meus relatórios"]
    )
    with aba_estudio:
        mostrar_estudio(usuario, limites, c)
    with aba_biblioteca:
        mostrar_biblioteca(usuario)
    with lugar_do_tutorial:
        mostrar_tutorial("relatorio", c)


def pagina_visao_geral():
    cabecalho_da_pagina("visao_geral")
    c = carregar_contexto()
    mostrar_tutorial("visao_geral", c)
    atalho_para_o_relatorio(relatorios.ATIVO)
    r = parametros_em_vigor(c.ticker)
    secao_painel_de_numeros(
        c.fechamento, c.retorno, c.taxa_livre_de_risco, int(r["quant.var_confianca"])
    )
    st.divider()
    medias = ("tecnica.media_rapida", "tecnica.media_lenta")
    personalizou_medias = any(r.origem(k) != research_presets.SISTEMA for k in medias)
    secao_preco(
        c.dados, tuple(int(r[k]) for k in medias) if personalizou_medias else ()
    )
    st.divider()
    secao_tendencia_e_volume(c.dados, r)
    avisar_parametros(
        r,
        (
            "quant.var_confianca",
            *medias,
            "tecnica.adx_periodo",
            "tecnica.adx_tendencia",
            "tecnica.volume_janela",
            "tecnica.periodicidade",
        ),
    )
    st.download_button(
        "Baixar os preços (CSV)",
        converter_para_csv(montar_tabela_de_precos(c.dados)),
        file_name=f"{c.ticker}_{c.periodo}.csv",
        mime="text/csv",
        help="Preços, volume e retorno diário, prontos para abrir no Excel (separador ponto e vírgula).",
    )


# --- Menu: a função de cada página ----------------------------------------------------------
FUNCOES_DAS_PAGINAS = {
    "inicio": pagina_inicio,
    "relatorio": pagina_relatorio,
    "parametros": pagina_parametros,
    "research": pagina_research,
    "fundamentos": pagina_fundamentos,
    "por_dentro": pagina_por_dentro,
    "donos": pagina_donos,
    "newsletter": pagina_newsletter,
    "alertas": pagina_alertas,
    "carteira_research": pagina_carteira_research,
    "trade": pagina_trade,
    "guia": pagina_guia,
    "termos": pagina_termos,
    "privacidade": pagina_privacidade,
    "visao_geral": pagina_visao_geral,
    "risco": pagina_risco,
    "retorno_mensal": pagina_retorno_mensal,
    "comparar": pagina_comparar,
    "correlacao": pagina_correlacao,
    "backtest": pagina_backtest,
    "ranking": pagina_ranking,
    "carteira": pagina_carteira,
    "experimentos": pagina_experimentos,
    "regimes": pagina_regimes,
    "aprendizado": pagina_aprendizado,
    "pares": pagina_pares,
    "simulacoes": pagina_simulacoes,
    "meus_dados": pagina_meus_dados,
    "admin": pagina_admin,
    "momentum": pagina_momentum,
    "planos": pagina_planos,
}


def montar_navegacao(e_admin=False):
    """O menu do topo: um grupo por seção; páginas do Pro ganham cadeado no plano Gratuito."""
    plano = plano_atual()
    estrutura = {}
    for grupo in GRUPOS:
        itens = []
        for p in paginas_do_grupo(grupo):
            if p.somente_admin and not e_admin:
                continue
            bloqueada = p.recurso is not None and not pode_usar(plano, p.recurso)
            e_a_inicial = p.chave == PAGINA_INICIAL
            pagina_do_menu = st.Page(
                FUNCOES_DAS_PAGINAS[p.chave],
                title=p.titulo,
                icon=":material/lock:" if bloqueada else p.icone,
                url_path="" if e_a_inicial else p.url,
                default=e_a_inicial,
                visibility="visible" if p.no_menu else "hidden",
            )
            PAGINAS_DO_MENU[p.chave] = pagina_do_menu
            itens.append(pagina_do_menu)
        if itens:
            estrutura[grupo] = itens
    return estrutura


# --- Programa principal --------------------------------------------------------
usuario_logado = obter_usuario_logado()
carregar_da_conta(usuario_logado)
preparar_estado_inicial()
manter_estado()
pagina_atual = st.navigation(
    montar_navegacao(e_admin=bool(usuario_logado and usuario_logado.e_admin)),
    position="top",
)
mostrar_topo(usuario_logado)
if usuario_logado is not None:
    if st.session_state.pop("primeira_vez", False):
        st.toast(
            f"Bem-vindo ao TickerLab, {usuario_logado.nome or usuario_logado.email}!"
        )
    mostrar_retorno_do_pagamento()
pagina_atual.run()

st.divider()
col_aviso, col_guia, col_termos, col_privacidade = st.columns(
    [5, 1, 1.2, 1.2], vertical_alignment="center"
)
col_aviso.markdown(
    '<div class="tl-rodape"><b>Ticker<span>Lab</span></b> · projeto educacional, não é '
    "recomendação de investimento. Dados do Yahoo Finance, que podem ter atraso ou erros. "
    "Rentabilidade passada não garante resultado futuro.</div>",
    unsafe_allow_html=True,
)
col_guia.page_link(PAGINAS_DO_MENU["guia"], label="Guia")
col_termos.page_link(PAGINAS_DO_MENU["termos"], label="Termos de uso")
col_privacidade.page_link(PAGINAS_DO_MENU["privacidade"], label="Privacidade")
