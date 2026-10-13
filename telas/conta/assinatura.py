"""Planos e assinatura (Stripe em modo de teste), o menu da conta e os recursos por plano.

Saiu do `app.py` sem mudar comportamento. Regra de `telas/`: nenhum estado mutável no módulo
(um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import logging

import pandas as pd
import streamlit as st

from src.banco.conexao import obter_engine
from src.banco.dados_do_usuario import contar_simulacoes
from src.cobranca import (
    CobrancaIndisponivelError,
    cobranca_esta_configurada,
    criar_pagina_de_pagamento,
    criar_portal_da_assinatura,
    pode_assinar,
)
from src.planos import (
    NOMES_DOS_RECURSOS,
    descrever_limite,
    limites_do,
    pode_usar,
    tabela_de_planos,
)
from telas.comum import PAGINAS_DO_MENU, cabecalho_da_pagina, plano_atual

# o mesmo logger do telas/comum.py (o nome fixo faz o Python devolver o mesmo objeto)
log_da_conta = logging.getLogger("tickerlab.conta")

# decisão 0029: até a cobrança real, só administradores assinam (`src.cobranca.pode_assinar`)
AVISO_DE_PLANOS_EM_BREVE = "Os planos pagos chegam em breve."


def _recarregar_o_plano():
    st.session_state["usuario_em"] = 0  # a próxima execução relê o usuário


def mostrar_planos():
    st.dataframe(pd.DataFrame(tabela_de_planos()).set_index("Recurso"), width="stretch")


def _preparar_link_de_pagamento(onde):
    """Cria a página de pagamento do Stripe e guarda o endereço para o botão de link."""
    usuario = st.session_state["usuario"]
    # o botão nem aparece para quem não pode assinar; esta é a segunda barreira
    if not pode_assinar(usuario.e_admin):
        st.toast(AVISO_DE_PLANOS_EM_BREVE)
        return
    assinatura = st.session_state.get("assinatura")
    try:
        url = criar_pagina_de_pagamento(
            usuario.id,
            usuario.email,
            assinatura.stripe_customer_id if assinatura else None,
        )
    except CobrancaIndisponivelError:
        st.toast("O pagamento não está disponível agora.")
        return
    except Exception:
        log_da_conta.exception("Falha ao criar a página de pagamento")
        st.toast("Não consegui abrir o pagamento agora. Tente de novo em instantes.")
        return
    st.session_state["link_de_pagamento"] = (onde, url)


def _preparar_link_do_portal(onde):
    assinatura = st.session_state.get("assinatura")
    if assinatura is None:
        return
    try:
        url = criar_portal_da_assinatura(assinatura.stripe_customer_id)
    except Exception:
        log_da_conta.exception("Falha ao criar o portal da assinatura")
        st.toast("Não consegui abrir o portal agora. Tente de novo em instantes.")
        return
    st.session_state["link_de_pagamento"] = (onde, url)


def mostrar_assinatura(onde):
    """Botões para assinar o Pro ou gerenciar a assinatura (só com conta e Stripe ligado)."""
    usuario = st.session_state.get("usuario")
    if usuario is None:
        return
    if not cobranca_esta_configurada():
        st.caption("A assinatura do plano Pro ainda não está disponível.")
        return
    if usuario.plano in ("gratuito", "plus") and not pode_assinar(usuario.e_admin):
        st.caption(AVISO_DE_PLANOS_EM_BREVE)
        return
    assinatura = st.session_state.get("assinatura")
    if usuario.plano == "gratuito":
        st.caption("Plano Plus: a assinatura chega em breve.")
    if usuario.plano in ("gratuito", "plus"):
        st.button(
            "Assinar o plano Pro",
            key=f"assinar_{onde}",
            type="primary",
            on_click=_preparar_link_de_pagamento,
            args=(onde,),
        )
    elif assinatura is not None:
        st.button(
            "Gerenciar a assinatura",
            key=f"gerenciar_{onde}",
            on_click=_preparar_link_do_portal,
            args=(onde,),
        )
    link = st.session_state.get("link_de_pagamento")
    if link and link[0] == onde:
        st.link_button("Continuar no Stripe", link[1], width="stretch")
        st.caption(
            "Modo de teste: use o cartão 4242 4242 4242 4242, qualquer data futura."
        )


def mostrar_retorno_do_pagamento():
    retorno = st.session_state.pop("retorno_do_pagamento", None)
    if retorno == "ok":
        st.success(
            "Pagamento recebido! O plano muda assim que o Stripe confirmar, em poucos "
            "segundos."
        )
        st.button("Atualizar o meu plano", on_click=_recarregar_o_plano)
    elif retorno == "cancelada":
        st.info("Pagamento cancelado. Nada foi cobrado.")


def exigir_recurso(recurso):
    """True se o plano atual pode usar o recurso; senão mostra o convite ao Pro e devolve False."""
    if pode_usar(plano_atual(), recurso):
        return True
    st.info(
        f"**{NOMES_DOS_RECURSOS[recurso]}** faz parte do plano **Pro**. "
        f"Você está no plano {limites_do(plano_atual()).nome}."
    )
    with st.expander("Comparar os planos"):
        mostrar_planos()
        st.caption("Pagamento em modo de teste do Stripe: nenhum dinheiro real.")
    mostrar_assinatura(f"recurso_{recurso}")
    return False


def mostrar_conta(usuario):
    """Botão no topo com os dados da conta e a saída."""
    with st.popover(
        f"{usuario.nome or usuario.email} · {limites_do(usuario.plano).nome}",
        icon=":material/account_circle:",
    ):
        if usuario.foto_url:
            st.image(usuario.foto_url, width=56)
        st.markdown(f"**{usuario.nome or 'Sem nome'}**")
        st.caption(usuario.email)
        st.markdown(
            f"Plano: **{usuario.plano.capitalize()}**\n\n"
            f"Perfil: **{'Administrador' if usuario.e_admin else 'Usuário'}**\n\n"
            f"Conta criada em {usuario.criado_em:%d/%m/%Y}"
        )
        assinatura = st.session_state.get("assinatura")
        if assinatura is not None and assinatura.periodo_fim:
            verbo = "Termina" if assinatura.cancela_no_fim else "Renova"
            st.caption(f"{verbo} em {assinatura.periodo_fim:%d/%m/%Y}.")
        mostrar_assinatura("conta")
        st.page_link(
            PAGINAS_DO_MENU["planos"],
            label="Planos e assinatura",
            icon=":material/workspace_premium:",
        )
        st.page_link(
            PAGINAS_DO_MENU["meus_dados"],
            label="Meus dados e privacidade",
            icon=":material/shield_person:",
        )
        st.button("Sair", on_click=st.logout, width="stretch")


def pagina_planos():
    cabecalho_da_pagina("planos")
    usuario = st.session_state.get("usuario")
    if usuario is None:
        st.info(
            "Sem login (modo local) todos os recursos estão liberados. Com uma conta, "
            "valem os limites de cada plano."
        )
        mostrar_planos()
        return
    limites = limites_do(usuario.plano)
    try:
        with obter_engine().connect() as conexao:
            simulacoes_salvas = contar_simulacoes(conexao, usuario.id)
    except Exception:
        log_da_conta.exception("Falha ao contar as simulações")
        simulacoes_salvas = None
    col_plano, col_simulacoes, col_favoritos = st.columns(3)
    col_plano.metric("Seu plano", limites.nome)
    col_simulacoes.metric(
        "Simulações salvas",
        "—"
        if simulacoes_salvas is None
        else f"{simulacoes_salvas} de {descrever_limite(limites.simulacoes).lower()}",
    )
    col_favoritos.metric(
        "Favoritos",
        f"{len(st.session_state['favoritos'])} de {limites.favoritos}",
    )
    assinatura = st.session_state.get("assinatura")
    if assinatura is not None and assinatura.periodo_fim:
        verbo = "termina" if assinatura.cancela_no_fim else "renova"
        st.caption(f"Sua assinatura {verbo} em {assinatura.periodo_fim:%d/%m/%Y}.")
    st.subheader("O que cada plano inclui")
    mostrar_planos()
    st.caption("Pagamento em modo de teste do Stripe: nenhum dinheiro real é cobrado.")
    mostrar_assinatura("planos")
