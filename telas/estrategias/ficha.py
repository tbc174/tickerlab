"""Estratégias: a ficha "Foi sorte?" no backtest (ADR 0037, D1).

A tela só lê, chama `src/ficha.py` e mostra: as perguntas, os vereditos e as explicações vêm de lá.
Regra de `telas/`: nenhum estado mutável no módulo.
"""

import logging

import streamlit as st

from src import ficha
from src.banco import tentativas
from src.banco.conexao import obter_engine
from src.banco.dados_do_usuario import carregar_preferencias, salvar_preferencias
from src.dados import normalizar_ticker
from src.ficha import Ficha, PedidoDaFicha, Resultado, Situacao
from src.protecoes import Protecoes
from src.tentativas import impressao
from telas.comum import ajuda_do
from telas.conta.guarda import conta_da_sessao_valendo

log = logging.getLogger("tickerlab.conta")

CHAVE_DA_TOLERANCIA = "ficha_tolerancia"  # em %, como a pessoa digita
# sem login: {ticker: impressões} só nesta sessão
CHAVE_DAS_TENTATIVAS_DA_SESSAO = "tentativas_da_sessao"
# o pedido e o veredito da ficha desta execução: o botão "Salvar" do backtest os guarda junto
# (o Pulse recalcula a ficha das estratégias salvas; onda 3, PR E2)
CHAVE_DA_FICHA_PARA_SALVAR = "ficha_para_salvar"

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


def lembrar_para_salvar(pedido: PedidoDaFicha, resultado: Ficha) -> None:
    st.session_state[CHAVE_DA_FICHA_PARA_SALVAR] = {
        "pedido": ficha.pedido_para_guardar(pedido),
        "veredito": resultado.veredito.resultado.value,
    }


def esquecer_a_ficha_para_salvar() -> None:
    """Começo de cada execução da aba: o botão só guarda a ficha que a tela acabou de mostrar."""
    st.session_state.pop(CHAVE_DA_FICHA_PARA_SALVAR, None)


def _guardar_tolerancia():
    """Com login, a tolerância fica nas preferências da conta (mesclada com o que já estava)."""
    usuario = st.session_state.get("usuario")
    if usuario is None or not conta_da_sessao_valendo(usuario):
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


def tolerancia_escolhida() -> float:
    """A tolerância de queda da pessoa (fração), para quem não mostra o campo (o Report Studio)."""
    em_porcento = st.session_state.get(
        CHAVE_DA_TOLERANCIA, ficha.TOLERANCIA_PADRAO_DE_QUEDA * 100
    )
    return ficha.normalizar_tolerancia(em_porcento / 100)


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
        help=ajuda_do(ficha.TERMO_DA_TOLERANCIA),
    )
    return em_porcento / 100


def _contar_na_sessao(ticker: str, marca: str) -> int:
    por_ativo = st.session_state.setdefault(CHAVE_DAS_TENTATIVAS_DA_SESSAO, {})
    vistas = por_ativo.setdefault(ticker, set())
    if len(vistas) < tentativas.TETO_POR_PESSOA:
        vistas.add(marca)
    return len(vistas)


def contar_esta_tentativa(
    estrategia: str, parametros: dict, protecoes: Protecoes | None, custo: float
) -> tuple[str, int]:
    """Registra a configuração que está na tela e devolve o ativo e quantas a pessoa já testou nele.

    Com login, a contagem fica na conta; sem login (ou se o banco falhar), só nesta sessão.
    """
    ticker = normalizar_ticker(st.session_state["ticker"])
    marca = impressao(
        ticker,
        estrategia,
        parametros,
        protecoes,
        custo,
        str(st.session_state["periodo"]),
    )
    usuario = st.session_state.get("usuario")
    if usuario is None:
        return ticker, _contar_na_sessao(ticker, marca)
    try:
        with obter_engine().begin() as conexao:
            tentativas.registrar_tentativa(conexao, usuario.id, ticker, marca)
            return ticker, tentativas.contar_tentativas(conexao, usuario.id, ticker)
    except Exception:
        log.exception("Falha ao registrar a tentativa do backtest na conta")
        return ticker, _contar_na_sessao(ticker, marca)


def mostrar_ficha(resultado: Ficha, texto_das_tentativas: str):
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
        st.markdown(texto_das_tentativas)
        st.caption(ficha.nota_das_tentativas(resultado.tentativas))
