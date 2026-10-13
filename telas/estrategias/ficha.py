"""Estratégias: a ficha "Foi sorte?" no backtest (ADR 0037, D1).

A tela só lê, chama `src/ficha.py` e mostra: as perguntas, os vereditos e as explicações vêm de lá.
Regra de `telas/`: nenhum estado mutável no módulo.
"""

import logging

import streamlit as st

from src import ficha
from src.banco.conexao import obter_engine
from src.banco.dados_do_usuario import carregar_preferencias, salvar_preferencias
from src.ficha import Ficha, PedidoDaFicha, Resultado, Situacao
from telas.comum import ajuda_do

log = logging.getLogger("tickerlab.conta")

CHAVE_DA_TOLERANCIA = "ficha_tolerancia"  # em %, como a pessoa digita

# sem verde nem vermelho (a marca reserva os dois para alta e queda): o ícone diz o resultado
ICONE_DO_VEREDITO = {
    Resultado.PASSOU: ":material/verified:",
    Resultado.NAO_PASSOU: ":material/cancel:",
    Resultado.INCONCLUSIVO: ":material/help:",
}
ICONE_DA_CHECAGEM = {
    Situacao.PASSOU: ":material/check_circle:",
    Situacao.NAO_PASSOU: ":material/cancel:",
    Situacao.NAO_SE_APLICA: ":material/remove:",
    Situacao.SEM_MEDIDA: ":material/help:",
}


@st.cache_data(show_spinner="Conferindo se o resultado foi sorte...")
def calcular_ficha(pedido: PedidoDaFicha) -> Ficha:
    return ficha.montar_ficha(pedido)


def _guardar_tolerancia():
    """Com login, a tolerância fica nas preferências da conta (mesclada com o que já estava)."""
    usuario = st.session_state.get("usuario")
    if usuario is None:
        return
    fracao = ficha.normalizar_tolerancia(st.session_state[CHAVE_DA_TOLERANCIA] / 100)
    try:
        with obter_engine().begin() as conexao:
            guardadas = carregar_preferencias(conexao, usuario.id)
            salvar_preferencias(
                conexao,
                usuario.id,
                {**guardadas, ficha.PREFERENCIA_DA_TOLERANCIA: fracao},
            )
    except Exception:
        log.exception("Falha ao salvar a tolerância de queda na conta")
        st.toast(
            "Não consegui guardar a tolerância na sua conta agora; vale só nesta visita."
        )


def escolher_tolerancia() -> float:
    """O campo "Quanto de queda você aguentaria?"; devolve a fração (0,30 = 30%)."""
    st.session_state.setdefault(
        CHAVE_DA_TOLERANCIA, round(ficha.TOLERANCIA_PADRAO_DE_QUEDA * 100)
    )
    em_porcento = st.number_input(
        "Quanto de queda você aguentaria? (%)",
        min_value=round(ficha.TOLERANCIA_MINIMA * 100),
        max_value=round(ficha.TOLERANCIA_MAXIMA * 100),
        step=5,
        key=CHAVE_DA_TOLERANCIA,
        on_change=_guardar_tolerancia,
        help=ajuda_do("Tolerância de queda"),
    )
    return em_porcento / 100


def mostrar_ficha(resultado: Ficha):
    """O veredito em destaque e as cinco checagens, cada uma com a frase que a explica."""
    veredito = resultado.veredito
    with st.container(border=True):
        st.markdown(f"#### {ICONE_DO_VEREDITO[veredito.resultado]} {veredito.titulo}")
        st.markdown(veredito.texto)
        for checagem in resultado.checagens:
            st.markdown(
                f"{ICONE_DA_CHECAGEM[checagem.situacao]} **{checagem.pergunta}** "
                f"({checagem.situacao.value})  \n{checagem.explicacao}"
            )
        st.caption(
            f"Tentativas contadas na checagem do acaso: {resultado.tentativas}. "
            "A ficha usa o custo padrão do app quando o seu é menor."
        )
