"""Compartilhar por link (onda 4 da ADR 0046): o botão, o link criado e a lista em Meus dados.

A tela só lê e mostra: regras e textos em `src/compartilhamentos.py`, banco em
`src/banco/compartilhamentos.py`. Regra de `telas/`: nenhum estado mutável no módulo.
"""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import sqlalchemy as sa
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from src import compartilhamentos as comp
from src.banco import compartilhamentos as links
from src.banco.conexao import obter_engine
from src.banco.usuarios import Usuario
from src.ficha import Ficha, PedidoDaFicha
from src.planos import LimiteDoPlanoError
from telas.conta.guarda import so_com_a_conta_valendo

log = logging.getLogger("tickerlab.conta")

# {alvo: (endereço do link criado nesta sessão, de quê)} e {alvo: (mensagem de erro, de quê)};
# "de quê" é a impressão do que estava na tela (a ficha) ou None (o PDF, que não muda)
CHAVE_DOS_LINKS_CRIADOS = "links_compartilhados_criados"
CHAVE_DOS_ERROS = "links_compartilhados_erros"

CriarLink = Callable[[sa.Connection, int], str]  # (conexão, dias) → código


@so_com_a_conta_valendo
def _criar(alvo: str, criar: CriarLink, de: str | None) -> None:
    """Botão "Criar o link": guarda o endereço só na sessão (o banco fica com o hash)."""
    erros = st.session_state.setdefault(CHAVE_DOS_ERROS, {})
    erros.pop(alvo, None)
    dias = st.session_state.get(f"{alvo}_prazo", comp.PRAZO_PADRAO)
    try:
        with obter_engine().begin() as conexao:
            codigo = criar(conexao, dias)
    except (LimiteDoPlanoError, ValueError) as erro:
        erros[alvo] = (str(erro), de)
        return
    except Exception:
        log.exception("Falha ao criar um link compartilhado")
        erros[alvo] = (
            "Não consegui criar o link agora. Tente de novo em instantes.",
            de,
        )
        return
    st.session_state.setdefault(CHAVE_DOS_LINKS_CRIADOS, {})[alvo] = (
        comp.endereco_do_link(codigo),
        de,
    )


def botao_de_compartilhar(
    alvo: str,
    tipo: str,
    criar: CriarLink,
    onde: DeltaGenerator | None = None,
    de: str | None = None,
) -> None:
    """O "Compartilhar": prazo, o que fica visível e o botão. `alvo` é a chave dos widgets."""
    onde = onde if onde is not None else st.container()
    with onde.popover("Compartilhar", icon=":material/share:"):
        st.caption(comp.O_QUE_FICA_VISIVEL[tipo])
        st.selectbox(
            "Vale por",
            comp.PRAZOS_EM_DIAS,
            index=comp.PRAZOS_EM_DIAS.index(comp.PRAZO_PADRAO),
            format_func=comp.rotulo_do_prazo,
            key=f"{alvo}_prazo",
        )
        st.button(
            "Criar o link",
            type="primary",
            key=f"{alvo}_criar",
            on_click=_criar,
            args=(alvo, criar, de),
        )


def _desta_tela(guardados: dict, alvo: str, de: str | None) -> str | None:
    """O que foi guardado para `alvo`, só se veio do que está na tela agora."""
    texto, origem = guardados.get(alvo, (None, None))
    return texto if origem == de else None


def mostrar_link_criado(
    alvo: str, onde: DeltaGenerator | None = None, de: str | None = None
) -> None:
    """O link desta sessão (uma vez só: depois, só a impressão fica no banco) ou o erro.

    `de` é a impressão do que está na tela: o link (ou o erro) de outra ficha não aparece.
    """
    onde = onde if onde is not None else st.container()
    erro = _desta_tela(st.session_state.get(CHAVE_DOS_ERROS, {}), alvo, de)
    if erro:
        onde.error(erro)
    endereco = _desta_tela(st.session_state.get(CHAVE_DOS_LINKS_CRIADOS, {}), alvo, de)
    if endereco:
        onde.success(
            "Link criado. Ele abre sem login, até o prazo ou até você revogar."
        )
        onde.code(endereco, language=None)
        onde.caption(comp.AVISO_DO_LINK_CRIADO)


def compartilhar_ficha(
    resultado: Ficha, pedido: PedidoDaFicha, ticker: str, texto_das_tentativas: str
) -> None:
    """Embaixo da ficha do backtest, só com login: congela o que a tela acabou de mostrar."""
    usuario = st.session_state.get("usuario")
    if usuario is None:
        return
    fonte = comp.fonte_dos_precos(pedido.dados.attrs.get("origem"))

    def congelar() -> dict:
        return comp.congelar_ficha(
            resultado, pedido, ticker, texto_das_tentativas, fonte, datetime.now(UTC)
        )

    def criar(conexao: sa.Connection, dias: int) -> str:
        return links.criar_link_da_ficha(
            conexao, usuario.id, usuario.plano, congelar(), dias
        )

    desta_ficha = comp.impressao_da_ficha(congelar())
    botao_de_compartilhar("compartilhar_ficha", "ficha", criar, de=desta_ficha)
    mostrar_link_criado("compartilhar_ficha", de=desta_ficha)


def compartilhar_pdf(
    usuario: Usuario,
    relatorio_id: uuid.UUID,
    coluna: DeltaGenerator,
    abaixo: DeltaGenerator,
) -> None:
    """O "Compartilhar" de um PDF guardado na biblioteca."""
    alvo = f"compartilhar_pdf_{relatorio_id}"

    def criar(conexao: sa.Connection, dias: int) -> str:
        return links.criar_link_do_pdf(
            conexao, usuario.id, usuario.plano, relatorio_id, dias
        )

    botao_de_compartilhar(alvo, "pdf", criar, onde=coluna)
    mostrar_link_criado(alvo, onde=abaixo)


@so_com_a_conta_valendo
def _revogar(usuario_id: uuid.UUID, link_id: uuid.UUID) -> None:
    try:
        with obter_engine().begin() as conexao:
            links.revogar_link(conexao, usuario_id, link_id)
    except Exception:
        log.exception("Falha ao revogar um link compartilhado")
        st.toast("Não consegui revogar o link agora. Tente de novo em instantes.")


def mostrar_links_da_conta(usuario: Usuario) -> None:
    """Meus dados › Links compartilhados: o que está valendo, quantas visitas, e revogar."""
    st.subheader("Links compartilhados")
    try:
        with obter_engine().connect() as conexao:
            lista = links.listar_links(conexao, usuario.id)
    except Exception:
        log.exception("Falha ao ler os links compartilhados")
        st.error("Não consegui ler os seus links agora. Tente de novo em instantes.")
        return
    if not lista:
        st.caption(comp.SEM_LINKS)
        return
    st.caption(comp.EXPLICACAO_DOS_LINKS)
    for link in lista:
        with st.container(border=True):
            col_texto, col_acao = st.columns([5, 1.4], vertical_alignment="center")
            col_texto.markdown(f"**{link.titulo}**")
            col_texto.caption(
                comp.descrever_link(
                    link.tipo,
                    link.situacao,
                    link.criado_em,
                    link.expira_em,
                    link.visitas,
                )
            )
            if link.situacao == "ativo":
                col_acao.button(
                    "Revogar",
                    icon=":material/link_off:",
                    key=f"revogar_link_{link.id}",
                    on_click=_revogar,
                    args=(usuario.id, link.id),
                    width="stretch",
                )
