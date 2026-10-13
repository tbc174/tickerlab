"""Página Relatório da empresa (série 2 da base de ML, PR 7; ADR 0032).

A tela só lê do banco e desenha o `Relatorio` de `src/relatorio_empresa.py`, seção por seção, na
mesma ordem do PDF e da futura API. Por enquanto só as empresas da B3 (os padrões e o FRE são da CVM).
"""

import logging

import pandas as pd
import streamlit as st
from sqlalchemy import exc as sa_exc

from src import eventos_sec
from src.banco.conexao import obter_engine, tabela_inexistente
from src.banco.relatorio_empresa import entradas_do_relatorio
from src.dados import normalizar_ticker
from src.moedas import moeda_do_ticker
from src.relatorio_empresa import Item, Relatorio, Secao, montar
from telas.comum import PAGINAS_DO_MENU, cabecalho_da_pagina, carregar_contexto
from telas.research.comum import _ainda_nao_coletado, _sem_banco_agora

ITENS_POR_LINHA = 3
NOMES_DAS_TABELAS = {
    "sensibilidade": "Valor por ação conforme o desconto e o crescimento",
    "historico": "Ano a ano",
    "contas": "Contas ano a ano",
    "vertical": "Análise vertical (cada conta sobre a receita)",
    "eventos": "Acontecimentos recentes",
    "indicadores": "Antes e agora",
    "pares": "Empresas parecidas",
    "piotroski": "Parcelas do Piotroski",
    "altman": "Parcelas do Altman Z''",
    "beneish": "Parcelas do Beneish",
}
SO_B3 = (
    "O relatório completo por enquanto é só das empresas da B3 (os padrões por setor e os "
    "proventos do FRE vêm da CVM). Escolha um ticker da B3 no topo; para empresas dos EUA, "
    "use a página Fundamentos."
)


def _ler(ticker: str, preco: float | None, fechamentos: pd.Series):
    """As entradas do relatório, ou None quando a página já explicou o motivo."""
    try:
        with obter_engine().connect() as conexao:
            entradas = entradas_do_relatorio(
                conexao, ticker, preco=preco, fechamentos=fechamentos
            )
    except (sa_exc.OperationalError, sa_exc.ProgrammingError) as erro:
        if tabela_inexistente(erro):
            st.info(
                _ainda_nao_coletado(
                    "As demonstrações ainda não foram coletadas neste servidor.",
                    ["python -m scripts.atualizar_fundamentos --anos 6"],
                ),
                icon=":material/schedule:",
            )
            return None
        logging.getLogger(__name__).exception("Falha ao ler o relatório da empresa")
        st.error(_sem_banco_agora("os dados da empresa"))
        return None
    if entradas is None or entradas.cnpj.startswith(eventos_sec.PREFIXO_DO_CIK):
        st.info(SO_B3, icon=":material/info:")
        return None
    if entradas.dados.contas.empty:
        st.info(
            f"Ainda não há demonstrações coletadas da {entradas.empresa}. A coleta roda uma vez "
            "por dia.",
            icon=":material/schedule:",
        )
        return None
    return entradas


def _mostrar_item(coluna, item: Item) -> None:
    coluna.metric(
        item.nome, item.texto, help=f"Base: {item.base}" if item.base else None
    )
    if item.motivo:
        coluna.caption(item.motivo)
    if item.nota:
        coluna.caption(
            f"Nota: **{item.nota}**"
            + (f" · {item.nota_texto}" if item.nota_texto else "")
        )


def _mostrar_secao(secao: Secao) -> None:
    st.subheader(secao.titulo)
    for inicio in range(0, len(secao.itens), ITENS_POR_LINHA):
        linha = secao.itens[inicio : inicio + ITENS_POR_LINHA]
        for coluna, item in zip(st.columns(ITENS_POR_LINHA), linha, strict=False):
            _mostrar_item(coluna, item)
    for paragrafo in secao.paragrafos:
        st.markdown(paragrafo)
    for chave, linhas in secao.tabelas.items():
        if linhas:
            with st.expander(
                NOMES_DAS_TABELAS.get(chave, chave.replace("_", " ").capitalize())
            ):
                st.dataframe(pd.DataFrame(linhas), hide_index=True, width="stretch")


def _mostrar(relatorio: Relatorio) -> None:
    st.markdown(
        f"**{relatorio.empresa}** · {relatorio.setor or 'setor não informado'} · "
        f"CNPJ {relatorio.cnpj}"
    )
    if relatorio.em_conferencia:
        st.warning(
            "Há números desta empresa em conferência pelas regras de qualidade: veja a seção "
            "Qualidade dos dados.",
            icon=":material/fact_check:",
        )
    for secao in relatorio.secoes:
        _mostrar_secao(secao)
    st.caption("Fontes: " + "; ".join(relatorio.fontes) + ". Nada aqui é recomendação.")


def pagina_relatorio_empresa():
    cabecalho_da_pagina("relatorio_empresa")
    c = carregar_contexto()
    ticker = normalizar_ticker(c.ticker)
    preco = float(c.fechamento.iloc[-1]) if moeda_do_ticker(ticker) == "BRL" else None
    entradas = _ler(ticker, preco, c.fechamento if preco is not None else None)
    if entradas is None:
        return
    _mostrar(montar(entradas))
    st.page_link(
        PAGINAS_DO_MENU["fundamentos"],
        label="Ver os fundamentos com os seus parâmetros",
        icon=":material/account_balance:",
    )
