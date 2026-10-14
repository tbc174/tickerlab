"""Entrada no app: login com o Google, o usuário da sessão e o aceite dos termos.

Saiu do `app.py` sem mudar comportamento. Regra de `telas/`: nenhum estado mutável no módulo
(um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import logging
import time

import streamlit as st

from src import marca
from src.autenticacao import (
    AVISO_DA_ENTRADA,
    LoginInvalidoError,
    emails_de_admin,
    esta_em_producao,
    ler_identidade,
    login_esta_configurado,
    registrar_login,
)
from src.banco.conexao import obter_engine
from src.banco.usuarios import buscar_por_id
from src.cobranca import buscar_assinatura
from src.conformidade import (
    CAIXA_DO_ACEITE,
    INTRODUCAO_DO_ACEITE,
    TITULO_DO_ACEITE,
    aceitar_os_termos,
    precisa_aceitar_os_termos,
)
from src.envio_novidades import TEXTO_DO_CONSENTIMENTO as TEXTO_DAS_NOVIDADES
from src.origem import NOME_DO_COOKIE, ler_origem
from telas.comum import paleta_da_sessao
from telas.conta.assinatura import _recarregar_o_plano
from telas.conta.textos_legais import _corpo_do_texto

# o mesmo logger do telas/comum.py (o nome fixo faz o Python devolver o mesmo objeto)
log_da_conta = logging.getLogger("tickerlab.conta")


def marca_html(paleta=marca.PALETA_ESCURA):
    """O símbolo com o nome, para as telas sem menu (entrada e aceite dos termos). O topo do
    símbolo segue o tema: claro no escuro, marinho no claro (o manual, seção 2)."""
    simbolo = marca.simbolo_svg(topo=paleta.simbolo_topo)
    return f'<div class="tl-marca">{simbolo}<div>Ticker<span>Lab</span></div></div>'


def mostrar_tela_de_entrada():
    """Tela para quem ainda não entrou: o app só abre depois do login com o Google."""
    _, centro, _ = st.columns([1, 3, 1])
    with centro:
        st.markdown(marca_html(paleta_da_sessao()), unsafe_allow_html=True)
        st.markdown(
            '<div class="tl-hero">Entenda uma ação antes de investir.</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            "Entre com a sua conta do Google para analisar ações, testar estratégias "
            "no passado e guardar o que você fizer."
        )
        st.button("Entrar com o Google", type="primary", on_click=st.login)
        st.caption(AVISO_DA_ENTRADA)


def _recusar_abrir_sem_login():
    """Produção sem o `[auth]` completo: o app não abre (o modo local liberaria tudo a todos)."""
    logging.getLogger(__name__).error(
        "Produção sem o login configurado ([auth] do secrets.toml): o app não vai abrir"
    )
    st.error("O TickerLab está em manutenção. Tente de novo em alguns minutos.")
    st.stop()


def _usuario_da_sessao():
    """O usuário da sessão (ou None no modo local, sem contas). Para a página se não houver login."""
    if not login_esta_configurado(_segredos()):
        if esta_em_producao():
            _recusar_abrir_sem_login()
        return None
    if not st.user.get("is_logged_in", False):
        mostrar_tela_de_entrada()
        st.stop()
    retorno = st.query_params.get("assinatura")
    if retorno in ("ok", "cancelada"):
        st.session_state["retorno_do_pagamento"] = retorno
        _recarregar_o_plano()
    atual = st.session_state.get("usuario")
    if atual is not None and atual.google_sub == st.user.get("sub"):
        return _com_plano_atualizado(atual)
    try:
        usuario, primeira_vez = registrar_login(
            ler_identidade(st.user.to_dict()),
            admins=emails_de_admin(),
            # gravado pelo site: o Google apaga as UTMs da URL no caminho do login
            origem=ler_origem(st.context.cookies.get(NOME_DO_COOKIE)),
        )
    except LoginInvalidoError as erro:
        st.error(f"Não foi possível entrar: {erro}")
        st.button("Sair", on_click=st.logout)
        st.stop()
    except Exception:
        logging.getLogger(__name__).exception("Falha ao registrar o login")
        st.error(
            "O serviço de contas está indisponível agora. Tente de novo em instantes."
        )
        st.stop()
    st.session_state["usuario"] = usuario
    st.session_state["usuario_em"] = time.monotonic()
    st.session_state["primeira_vez"] = primeira_vez
    _carregar_assinatura(usuario)
    return usuario


SEGUNDOS_ATE_RELER_O_USUARIO = 60


def _com_plano_atualizado(usuario):
    """Relê o usuário do banco a cada minuto: o plano pode mudar fora desta sessão."""
    agora = time.monotonic()
    if agora - st.session_state.get("usuario_em", 0) < SEGUNDOS_ATE_RELER_O_USUARIO:
        return usuario
    st.session_state["usuario_em"] = agora
    try:
        with obter_engine().connect() as conexao:
            novo = buscar_por_id(conexao, usuario.id)
    except Exception:
        logging.getLogger(__name__).exception("Falha ao reler o usuário")
        return usuario
    if novo is None:  # a conta foi apagada
        st.session_state.pop("usuario", None)
        st.error("Esta conta não existe mais.")
        st.button("Sair", on_click=st.logout)
        st.stop()
    st.session_state["usuario"] = novo
    _carregar_assinatura(novo)
    return novo


def _carregar_assinatura(usuario):
    """Guarda na sessão a assinatura do Stripe do usuário (ou None)."""
    try:
        with obter_engine().connect() as conexao:
            st.session_state["assinatura"] = buscar_assinatura(conexao, usuario.id)
    except Exception:
        logging.getLogger(__name__).exception("Falha ao ler a assinatura")
        st.session_state["assinatura"] = None


def _segredos():
    try:
        return st.secrets
    except FileNotFoundError:
        return None


def _registrar_aceite(usuario):
    """O aceite dos termos e, se a caixa opcional foi marcada, a inscrição nas Novidades (na
    mesma transação). A caixa desmarcada não tira ninguém: quem já recebe sai em Meus dados."""
    quer_novidades = bool(st.session_state.get("aceite_das_novidades"))
    try:
        with obter_engine().begin() as conexao:
            aceitar_os_termos(conexao, usuario.id, quer_novidades)
    except Exception:
        log_da_conta.exception("Falha ao registrar o aceite dos termos")
        st.toast("Não consegui registrar o aceite agora. Tente de novo em instantes.")
        return
    st.session_state.pop(
        "usuario", None
    )  # a próxima execução relê o usuário já com o aceite


def mostrar_aceite_dos_termos(usuario):
    """Tela de primeiro acesso (ou de termos novos): o app só abre depois do aceite."""
    _, centro, _ = st.columns([1, 3, 1])
    with centro:
        st.markdown(marca_html(paleta_da_sessao()), unsafe_allow_html=True)
        st.markdown(
            f'<div class="tl-hero">{TITULO_DO_ACEITE}</div>', unsafe_allow_html=True
        )
        st.markdown(INTRODUCAO_DO_ACEITE)
        with st.expander("Termos de uso"):
            st.markdown(_corpo_do_texto("termos"))
        with st.expander("Política de privacidade"):
            st.markdown(_corpo_do_texto("privacidade"))
        aceitou = st.checkbox(
            CAIXA_DO_ACEITE,
            key="aceite_dos_termos",
        )
        st.checkbox(
            f"Opcional: {TEXTO_DAS_NOVIDADES}",
            value=False,  # opt-in: começa desmarcada e não é condição para usar o app
            key="aceite_das_novidades",
        )
        st.button(
            "Continuar",
            type="primary",
            disabled=not aceitou,
            on_click=_registrar_aceite,
            args=(usuario,),
        )
        st.button("Sair", on_click=st.logout)


def obter_usuario_logado():
    """O usuário da sessão, já com os termos aceitos (ou None no modo local)."""
    usuario = _usuario_da_sessao()
    if usuario is not None and precisa_aceitar_os_termos(usuario):
        mostrar_aceite_dos_termos(usuario)
        st.stop()
    return usuario
