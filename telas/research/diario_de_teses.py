"""Research: Diário de Teses (anotações datadas sobre cada ativo; onda 3, PR F).

A tela só lê e grava pelo `src/banco/teses.py` e usa as regras de `src/diario_de_teses.py`. O texto
é da pessoa: aparece com `st.text` (sem Markdown nem HTML). Guardar e apagar rodam em callbacks,
antes dos campos serem desenhados, para poder limpar o formulário. Regra de `telas/`: nenhum
estado mutável no módulo.
"""

import logging
import uuid

import streamlit as st

from src import diario_de_teses as diario
from src.banco import teses as repo_teses
from src.banco.conexao import obter_engine, tabela_inexistente
from src.banco.dados_do_usuario import listar_simulacoes
from telas.comum import cabecalho_da_pagina
from telas.conta.guarda import so_com_a_conta_valendo
from telas.research.comum import _sem_banco_agora

CHAVE_DO_ATIVO = "diario_ativo"
CHAVE_DO_TEXTO = "diario_texto"
CHAVE_DAS_ESTRATEGIAS = "diario_estrategias"

log = logging.getLogger(__name__)


def _guardar(usuario):
    estado = st.session_state
    try:
        with obter_engine().begin() as conexao:
            repo_teses.escrever(
                conexao,
                usuario.id,
                estado.get(CHAVE_DO_ATIVO, ""),
                estado.get(CHAVE_DO_TEXTO, ""),
                [uuid.UUID(i) for i in estado.get(CHAVE_DAS_ESTRATEGIAS, [])],
            )
    except diario.TeseInvalidaError as erro:
        st.toast(str(erro))
        return
    except Exception:
        log.exception("Falha ao guardar a anotação do Diário de Teses")
        st.toast("Não consegui guardar a anotação agora. Tente de novo em instantes.")
        return
    estado[CHAVE_DO_TEXTO] = ""
    estado[CHAVE_DAS_ESTRATEGIAS] = []
    st.toast("Anotação guardada no seu diário.")


@so_com_a_conta_valendo
def _apagar(usuario, tese_id):
    try:
        with obter_engine().begin() as conexao:
            repo_teses.apagar(conexao, usuario.id, tese_id)
    except Exception:
        log.exception("Falha ao apagar a anotação do Diário de Teses")
        st.toast("Não consegui apagar a anotação agora. Tente de novo em instantes.")


def _ticker_digitado():
    try:
        return diario.ticker_da_tese(st.session_state.get(CHAVE_DO_ATIVO, ""))
    except diario.TeseInvalidaError:
        return None


def _formulario(usuario, backtests):
    st.subheader("Nova anotação")
    if CHAVE_DO_ATIVO not in st.session_state:
        st.session_state[CHAVE_DO_ATIVO] = str(st.session_state.get("ticker", ""))
    st.text_input(
        "Ativo", key=CHAVE_DO_ATIVO, help="O código do ativo, como PETR4 ou AAPL."
    )
    ticker = _ticker_digitado()
    ligaveis = (
        diario.backtests_que_podem_ser_ligados(ticker, backtests) if ticker else []
    )
    nomes = {str(b.id): b.nome for b in ligaveis}
    # o ativo mudou: os backtests escolhidos para o anterior saem da escolha
    st.session_state[CHAVE_DAS_ESTRATEGIAS] = [
        i for i in st.session_state.get(CHAVE_DAS_ESTRATEGIAS, []) if i in nomes
    ]
    st.multiselect(
        "Backtests salvos que sustentam a tese (opcional)",
        options=list(nomes),
        format_func=nomes.__getitem__,
        key=CHAVE_DAS_ESTRATEGIAS,
        max_selections=diario.MAXIMO_DE_ESTRATEGIAS,
        placeholder="Nenhum backtest salvo deste ativo"
        if not nomes
        else "Escolha os backtests",
        help='Quando o veredito da ficha "Foi sorte?" de um deles mudar, o Pulse mostra '
        "esta anotação junto.",
    )
    st.text_area(
        "O que você pensa deste ativo",
        key=CHAVE_DO_TEXTO,
        max_chars=diario.TAMANHO_MAXIMO,
        placeholder="Por que comprou ou acompanha, o que espera e o que faria você mudar de ideia.",
    )
    st.button(
        "Guardar no diário",
        key="diario_guardar",
        type="primary",
        on_click=_guardar,
        args=(usuario,),
    )


def _lista(usuario, anotacoes, backtests):
    nomes = {b.id: b.nome for b in backtests}
    st.subheader("O seu diário")
    if not anotacoes:
        st.info(
            "Nenhuma anotação ainda. Escreva a primeira acima: daqui a alguns meses, você vai "
            "poder comparar o que pensava com o que aconteceu."
        )
        return
    for ticker, do_ativo in diario.agrupar_por_ativo(anotacoes):
        st.markdown(f"#### {ticker.removesuffix('.SA')}")
        for anotacao in do_ativo:
            with st.container(border=True):
                ligados = [nomes[s] for s in anotacao.estrategias if s in nomes]
                legenda = f"Escrita em {diario.texto_da_data(anotacao.criada_em)}"
                if ligados:
                    legenda += " · Backtests ligados: " + ", ".join(ligados)
                st.caption(legenda)
                st.text(anotacao.texto)
                with st.popover("Apagar", icon=":material/delete:"):
                    st.caption("A anotação some de vez do seu diário.")
                    st.button(
                        "Apagar de vez",
                        key=f"diario_apagar_{anotacao.id}",
                        on_click=_apagar,
                        args=(usuario, anotacao.id),
                    )


def pagina_diario_de_teses():
    cabecalho_da_pagina("diario_de_teses")
    usuario = st.session_state.get("usuario")
    if usuario is None:
        st.info(
            "Entre com a sua conta do Google para escrever o seu Diário de Teses: o que você "
            "pensa de cada ativo, com a data, ligado aos backtests que você salvou."
        )
        return
    try:
        with obter_engine().connect() as conexao:
            anotacoes = repo_teses.listar(conexao, usuario.id)
            backtests = listar_simulacoes(conexao, usuario.id, tipo="backtest")
    except Exception as erro:
        if not tabela_inexistente(erro):
            log.exception("Falha ao abrir o Diário de Teses")
        st.error(_sem_banco_agora("o seu Diário de Teses"))
        return
    _formulario(usuario, backtests)
    _lista(usuario, anotacoes, backtests)
    with st.expander("Limites do Diário de Teses"):
        for limite in diario.LIMITES:
            st.markdown(f"- {limite}")
