"""Research: Newsletter (etapa 4): a edição na tela, o PDF e a inscrição por e-mail.

Saiu do `app.py` sem mudar comportamento. Regra de `telas/`: nenhum estado mutável no módulo
(um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import logging

import streamlit as st
from sqlalchemy import exc as sa_exc

from src import edicao as edicao_do_banco
from src import envio_newsletter, newsletter, relatorios
from src.banco import newsletter_por_email
from src.banco.conexao import obter_engine, tabela_inexistente
from src.conteudo import texto_da_fonte
from telas.comum import (
    PAGINAS_DO_MENU,
    avisar_parametros,
    cabecalho_da_pagina,
    parametros_em_vigor,
)
from telas.conta.guarda import so_com_a_conta_valendo
from telas.research.comum import (
    _carteira_da_lista,
    _listas_do_research,
    _sem_banco_agora,
)

JANELAS_DA_NEWSLETTER = {1: "1 dia", 7: "7 dias", 30: "30 dias", 90: "90 dias"}


class BancoIndisponivelError(ValueError):
    """O banco não respondeu (não é o mesmo que "ainda não coletado")."""


def _edicao(nome, tickers, janela, carteira=None):
    """A edição da lista com os seus parâmetros (None se o banco ainda não tem as tabelas).

    Levanta `BancoIndisponivelError` se o banco não respondeu: a tela diz isso, e não que os
    documentos ainda não foram coletados (achado D-2 do Master v3).
    """
    try:
        with obter_engine().connect() as conexao:
            return edicao_do_banco.montar_edicao(
                conexao,
                nome,
                tickers,
                janela,
                parametros_em_vigor(None),
                relatorios.agora(),
                carteira,
            )
    except (sa_exc.OperationalError, sa_exc.ProgrammingError) as erro:
        if tabela_inexistente(erro):
            return None
        logging.getLogger(__name__).exception("Falha ao ler a edição da Newsletter")
        raise BancoIndisponivelError(_sem_banco_agora("os documentos")) from erro


def _mostrar_secao_da_newsletter(secao):
    st.markdown(f"#### {secao.titulo}")
    if not secao.itens:
        st.caption(secao.vazio)
        return
    # título, texto e trechos saem das fontes (assunto, empresa, frases): nunca Markdown (7d)
    for item in secao.itens:
        texto = f"**{texto_da_fonte(item.titulo)}**  \n{texto_da_fonte(item.texto)}"
        if item.link:
            texto += f"  \n[Abrir o documento original na {item.sigla_da_fonte}]({item.link})"
        st.markdown(texto)
        if item.trechos:
            st.caption(
                f"{newsletter.TITULO_DOS_TRECHOS}:  \n"
                + "  \n".join(f"“{texto_da_fonte(t)}”" for t in item.trechos)
            )
        if item.razoes:
            st.caption("Por que aparece: " + " · ".join(item.razoes))


@so_com_a_conta_valendo
def _inscrever_na_newsletter(usuario):
    lista = st.session_state["newsletter_email_lista"]
    cadencia = st.session_state["newsletter_email_cadencia"]
    with obter_engine().begin() as conexao:
        newsletter_por_email.inscrever(
            conexao,
            usuario.id,
            lista,
            cadencia,
            envio_newsletter.VERSAO_DO_CONSENTIMENTO,
        )
    st.session_state["newsletter_email_consentimento"] = False
    st.toast(
        f'Inscrito: "{lista}", {envio_newsletter.NOMES_DAS_CADENCIAS[cadencia].lower()}.'
    )


@so_com_a_conta_valendo
def _cancelar_a_newsletter(usuario):
    with obter_engine().begin() as conexao:
        newsletter_por_email.cancelar(conexao, usuario.id)
    st.toast("Inscrição cancelada: você não recebe mais a Newsletter por e-mail.")


def _mostrar_inscricao_por_email(usuario, nomes):
    """Receber por e-mail (etapa 5c). Com a trava ligada, só para administradores."""
    if usuario is None or (envio_newsletter.so_para_admins() and not usuario.e_admin):
        return
    try:
        with obter_engine().connect() as conexao:
            atual = newsletter_por_email.inscricao(conexao, usuario.id)
    except (sa_exc.OperationalError, sa_exc.ProgrammingError):
        return  # banco sem a tabela (modo local sem migrar)
    rotulo = "Receber por e-mail" + (
        " (em teste: só administradores)" if envio_newsletter.so_para_admins() else ""
    )
    with st.expander(rotulo, icon=":material/mail:"):
        if atual is not None:
            st.markdown(
                f"Inscrito na lista **{atual.lista}**, "
                f"{envio_newsletter.NOMES_DAS_CADENCIAS[atual.cadencia].lower()}, desde "
                f"{atual.inscrito_em.astimezone(relatorios.FUSO):%d/%m/%Y}."
            )
            st.button(
                "Cancelar a inscrição", key="newsletter_email_cancelar",
                icon=":material/unsubscribe:", on_click=_cancelar_a_newsletter, args=(usuario,),
            )  # fmt: skip
        col_lista, col_cadencia = st.columns(2)
        col_lista.selectbox("Lista", nomes, key="newsletter_email_lista")
        col_cadencia.selectbox(
            "Frequência",
            list(envio_newsletter.NOMES_DAS_CADENCIAS),
            format_func=envio_newsletter.NOMES_DAS_CADENCIAS.get,
            key="newsletter_email_cadencia",
        )
        consentiu = st.checkbox(
            envio_newsletter.TEXTO_DO_CONSENTIMENTO,
            key="newsletter_email_consentimento",
        )
        st.button(
            "Trocar a inscrição" if atual else "Inscrever", type="primary",
            key="newsletter_email_inscrever", icon=":material/mark_email_read:",
            disabled=not consentiu, on_click=_inscrever_na_newsletter, args=(usuario,),
        )  # fmt: skip
        st.caption(
            "A edição sai depois das coletas da manhã (a semanal, às segundas), uma vez por "
            "período, pelo Resend. Cada e-mail traz o link para sair."
        )


def _ir_para_o_pdf(nome, janela):
    st.session_state["tipo_de_relatorio"] = relatorios.NEWSLETTER
    st.session_state["relatorio_newsletter_lista"] = nome
    st.session_state["relatorio_newsletter_janela"] = janela
    st.session_state["ir_para_relatorio"] = True


def pagina_newsletter():
    cabecalho_da_pagina("newsletter")
    listas = _listas_do_research(st.session_state.get("usuario"))
    nomes = [lista[0] for lista in listas]
    col_lista, col_janela = st.columns([2, 3])
    escolhida = col_lista.selectbox("Lista", nomes, key="newsletter_lista")
    nome, tickers, _ = listas[nomes.index(escolhida)]
    cadencia = parametros_em_vigor(None)["newsletter.cadencia"]
    janela = col_janela.segmented_control(
        "Período",
        list(JANELAS_DA_NEWSLETTER),
        format_func=JANELAS_DA_NEWSLETTER.get,
        default=newsletter.JANELA_DA_CADENCIA.get(cadencia, 7),
        required=True,
        key="newsletter_janela",
        help="Começa na frequência escolhida em Parâmetros (diária: 1 dia; semanal: 7 dias).",
    )
    try:
        edicao = _edicao(nome, tickers, janela, _carteira_da_lista(nome))
    except BancoIndisponivelError as erro:
        st.error(str(erro))
        return
    if edicao is None:
        st.info(
            "Os documentos ainda não foram coletados neste servidor.",
            icon=":material/schedule:",
        )
        return
    st.caption(
        f"Edição de **{edicao.lista}**, de {edicao.inicio:%d/%m/%Y} a {edicao.fim:%d/%m/%Y}, "
        f"gerada em {edicao.gerada_em:%d/%m/%Y às %H:%M}. Montada só com fatos dos documentos "
        "oficiais, em frases de modelo fixo (sem inteligência artificial)."
    )
    st.button(
        "Gerar o PDF no Report Studio",
        icon=":material/picture_as_pdf:",
        key="newsletter_pdf",
        on_click=_ir_para_o_pdf,
        args=(nome, janela),
    )
    if st.session_state.pop("ir_para_relatorio", False):
        st.switch_page(PAGINAS_DO_MENU["relatorio"])
    for secao in edicao.secoes:
        _mostrar_secao_da_newsletter(secao)
    with st.expander("Parâmetros e fontes desta edição"):
        st.markdown("\n".join(f"- {frase}" for frase in edicao.parametros))
        st.markdown(
            "\n".join(f"- **{fonte}:** {quando}" for fonte, quando in edicao.fontes)
        )
    st.markdown("#### Limites")
    st.markdown("\n".join(f"- {frase}" for frase in edicao.limites))
    _mostrar_inscricao_por_email(st.session_state.get("usuario"), nomes)
    avisar_parametros(
        parametros_em_vigor(None),
        ("newsletter.cadencia", "newsletter.max_itens", "newsletter.temas"),
    )
