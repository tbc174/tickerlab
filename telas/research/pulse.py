"""Research: Pulse (o que mudou nos seus ativos desde a última visita; onda 3, PR E).

A tela só lê do banco, chama `src/pulse.py` e mostra. A janela fica na sessão: um rerun do
Streamlit não a zera no meio da leitura. A visita só é marcada depois que os acontecimentos foram
lidos sem erro; senão a pessoa perderia o que ainda não viu. Regra de `telas/`: nenhum estado
mutável no módulo.
"""

import logging

import pandas as pd
import streamlit as st

from src import pulse, research
from src.banco import pulse as repo_pulse
from src.banco.conexao import obter_engine, tabela_inexistente
from src.banco.dados_do_usuario import (
    listar_favoritos,
    listar_simulacoes,
    listar_watchlists,
)
from src.banco.eventos import eventos_dos_tickers
from src.dados import DadosIndisponiveisError
from telas.comum import (
    cabecalho_da_pagina,
    carregar_dados_na_moeda,
    parametros_em_vigor,
)
from telas.research.acontecimentos import _mostrar_item, _resumos_dos_itens
from telas.research.comum import _carteira_do_research, _sem_banco_agora

CHAVE_DA_JANELA = "pulse_janela"  # (id da pessoa, Janela): a janela desta sessão
CHAVE_DA_MARCA = (
    "pulse_marcado"  # (id da pessoa, hora marcada): a visita já foi gravada
)

log = logging.getLogger(__name__)


def _janela_da_sessao(usuario):
    guardada = st.session_state.get(CHAVE_DA_JANELA)
    if guardada is not None and guardada[0] == usuario.id:
        return guardada[1]
    with obter_engine().connect() as conexao:
        visita = repo_pulse.ultima_visita(conexao, usuario.id)
    janela = pulse.janela(visita, pulse.agora())
    st.session_state[CHAVE_DA_JANELA] = (usuario.id, janela)
    return janela


def _atualizar():
    """Começa uma janela nova a partir da visita que acabou de ser marcada."""
    st.session_state.pop(CHAVE_DA_JANELA, None)


def _marcar_visita(usuario, janela):
    marca = (usuario.id, janela.ate)
    if st.session_state.get(CHAVE_DA_MARCA) == marca:
        return
    with obter_engine().begin() as conexao:
        repo_pulse.marcar_visita(conexao, usuario.id, janela.ate)
    st.session_state[CHAVE_DA_MARCA] = marca


def _ativos(usuario):
    with obter_engine().connect() as conexao:
        favoritos = listar_favoritos(conexao, usuario.id)
        listas = [(w.nome, w.tickers) for w in listar_watchlists(conexao, usuario.id)]
        estrategias = [
            s.parametros.get("ticker") for s in listar_simulacoes(conexao, usuario.id)
        ]
    carteira = _carteira_do_research(usuario)
    return pulse.ativos_da_pessoa(
        favoritos, list(carteira.pesos) if carteira else [], listas, estrategias
    )


def _eventos_novos(ativos, janela):
    """Os eventos coletados na janela; None se a leitura falhou (a visita não é marcada)."""
    try:
        with obter_engine().connect() as conexao:
            return eventos_dos_tickers(
                conexao,
                [a.ticker for a in ativos],
                janela.publicados_desde,
                coletados_entre=(janela.desde, janela.ate),
            )
    except Exception as erro:
        if tabela_inexistente(erro):
            return []  # banco sem o Research (modo local sem migrar): nada coletado
        log.exception("Falha ao ler os acontecimentos do Pulse")
        st.warning(_sem_banco_agora("os acontecimentos"))
        return None


def _mostrar_acontecimentos(ativos, janela, eventos):
    st.subheader("Acontecimentos novos")
    r = parametros_em_vigor(None)
    itens = pulse.acontecimentos(
        eventos,
        ativos,
        janela,
        research.pesos_da_resolucao(r.valores("relevancia")),
        list(r["newsletter.temas"]),
    )
    if not itens:
        st.info("Nenhum acontecimento novo nas empresas dos seus ativos.")
        return
    resumos = _resumos_dos_itens(itens)
    for i, item in enumerate(itens):
        _mostrar_item(item, f"pulse{i}", resumo=resumos.get(item.evento.protocolo))


def _mostrar_variacoes(ativos, janela):
    st.subheader("Variação do preço")
    periodo = pulse.periodo_de_precos(janela)
    variacoes, sem_mudanca = [], []
    for ativo in ativos:
        try:
            fechamentos = carregar_dados_na_moeda(ativo.ticker, periodo)["Close"]
        except (DadosIndisponiveisError, ValueError, KeyError):
            sem_mudanca.append(ativo.ticker)
            continue
        v = pulse.variacao(ativo.ticker, fechamentos, janela.desde)
        if v is None:
            sem_mudanca.append(ativo.ticker)
        else:
            variacoes.append(v)
    origens = {a.ticker: a.origens for a in ativos}
    if variacoes:
        ordenadas = pulse.ordenar_variacoes(variacoes)
        st.dataframe(
            pd.DataFrame(
                {
                    "Ativo": [v.ticker.removesuffix(".SA") for v in ordenadas],
                    "Variação (%)": [round(v.retorno * 100, 2) for v in ordenadas],
                    "De": [f"{v.de:%d/%m/%Y}" for v in ordenadas],
                    "Até": [f"{v.ate:%d/%m/%Y}" for v in ordenadas],
                    "Por que está aqui": [
                        ", ".join(origens.get(v.ticker, ())) for v in ordenadas
                    ],
                }
            ),
            column_config={
                "Variação (%)": st.column_config.NumberColumn(format="%+.1f%%")
            },
            hide_index=True,
        )
        st.caption(
            "Do último fechamento que já existia na hora da sua visita até o último fechamento "
            "de hoje, na moeda do ativo e sem os proventos."
        )
    if sem_mudanca:
        st.caption(
            "Sem pregão novo ou sem preço desde a visita: "
            + ", ".join(t.removesuffix(".SA") for t in sem_mudanca)
            + "."
        )


def pagina_pulse():
    cabecalho_da_pagina("pulse")
    usuario = st.session_state.get("usuario")
    if usuario is None:
        st.info(
            "Entre com a sua conta do Google para o Pulse lembrar da sua última visita e "
            "mostrar o que mudou nos seus ativos."
        )
        return
    try:
        janela = _janela_da_sessao(usuario)
        ativos, fora = _ativos(usuario)
    except Exception as erro:
        if not tabela_inexistente(erro):
            log.exception("Falha ao abrir o Pulse")
        st.error(_sem_banco_agora("o seu Pulse"))
        return
    st.caption(pulse.texto_da_janela(janela))
    if not ativos:
        st.info(
            "Ainda não há nenhum ativo guardado. O Pulse acompanha os seus favoritos, as "
            "listas do Research, a carteira guardada (Pro) e os ativos das estratégias salvas."
        )
        _marcar_visita(usuario, janela)
        return
    if fora:
        st.caption(
            f"O Pulse acompanha até {pulse.MAXIMO_DE_ATIVOS} ativos; {fora} ficaram de fora "
            "(valem os favoritos, depois a carteira, as listas e as estratégias)."
        )
    eventos = _eventos_novos(ativos, janela)
    if eventos is not None:
        _mostrar_acontecimentos(ativos, janela, eventos)
    _mostrar_variacoes(ativos, janela)
    with st.expander("Limites do Pulse"):
        for limite in pulse.LIMITES:
            st.markdown(f"- {limite}")
    if eventos is not None:
        _marcar_visita(usuario, janela)
        st.button(
            "Marcar como visto e atualizar",
            on_click=_atualizar,
            help="A próxima janela começa agora: só aparece o que chegar depois.",
        )
