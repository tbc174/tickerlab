"""Dados da conta: favoritos e preferências guardados, e as simulações salvas.

Saiu do `app.py` sem mudar comportamento (Master v3, Fase E). Regra de `telas/`: nenhum estado
mutável no módulo (um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import logging

import pandas as pd
import streamlit as st

from src import ficha, tema_do_app
from src.banco.conexao import obter_engine
from src.banco.dados_do_usuario import (
    DadosInvalidosError,
    apagar_simulacao,
    carregar_preferencias,
    listar_favoritos,
    listar_simulacoes,
    salvar_simulacao,
)
from src.carteiras import ESTRATEGIAS_DE_CARTEIRA
from src.estrategias import ESTRATEGIAS
from src.link import ler_parametros
from src.planos import LimiteDoPlanoError, descrever_limite, limites_do
from src.simulacoes import NOMES_DOS_TIPOS, capturar_estado, restaurar_estado
from telas.comum import cabecalho_da_pagina
from telas.conta.assinatura import mostrar_planos

# o mesmo logger do telas/comum.py (o nome fixo faz o Python devolver o mesmo objeto)
log_da_conta = logging.getLogger("tickerlab.conta")


ESPERAS_DEPOIS_DO_STOP = {
    "Só com um sinal novo da estratégia": None,
    "Esperar 5 dias úteis": 5,
    "Esperar 20 dias úteis": 20,
    "Esperar 60 dias úteis": 60,
}


def carregar_da_conta(usuario):
    """Uma vez por sessão: favoritos e preferências da conta viram o ponto de partida.

    Vem antes de `ler_entradas`, então um link compartilhado (que é lido depois) ainda manda.
    """
    if usuario is None or st.session_state.get("conta_carregada"):
        return
    st.session_state["conta_carregada"] = True
    try:
        with obter_engine().connect() as conexao:
            favoritos = listar_favoritos(conexao, usuario.id)
            preferencias = carregar_preferencias(conexao, usuario.id)
    except Exception:
        log_da_conta.exception("Falha ao carregar os dados da conta")
        st.warning("Não consegui carregar os favoritos e as preferências da sua conta.")
        return
    lidos = ler_parametros(
        {
            "ticker": str(preferencias.get("ticker", "")),
            "periodo": str(preferencias.get("periodo", "")),
            "taxa": str(preferencias.get("taxa", "")),
            "reais": "1" if preferencias.get("em_reais") is True else "",
            "fav": ",".join(favoritos),
        }
    )
    for chave in ("ticker", "periodo", "taxa", "em_reais", "favoritos"):
        if chave in lidos:
            st.session_state[chave] = lidos[chave]
    if "tema" in preferencias:  # a escolha da conta manda sobre a guardada no navegador
        st.session_state["tema_do_app"] = tema_do_app.normalizar(preferencias["tema"])
        st.session_state["tema_escolhido"] = True
    if isinstance(preferencias.get("relatorio"), dict):
        st.session_state["config_salva_do_relatorio"] = preferencias["relatorio"]
    if preferencias.get("tutorial_visto") is True:
        st.session_state["tutorial_visto"] = True
    if ficha.PREFERENCIA_DA_TOLERANCIA in preferencias:
        tolerancia = ficha.normalizar_tolerancia(
            preferencias[ficha.PREFERENCIA_DA_TOLERANCIA]
        )
        st.session_state["ficha_tolerancia"] = round(tolerancia * 100)


def _campo_ainda_vale(chave, valor):
    """A tela de hoje ainda aceita este valor guardado? (evita quebrar um campo ao reabrir)"""
    if chave == "backtest_estrategia":
        return valor in ESTRATEGIAS
    if chave == "carteira_estrategia":
        return valor in ESTRATEGIAS_DE_CARTEIRA
    if chave == "espera_depois_do_stop":
        return valor in ESPERAS_DEPOIS_DO_STOP
    if chave == "backtest_modo_custos":
        return valor in ("Um número só", "Detalhados")
    registros = (
        ("parametro_", ESTRATEGIAS),
        ("carteira_", ESTRATEGIAS_DE_CARTEIRA),
    )
    for prefixo, registro in registros:
        for nome, estrategia in registro.items():
            for p in estrategia.parametros:
                if chave == f"{prefixo}{nome}_{p.nome}":
                    if getattr(p, "opcoes", None):
                        return valor in p.opcoes
                    return (
                        isinstance(valor, int | float)
                        and not isinstance(valor, bool)
                        and p.minimo <= valor <= p.maximo
                    )
    return not chave.startswith("parametro_")  # parâmetro desconhecido: não volta


def _salvar_simulacao(usuario, tipo, nome_sugerido, resumo):
    nome = st.session_state.get(f"salvar_nome_{tipo}", "").strip() or nome_sugerido
    try:
        with obter_engine().begin() as conexao:
            salvar_simulacao(
                conexao,
                usuario.id,
                tipo,
                nome,
                capturar_estado(st.session_state, tipo),
                resumo,
                plano=usuario.plano,
            )
    except (DadosInvalidosError, LimiteDoPlanoError) as erro:
        st.toast(str(erro))
        return
    except Exception:
        log_da_conta.exception("Falha ao salvar a simulação")
        st.toast("Não consegui salvar a simulação agora. Tente de novo em instantes.")
        return
    st.session_state[f"salvar_nome_{tipo}"] = ""
    st.toast(f"Simulação salva: {nome}. Veja em Minhas simulações.")


def oferecer_salvar_simulacao(tipo, nome_sugerido, numeros, dados_ate):
    """Caixa para guardar a simulação da tela na conta do usuário."""
    usuario = st.session_state.get("usuario")
    nome_sugerido = nome_sugerido[:120]
    resumo = {
        "numeros": {str(k): str(v) for k, v in numeros.items()},
        "dados_ate": dados_ate,
    }
    with st.expander("Salvar esta simulação na minha conta"):
        if usuario is None:
            st.caption("Entre com a sua conta do Google para guardar simulações.")
            return
        st.text_input(
            "Nome",
            key=f"salvar_nome_{tipo}",
            placeholder=nome_sugerido,
            max_chars=120,
            help="Se ficar em branco, uso o nome sugerido.",
        )
        st.button(
            "Salvar",
            key=f"salvar_{tipo}",
            on_click=_salvar_simulacao,
            args=(usuario, tipo, nome_sugerido, resumo),
        )
        st.caption(
            "Guardo as escolhas desta aba e um resumo dos números. Ao reabrir, "
            "tudo é recalculado com os dados de hoje."
        )


def _reabrir_simulacao(simulacao):
    campos = restaurar_estado(
        simulacao.parametros, simulacao.tipo, campo_ainda_vale=_campo_ainda_vale
    )
    for chave, valor in campos.items():
        st.session_state[chave] = valor
    st.toast(
        f'Reabri "{simulacao.nome}". Abra a aba {NOMES_DOS_TIPOS[simulacao.tipo]} '
        "para ver."
    )


def _apagar_simulacao(usuario, simulacao):
    try:
        with obter_engine().begin() as conexao:
            apagar_simulacao(conexao, usuario.id, simulacao.id)
    except Exception:
        log_da_conta.exception("Falha ao apagar a simulação")
        st.toast("Não consegui apagar agora. Tente de novo em instantes.")
        return
    st.toast(f"Simulação apagada: {simulacao.nome}.")


def secao_minhas_simulacoes():
    usuario = st.session_state.get("usuario")
    if usuario is None:
        st.info(
            "Entre com a sua conta do Google para guardar e reabrir simulações. "
            "Depois de rodar um Backtest, uma Carteira ou um Par, use "
            '"Salvar esta simulação na minha conta".'
        )
        return
    try:
        with obter_engine().connect() as conexao:
            simulacoes = listar_simulacoes(conexao, usuario.id)
    except Exception:
        log_da_conta.exception("Falha ao listar as simulações")
        st.warning("Não consegui carregar as suas simulações agora.")
        return
    if not simulacoes:
        st.caption(
            f"Plano {limites_do(usuario.plano).nome}: "
            f"{descrever_limite(limites_do(usuario.plano).simulacoes).lower()} simulações."
        )
        st.info(
            "Você ainda não salvou nenhuma simulação. Rode um Backtest, uma Carteira ou "
            'um Par e use "Salvar esta simulação na minha conta".'
        )
        return
    limite = limites_do(usuario.plano).simulacoes
    st.caption(
        f"{len(simulacoes)} de {descrever_limite(limite).lower()} simulações no plano "
        f"{limites_do(usuario.plano).nome}, da mais nova para a mais antiga."
    )
    with st.expander("Ver os planos"):
        mostrar_planos()
    for simulacao in simulacoes:
        titulo = (
            f"{simulacao.nome} · {NOMES_DOS_TIPOS[simulacao.tipo]} · "
            f"{simulacao.criada_em:%d/%m/%Y %H:%M}"
        )
        with st.expander(titulo):
            numeros = simulacao.resultado.get("numeros", {})
            if numeros:
                st.dataframe(pd.DataFrame({"Resultado": numeros}), width="stretch")
            if simulacao.resultado.get("dados_ate"):
                st.caption(
                    f"Números calculados com dados até {simulacao.resultado['dados_ate']}."
                )
            col_reabrir, col_apagar, _ = st.columns([1, 1, 4])
            col_reabrir.button(
                "Reabrir",
                key=f"reabrir_{simulacao.id}",
                on_click=_reabrir_simulacao,
                args=(simulacao,),
            )
            with col_apagar.popover("Apagar"):
                st.write("Apagar esta simulação para sempre?")
                st.button(
                    "Sim, apagar",
                    key=f"apagar_{simulacao.id}",
                    on_click=_apagar_simulacao,
                    args=(usuario, simulacao),
                )


def pagina_simulacoes():
    cabecalho_da_pagina("simulacoes")
    secao_minhas_simulacoes()
