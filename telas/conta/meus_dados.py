"""Meus dados: a aparência (tema), as Novidades por e-mail (opt-in) e, pela LGPD, exportar,
baixar os PDFs e apagar a conta.

Saiu do `app.py` sem mudar comportamento. Regra de `telas/`: nenhum estado mutável no módulo
(um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import functools
import json
import logging

import streamlit as st

from src import tema_do_app
from src.banco import novidades_por_email
from src.banco.conexao import obter_engine
from src.banco.dados_do_usuario import carregar_preferencias, salvar_preferencias
from src.banco.pdfs_originais import pdfs_em_zip
from src.cobranca import buscar_assinatura, encerrar_cobranca
from src.conformidade import (
    TEXTO_PARA_CONFIRMAR_A_EXCLUSAO,
    apagar_conta,
    exportar_meus_dados,
)
from src.envio_novidades import TEXTO_DO_CONSENTIMENTO as TEXTO_DAS_NOVIDADES
from src.envio_novidades import VERSAO_DO_CONSENTIMENTO as VERSAO_DAS_NOVIDADES
from telas.compartilhar import mostrar_links_da_conta
from telas.comum import cabecalho_da_pagina

# o mesmo logger do telas/comum.py (o nome fixo faz o Python devolver o mesmo objeto)
log_da_conta = logging.getLogger("tickerlab.conta")


def _preparar_exportacao(usuario):
    try:
        with obter_engine().begin() as conexao:
            dados = exportar_meus_dados(conexao, usuario.id)
    except Exception:
        log_da_conta.exception("Falha ao exportar os dados")
        st.toast("Não consegui preparar o arquivo agora. Tente de novo em instantes.")
        return
    st.session_state["exportacao_json"] = json.dumps(
        dados, ensure_ascii=False, indent=2, default=str
    )


def _meus_pdfs_em_zip(usuario_id):
    """Os PDFs originais guardados, num .zip montado só na hora do clique (LGPD: portabilidade)."""
    with obter_engine().connect() as conexao:
        return pdfs_em_zip(conexao, usuario_id)


def _apagar_minha_conta(usuario):
    """Encerra a cobrança, apaga tudo e sai. Se a cobrança não puder ser encerrada, não apaga."""
    try:
        with obter_engine().connect() as conexao:
            assinatura = buscar_assinatura(conexao, usuario.id)
        encerrar_cobranca(assinatura)
        with obter_engine().begin() as conexao:
            apagar_conta(conexao, usuario.id)
    except Exception:
        log_da_conta.exception("Falha ao apagar a conta")
        st.toast(
            "Não consegui apagar a conta agora (a cobrança precisa ser encerrada antes). "
            "Tente de novo em instantes."
        )
        return
    st.session_state.clear()
    st.logout()


def _guardar_tema(usuario):
    """A escolha vale já nesta sessão e, com login, fica nas preferências da conta (mesclada com
    o que já estava guardado, como a configuração do Report Studio)."""
    escolha = tema_do_app.normalizar(st.session_state.get("escolha_do_tema"))
    st.session_state["tema_do_app"] = escolha
    st.session_state["tema_escolhido"] = True
    if usuario is None:
        return
    try:
        with obter_engine().begin() as conexao:
            guardadas = carregar_preferencias(conexao, usuario.id)
            salvar_preferencias(conexao, usuario.id, {**guardadas, "tema": escolha})
    except Exception:
        log_da_conta.exception("Falha ao salvar o tema na conta")
        st.toast(
            "Não consegui guardar o tema na sua conta agora; vale só nesta visita."
        )


def _mostrar_aparencia(usuario):
    st.subheader("Aparência")
    st.caption(
        "Automático: claro de dia e escuro à noite, pela hora do nascer e do pôr do sol na "
        "capital do fuso do seu aparelho (sem pedir a sua localização). A troca vale ao abrir "
        "ou recarregar uma página."
    )
    st.session_state.setdefault(
        "escolha_do_tema", st.session_state.get("tema_do_app", tema_do_app.PADRAO)
    )
    st.segmented_control(
        "Tema",
        options=list(tema_do_app.ESCOLHAS),
        format_func=tema_do_app.NOMES.get,
        required=True,
        key="escolha_do_tema",
        on_change=_guardar_tema,
        args=(usuario,),
    )


def _mudar_novidades(usuario, receber):
    try:
        with obter_engine().begin() as conexao:
            if receber:
                novidades_por_email.inscrever(conexao, usuario.id, VERSAO_DAS_NOVIDADES)
            else:
                novidades_por_email.cancelar(conexao, usuario.id)
    except Exception:
        log_da_conta.exception("Falha ao mudar a inscrição nas Novidades")
        st.toast("Não consegui guardar a escolha agora. Tente de novo em instantes.")
        return
    st.session_state.pop("novidades_consentimento", None)


def _mostrar_novidades(usuario):
    """Novidades e ofertas por e-mail: o opt-in fica aqui para quem não marcou no 1º acesso."""
    st.subheader("Novidades e ofertas por e-mail")
    try:
        with obter_engine().connect() as conexao:
            inscrita = novidades_por_email.inscricao(conexao, usuario.id)
    except Exception:
        log_da_conta.exception("Falha ao ler a inscrição nas Novidades")
        st.caption("Não consegui ler a sua escolha agora.")
        return
    if inscrita is not None:
        st.caption(
            f"Você recebe novidades e ofertas do TickerLab desde "
            f"{inscrita.inscrito_em:%d/%m/%Y}. Cada e-mail também traz um link para sair."
        )
        st.button(
            "Não quero mais receber",
            key="novidades_cancelar",
            on_click=_mudar_novidades,
            args=(usuario, False),
        )
        return
    st.caption(
        "O e-mail da sua conta serve só para a conta. Propaganda do TickerLab, só se você pedir."
    )
    marcou = st.checkbox(TEXTO_DAS_NOVIDADES, key="novidades_consentimento")
    st.button(
        "Quero receber",
        key="novidades_inscrever",
        disabled=not marcou,
        on_click=_mudar_novidades,
        args=(usuario, True),
    )


def pagina_meus_dados():
    cabecalho_da_pagina("meus_dados")
    usuario = st.session_state.get("usuario")
    _mostrar_aparencia(usuario)
    st.divider()
    if usuario is None:
        st.info("Sem login (modo local) não há conta nem dados pessoais guardados.")
        return
    _mostrar_novidades(usuario)
    st.divider()
    mostrar_exportacao(usuario)
    st.divider()
    mostrar_links_da_conta(usuario)
    st.divider()
    mostrar_apagar_a_conta(usuario)


def mostrar_exportacao(usuario):
    """Baixar a cópia dos dados (JSON) e os PDFs guardados (LGPD: acesso e portabilidade).

    Também na tela do aceite dos termos: não aceitar termos novos não tira esse direito.
    """
    st.subheader("Baixar uma cópia dos meus dados")
    st.caption(
        "Perfil, preferências, favoritos, simulações e situação da assinatura, em um "
        "arquivo JSON."
    )
    st.button(
        "Preparar o arquivo",
        key="preparar_exportacao",
        on_click=_preparar_exportacao,
        args=(usuario,),
    )
    if "exportacao_json" in st.session_state:
        st.download_button(
            "Baixar meus dados (JSON)",
            st.session_state["exportacao_json"],
            file_name="meus-dados-tickerlab.json",
            mime="application/json",
            key="baixar_meus_dados",
        )
    st.caption(
        "Os PDFs originais guardados na biblioteca vêm à parte, num .zip (o JSON lista cada um "
        "com o hash SHA-256)."
    )
    st.download_button(
        "Baixar meus PDFs guardados (.zip)",
        data=functools.partial(_meus_pdfs_em_zip, usuario.id),
        file_name="meus-pdfs-tickerlab.zip",
        mime="application/zip",
        key="baixar_meus_pdfs",
        on_click="ignore",
    )


def mostrar_apagar_a_conta(usuario):
    """Apagar a conta, com a palavra de confirmação (LGPD: eliminação; também na tela do aceite)."""
    st.subheader("Apagar a minha conta")
    st.warning(
        "Isto apaga **para sempre** o seu perfil, preferências, favoritos e simulações, "
        "e cancela a sua assinatura. Não dá para desfazer."
    )
    st.text_input(
        f"Para confirmar, digite {TEXTO_PARA_CONFIRMAR_A_EXCLUSAO}",
        key="confirmar_exclusao",
    )
    digitado = st.session_state.get("confirmar_exclusao", "").strip()
    st.button(
        "Apagar a minha conta e os meus dados",
        type="primary",
        key="apagar_minha_conta",
        disabled=digitado != TEXTO_PARA_CONFIRMAR_A_EXCLUSAO,
        on_click=_apagar_minha_conta,
        args=(usuario,),
    )
