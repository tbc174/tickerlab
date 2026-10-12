"""Research: Pessoas de dentro (R2): negociações de diretores e conselheiros (VLMO e Form 4).

Saiu do `app.py` sem mudar comportamento. Regra de `telas/`: nenhum estado mutável no módulo
(um módulo importado é do processo inteiro, isto é, de todos os usuários).
"""

import logging
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
from sqlalchemy import exc as sa_exc

from src import graficos, negociacoes, relatorios
from src.banco import negociacoes as repo_negociacoes
from src.banco.conexao import obter_engine, tabela_inexistente
from src.banco.eventos import empresas_dos_tickers, tickers_das_empresas
from src.dados import normalizar_ticker
from telas.comum import cabecalho_da_pagina, carregar_contexto, mostrar_grafico
from telas.research.busca_na_sec import (
    mostrar_resultado_da_busca_na_sec,
    oferecer_busca_na_sec,
)
from telas.research.comum import _ainda_nao_coletado, _sem_banco_agora

JANELAS_DE_NEGOCIACOES = {90: "3 meses", 180: "6 meses", 365: "12 meses"}


BOLSAS_DAS_NEGOCIACOES = {
    negociacoes.FONTE_VLMO: "B3 (CVM)",
    negociacoes.FONTE_FORM4: "EUA (SEC)",
}


CARGOS_DE_QUEM_DECIDE = ("diretoria", "conselho")  # o padrão da pesquisa acadêmica


TAMANHO_DO_RANKING = 10


def _ler_negociacoes(desde, cnpjs=None):
    """(negociações, None) ou (None, mensagem) quando a base ainda não existe ou falhou."""
    try:
        with obter_engine().connect() as conexao:
            return repo_negociacoes.negociacoes(conexao, desde, cnpjs), None
    except Exception as erro:
        if not tabela_inexistente(erro):
            logging.getLogger(__name__).exception("Falha ao ler as negociações")
            return None, _sem_banco_agora("as negociações")
        return None, _ainda_nao_coletado(
            "As negociações ainda não foram coletadas neste servidor.",
            [
                "python -m scripts.atualizar_negociacoes_cvm",
                "python -m scripts.atualizar_eventos_sec",
            ],
        )


def _tabela_de_negociacoes(tabela):
    moeda = tabela["moeda"].iloc[0]
    return pd.DataFrame(
        {
            "Entregue em": [f"{d:%d/%m/%Y}" for d in tabela["entregue_em"]],
            "Negociação": [
                f"{d:%d/%m/%Y}" if pd.notna(d) else f"mês de {r:%m/%Y}"
                for d, r in zip(tabela["data"], tabela["referencia"], strict=True)
            ],
            "Cargo": [
                negociacoes.CARGOS[c] + (f" ({d})" if d else "")
                for c, d in zip(tabela["cargo"], tabela["cargo_descricao"], strict=True)
            ],
            "Operação": tabela["operacao"].str.capitalize(),
            "Ações": [f"{q:,.0f}".replace(",", ".") for q in tabela["quantidade"]],
            "Valor": [negociacoes.formatar_valor(v, moeda) for v in tabela["valor"]],
            "Plano 10b5-1": [
                "sim" if p is True else ("não" if p is False else "—")
                for p in tabela["plano_10b5_1"]
            ],
            "Abrir": tabela["link"],
        }
    )


def _negociacoes_do_ativo(ticker, janela):
    try:
        with obter_engine().connect() as conexao:
            empresa = empresas_dos_tickers(conexao, [ticker]).get(ticker)
    except (sa_exc.OperationalError, sa_exc.ProgrammingError):
        empresa = None
    if empresa is None:
        oferecer_busca_na_sec(ticker, "As negociações")
        return
    desde = datetime.now(relatorios.FUSO).date() - timedelta(days=janela)
    tabela, erro = _ler_negociacoes(desde, [empresa[0]])
    if erro:
        st.info(erro, icon=":material/schedule:")
        return
    st.markdown(f"**{empresa[1]}** · últimos {JANELAS_DE_NEGOCIACOES[janela]}")
    if tabela.empty:
        st.info(
            "Nenhuma compra ou venda de pessoas de dentro informada nesse período. Na B3 o "
            "formulário é mensal e sai até o dia 10 do mês seguinte.",
            icon=":material/info:",
        )
        return
    moeda = tabela["moeda"].iloc[0]
    saldo = negociacoes.saldo_por_empresa(tabela)
    with st.container(horizontal=True):
        if not saldo.empty:
            linha = saldo.iloc[0]
            st.metric(
                "Compras",
                negociacoes.formatar_valor(linha["compras"], moeda),
                border=True,
            )
            st.metric(
                "Vendas",
                negociacoes.formatar_valor(linha["vendas"], moeda),
                border=True,
            )
            st.metric(
                "Saldo (compras − vendas)",
                negociacoes.formatar_valor(linha["saldo"], moeda),
                border=True,
                help="Sem a tesouraria da própria empresa. Valores não informados contam zero.",
            )
        st.metric("Documentos", tabela["documento"].nunique(), border=True)
    mostrar_grafico(
        graficos.criar_grafico_negociacoes(negociacoes.resumo_por_mes(tabela), moeda)
    )
    st.dataframe(
        _tabela_de_negociacoes(tabela),
        hide_index=True,
        width="stretch",
        column_config={
            "Abrir": st.column_config.LinkColumn("Abrir", display_text="documento")
        },
    )


def _ranking_formatado(saldo, tickers):
    return pd.DataFrame(
        {
            "Ativo": [tickers.get(c, "—").removesuffix(".SA") for c in saldo["cnpj"]],
            "Empresa": saldo["empresa"],
            "Compras": [
                negociacoes.formatar_valor(v, m)
                for v, m in zip(saldo["compras"], saldo["moeda"], strict=True)
            ],
            "Vendas": [
                negociacoes.formatar_valor(v, m)
                for v, m in zip(saldo["vendas"], saldo["moeda"], strict=True)
            ],
            "Saldo": [
                negociacoes.formatar_valor(v, m)
                for v, m in zip(saldo["saldo"], saldo["moeda"], strict=True)
            ],
            "Documentos": saldo["documentos"],
        }
    )


def _ranking_do_mercado(janela):
    col_bolsa, col_cargos = st.columns([1, 2])
    fonte = col_bolsa.segmented_control(
        "Bolsa",
        list(BOLSAS_DAS_NEGOCIACOES),
        format_func=BOLSAS_DAS_NEGOCIACOES.get,
        default=negociacoes.FONTE_VLMO,
        required=True,
        key="dentro_bolsa",
    )
    cargos = col_cargos.multiselect(
        "Cargos",
        [c for c in negociacoes.CARGOS if c != "companhia"],
        default=list(CARGOS_DE_QUEM_DECIDE),
        format_func=negociacoes.CARGOS.get,
        key="dentro_cargos",
        help="Diretoria e conselho são o padrão dos estudos. Controladores costumam aparecer "
        "em ofertas de ações e reorganizações, que não são decisões do dia a dia.",
    )
    desde = datetime.now(relatorios.FUSO).date() - timedelta(days=janela)
    tabela, erro = _ler_negociacoes(desde)
    if erro:
        st.info(erro, icon=":material/schedule:")
        return
    tabela = tabela[(tabela["fonte"] == fonte) & tabela["cargo"].isin(cargos)]
    saldo = negociacoes.saldo_por_empresa(tabela)
    if saldo.empty:
        st.info("Nenhuma negociação desses cargos no período.", icon=":material/info:")
        return
    with obter_engine().connect() as conexao:
        tickers = tickers_das_empresas(conexao, saldo["cnpj"])
    compradores = saldo[saldo["saldo"] > 0].head(TAMANHO_DO_RANKING)
    vendedores = saldo[saldo["saldo"] < 0].sort_values("saldo").head(TAMANHO_DO_RANKING)
    st.markdown("##### Mais compras do que vendas")
    if compradores.empty:
        st.caption("Nenhuma empresa com saldo comprador no período.")
    else:
        st.dataframe(
            _ranking_formatado(compradores, tickers), hide_index=True, width="stretch"
        )
    st.markdown("##### Mais vendas do que compras")
    if vendedores.empty:
        st.caption("Nenhuma empresa com saldo vendedor no período.")
    else:
        st.dataframe(
            _ranking_formatado(vendedores, tickers), hide_index=True, width="stretch"
        )
    st.caption(
        "Saldo em dinheiro, só com os cargos escolhidos; valores não informados contam zero. "
        "É uma lista de fatos, não de recomendações."
    )


def pagina_por_dentro():
    cabecalho_da_pagina("por_dentro")
    mostrar_resultado_da_busca_na_sec()
    c = carregar_contexto()
    janela = st.segmented_control(
        "Período",
        list(JANELAS_DE_NEGOCIACOES),
        format_func=JANELAS_DE_NEGOCIACOES.get,
        default=180,
        required=True,
        key="dentro_janela",
    )
    aba_ativo, aba_mercado = st.tabs(["Do ativo do topo", "No mercado"])
    with aba_ativo:
        _negociacoes_do_ativo(normalizar_ticker(c.ticker), janela)
    with aba_mercado:
        _ranking_do_mercado(janela)
    with st.expander("Como ler estes dados"):
        st.markdown(
            "- **Quem são:** controladores, diretores e conselheiros (nos EUA, também quem tem "
            "10% ou mais). A lei obriga essas pessoas a informar quando negociam ações da própria "
            "empresa.\n"
            "- **Quando ficam públicos:** na B3, o formulário da CVM é **mensal** (somado por "
            "cargo) e sai até o dia 10 do mês seguinte; nos EUA, o Form 4 sai em até **2 dias "
            "úteis**, um por pessoa.\n"
            "- **O que a pesquisa diz:** nos EUA, as **compras** de pessoas de dentro costumam "
            "carregar informação (Lakonishok e Lee, 2001; Cohen, Malloy e Pomorski, 2012); as "
            "**vendas** dizem pouco, porque se vende para diversificar ou pagar impostos. No "
            "Brasil o tema foi pouco estudado.\n"
            "- **Plano 10b5-1:** venda programada com meses de antecedência; informa ainda menos.\n"
            "- **O que fica de fora:** opções, ações recebidas como pagamento, doações e "
            "empréstimos, que não são decisões de compra ou venda.\n"
            "- **Privacidade:** mostramos o cargo, nunca o nome da pessoa.\n\n"
            "Fontes: CVM (formulário de valores mobiliários negociados, art. 11 da Resolução CVM "
            "44) e SEC (Form 4). Nada aqui é recomendação de investimento."
        )
