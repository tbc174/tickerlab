"""Início: a página inicial, com a busca de um ativo, os atalhos e o tutorial.

Saiu do `app.py` sem mudar comportamento (Master v3, Fase E). Regra de `telas/`: nenhum estado
mutável no módulo (um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import streamlit as st

from src import catalogo, relatorios
from src.planos import limites_do
from telas.comum import PAGINAS_DO_MENU, marcar_feito, plano_atual
from telas.relatorios.estudio import atalho_para_o_relatorio
from telas.tutorial import (
    _reabrir_tutorial,
    mostrar_lista_de_tarefas,
    mostrar_portas_de_entrada,
    mostrar_tutorial,
)


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
        format_func=catalogo.codigo,
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
