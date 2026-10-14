"""TickerLab: a entrada do app. Configura a página, monta o menu e roda a página escolhida.

As telas ficam em telas/ (uma pasta ou um arquivo por grupo de páginas) e os cálculos em src/.
"""

import streamlit as st

from src import marca, tema_do_app
from src.estilo import CSS_DO_APP
from src.link import ler_parametros
from src.logs import configurar_logs
from src.paginas import GRUPOS, PAGINA_INICIAL, PAGINAS, paginas_do_grupo
from src.planos import pode_usar
from telas.analise import (
    pagina_comparar,
    pagina_correlacao,
    pagina_retorno_mensal,
    pagina_risco,
    pagina_visao_geral,
)
from telas.carteira_b3 import pagina_carteira_b3
from telas.comum import PAGINAS_DO_MENU, paleta_da_sessao, plano_atual
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
from telas.inicio import pagina_inicio
from telas.momentum import pagina_momentum
from telas.relatorios.pagina import pagina_relatorio
from telas.research.acontecimentos import pagina_research
from telas.research.alertas import pagina_alertas
from telas.research.diario_de_teses import pagina_diario_de_teses
from telas.research.donos import pagina_donos
from telas.research.fundamentos import pagina_fundamentos
from telas.research.juros_e_inflacao import pagina_juros_e_inflacao
from telas.research.linha_do_tempo import pagina_linha_do_tempo
from telas.research.minha_carteira import pagina_carteira_research
from telas.research.newsletter import pagina_newsletter
from telas.research.parametros import pagina_parametros
from telas.research.por_dentro import pagina_por_dentro
from telas.research.pulse import pagina_pulse
from telas.research.relatorio_empresa import pagina_relatorio_empresa
from telas.trade import pagina_trade

configurar_logs()
st.set_page_config(
    page_title="TickerLab", page_icon=str(marca.ARQUIVO_DO_ICONE), layout="wide"
)
st.markdown(f"<style>{CSS_DO_APP}</style>", unsafe_allow_html=True)
# símbolo + "TickerLab" no canto do menu (clicar volta ao Início), na versão do tema de quem vê;
# só o símbolo se faltar espaço
st.logo(str(marca.arquivo_da_assinatura(paleta_da_sessao())), size="large")


# --- Cabeçalho e entradas -----------------------------------------------------


def preparar_estado_inicial():
    """Valores iniciais dos campos do topo; na primeira visita, lê os da URL (link compartilhado)."""
    padroes = {
        "ticker": "PETR4.SA",
        "periodo": "2y",
        "taxa": "Zero",
        "favoritos": [],
        "tema_do_app": tema_do_app.PADRAO,
    }
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


# --- Menu: a função de cada página ----------------------------------------------------------
# endereço de cada página no navegador (o Streamlit guarda o tema por endereço)
ENDERECOS_DAS_PAGINAS = ["/", *(f"/{p.url}" for p in PAGINAS)]
FUNCOES_DAS_PAGINAS = {
    "inicio": pagina_inicio,
    "relatorio": pagina_relatorio,
    "parametros": pagina_parametros,
    "research": pagina_research,
    "pulse": pagina_pulse,
    "diario_de_teses": pagina_diario_de_teses,
    "fundamentos": pagina_fundamentos,
    "relatorio_empresa": pagina_relatorio_empresa,
    "carteira_b3": pagina_carteira_b3,
    "juros_e_inflacao": pagina_juros_e_inflacao,
    "linha_do_tempo": pagina_linha_do_tempo,
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
# o tema escolhido (claro, escuro ou automático pelo sol): o script grava a escolha onde o
# Streamlit lê o tema e recarrega uma vez se a página abriu no tema errado (src/tema_do_app.py)
st.html(
    tema_do_app.script(
        st.session_state["tema_do_app"],
        ENDERECOS_DAS_PAGINAS,
        guardada=st.session_state.get("tema_escolhido", False),
    ),
    unsafe_allow_javascript=True,
)
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
    '<div class="tl-rodape"><b>Ticker<span>Lab</span></b> · plataforma de inteligência financeira; não é '
    "recomendação de investimento. Dados do Yahoo Finance, que podem ter atraso ou erros. "
    "Rentabilidade passada não garante resultado futuro.</div>",
    unsafe_allow_html=True,
)
col_guia.page_link(PAGINAS_DO_MENU["guia"], label="Guia")
col_termos.page_link(PAGINAS_DO_MENU["termos"], label="Termos de uso")
col_privacidade.page_link(PAGINAS_DO_MENU["privacidade"], label="Privacidade")
