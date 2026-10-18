"""Research: Preços de referência (café, algodão e fertilizantes), com a fonte e o aviso de cada número.

A tela só lê, chama `src/commodities/painel_de_precos.py` e mostra. Regra de `telas/`: nenhum
estado mutável no módulo.
"""

import logging
from datetime import date

import pandas as pd
import streamlit as st

from src import graficos, relatorios
from src.banco.conexao import obter_engine, tabela_inexistente
from src.commodities import painel_de_precos as painel
from telas.comum import cabecalho_da_pagina, mostrar_grafico

log = logging.getLogger(__name__)


def _ler_painel(hoje: date) -> painel.PainelDePrecos | None:
    """O painel de hoje, ou None se o acervo ainda não tem as séries (ou o banco não respondeu)."""
    try:
        with obter_engine().connect() as conexao:
            lido = painel.montar_painel(conexao, hoje)
    except Exception as erro:
        if not tabela_inexistente(erro):
            log.exception("Falha ao ler os preços de referência")
            st.error(
                "Não consegui ler os preços de referência agora. Tente de novo em instantes."
            )
            return None
        lido = painel.PainelDePrecos(itens=(), spread=())
    if not lido.itens:
        st.info(
            "Os preços de referência ainda não foram coletados neste servidor "
            "(`python -m scripts.atualizar_series_macro`)."
        )
        return None
    return lido


def _formatar(valor: float) -> str:
    return f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _mostrar_item(item: painel.PrecoDeReferencia) -> None:
    variacao = item.variacao_12_meses
    st.metric(
        f"{item.nome} ({item.unidade})",
        _formatar(item.ultimo_valor),
        delta=None
        if variacao is None
        else f"{variacao:+.1f}% em 12 meses".replace(".", ","),
    )
    st.caption(f"Média de {item.ultimo_mes:%m/%Y}, Pink Sheet do Banco Mundial.")
    mostrar_grafico(graficos.criar_grafico_preco_de_referencia(item))
    if item.nota_das_fontes:
        st.caption(item.nota_das_fontes)


def _mostrar_spread(spread: tuple[painel.PontoDoSpread, ...]) -> None:
    if not spread:
        return
    st.markdown("**Spread arábica menos robusta**")
    st.caption(
        "Quando a diferença abre muito, a indústria troca de grão; o conilon do Brasil é robusta."
    )
    mostrar_grafico(graficos.criar_grafico_spread_do_cafe(spread))


def pagina_precos_de_referencia() -> None:
    cabecalho_da_pagina("precos_de_referencia")
    hoje = pd.Timestamp.now(tz=relatorios.FUSO).date()
    lido = _ler_painel(hoje)
    if lido is None:
        return
    st.warning(lido.aviso_diario)
    for item in lido.itens:
        _mostrar_item(item)
        if item.chave == painel.ROBUSTA:
            _mostrar_spread(lido.spread)
    st.caption(lido.atribuicao)
