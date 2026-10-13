"""Carteira da B3: a posição da Área do Investidor lida só na memória, para todos os planos.

Concentração, a carteira no passado, Raio-X e Rebalanceamento. A tela só lê, chama
`src/analise_da_carteira.py` e mostra; nada da planilha é guardado (nem em banco, nem em log).
Regra de `telas/`: nenhum estado mutável no módulo.
"""

import logging

import pandas as pd
import streamlit as st

from src import analise_da_carteira as ac
from src import graficos, relatorios
from src.banco.conexao import obter_engine, tabela_inexistente
from src.banco.demonstracoes import setores_dos_tickers
from src.carteira_b3 import ArquivoDaB3Error, CarteiraB3, ler_carteira
from src.dados import DadosIndisponiveisError
from telas.comum import (
    PERIODOS_DO_TOPO,
    cabecalho_da_pagina,
    carregar_dados,
    formatar_pct,
    mostrar_grafico,
)
from telas.relatorios.estudio import ARQUIVO_DA_CARTEIRA_DE_EXEMPLO

log = logging.getLogger(__name__)
IBOVESPA = "^BVSP"
PERIODO_PADRAO = "2y"


def _pedir_carteira() -> CarteiraB3 | None:
    st.markdown(ac.COMO_BAIXAR_A_PLANILHA)
    if st.toggle("Usar a carteira de exemplo (fictícia)", key="carteira_b3_exemplo"):
        st.warning(ac.AVISO_DO_EXEMPLO, icon=":material/science:")
        conteudo, nome = (
            ARQUIVO_DA_CARTEIRA_DE_EXEMPLO.read_bytes(),
            ARQUIVO_DA_CARTEIRA_DE_EXEMPLO.name,
        )
    else:
        arquivo = st.file_uploader(
            "Planilha de posição da B3", type=["xlsx", "csv"], key="carteira_b3_arquivo"
        )
        if arquivo is None:
            return None
        conteudo, nome = arquivo.getvalue(), arquivo.name
    try:
        carteira = ler_carteira(conteudo, nome)
    except ArquivoDaB3Error as erro:
        st.error(str(erro))
        return None
    for aviso in carteira.avisos:
        st.warning(aviso)
    return carteira


def _mostrar_concentracao(carteira):
    conc = ac.concentracao(carteira)
    st.subheader("Concentração")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Maior posição",
        f"{conc.maior[0]}: {formatar_pct(conc.maior[1])}" if conc.maior else "—",
    )
    c2.metric(
        "3 maiores juntas",
        formatar_pct(conc.tres_maiores) if conc.tres_maiores is not None else "—",
    )
    c3.metric(
        "Número efetivo de ativos", f"{conc.numero_efetivo:.1f}".replace(".", ",")
    )
    c4.metric(
        "Tesouro e renda fixa",
        formatar_pct(conc.fracao_renda_fixa)
        if conc.fracao_renda_fixa is not None
        else "—",
    )


def _tabela_de_fatias(titulo, fatias):
    st.markdown(f"**{titulo}**")
    st.dataframe(
        pd.DataFrame(
            {"Grupo": [f.grupo for f in fatias], "Peso": [f.peso * 100 for f in fatias]}
        ),
        column_config={
            "Peso": st.column_config.ProgressColumn(
                format="%.1f%%", min_value=0, max_value=100
            )
        },
        hide_index=True,
        width="stretch",
    )


def _setores(carteira):
    try:
        with obter_engine().connect() as conexao:
            return setores_dos_tickers(conexao, list(carteira.posicoes["ticker"]))
    except Exception as erro:
        if not tabela_inexistente(erro):
            log.exception("Falha ao ler os setores da CVM")
        return {}


def _mostrar_raio_x(carteira):
    raio = ac.raio_x(carteira, _setores(carteira))
    st.subheader("Raio-X")
    c1, c2, c3 = st.columns(3)
    with c1:
        _tabela_de_fatias("Por tipo", raio.por_tipo)
    with c2:
        _tabela_de_fatias("Por setor (CVM)", raio.por_setor)
    with c3:
        _tabela_de_fatias("Por moeda", raio.por_moeda)
    st.caption(ac.NOTA_DA_MOEDA)


def _fechamentos(tickers, periodo):
    fechamentos, falharam = {}, []
    for ticker in tickers:
        try:
            fechamentos[ticker] = carregar_dados(ticker, periodo)["Close"]
        except (DadosIndisponiveisError, ValueError):
            falharam.append(ticker)
    return fechamentos, falharam


def _mostrar_comportamento(carteira):
    st.subheader("A carteira de hoje no passado")
    periodo = st.selectbox(
        "Período",
        list(PERIODOS_DO_TOPO),
        index=list(PERIODOS_DO_TOPO).index(PERIODO_PADRAO),
        format_func=PERIODOS_DO_TOPO.get,
        key="carteira_b3_periodo",
    )
    fechamentos, falharam = _fechamentos(list(carteira.posicoes["ticker"]), periodo)
    if falharam:
        st.caption(f"Sem histórico de preço, ficaram de fora: {', '.join(falharam)}.")
    if not fechamentos:
        st.info("Nenhum ativo da carteira tem histórico de preço no período.")
        return
    ibovespa = _fechamentos([IBOVESPA], periodo)[0].get(IBOVESPA)
    comp = ac.comportamento(carteira, pd.DataFrame(fechamentos), ibovespa, 0.0)
    curvas = {"Minha carteira": pd.Series({p.dia: p.valor for p in comp.curva})}
    if comp.curva_ibovespa is not None:
        curvas[IBOVESPA] = pd.Series({p.dia: p.valor for p in comp.curva_ibovespa})
    base100 = pd.DataFrame(curvas)
    base100.index = pd.to_datetime(base100.index)
    mostrar_grafico(
        graficos.criar_grafico_comparacao(
            base100, "Minha carteira", {IBOVESPA: "Ibovespa"}
        )
    )
    st.caption(relatorios.AVISO_DA_MINHA_CARTEIRA)


def _mostrar_rebalanceamento(carteira):
    st.subheader("Rebalanceamento")
    atuais = carteira.pesos()
    editados = st.data_editor(
        pd.DataFrame(
            {
                "Ativo": carteira.posicoes["codigo"].to_list(),
                "Peso de hoje (%)": [
                    atuais[t] * 100 for t in carteira.posicoes["ticker"]
                ],
                "Peso que você quer (%)": [
                    atuais[t] * 100 for t in carteira.posicoes["ticker"]
                ],
            }
        ),
        disabled=["Ativo", "Peso de hoje (%)"],
        column_config={
            "Peso de hoje (%)": st.column_config.NumberColumn(format="%.2f"),
            "Peso que você quer (%)": st.column_config.NumberColumn(
                format="%.2f", min_value=0.0, max_value=100.0
            ),
        },
        hide_index=True,
        key="carteira_b3_pesos",
    )
    alvo = dict(
        zip(editados["Ativo"], editados["Peso que você quer (%)"] / 100, strict=True)
    )
    try:
        ajustes = ac.rebalancear(carteira, alvo)
    except ValueError as erro:
        st.info(str(erro))
        return
    st.dataframe(
        pd.DataFrame(
            {
                "Ativo": [a.codigo for a in ajustes],
                "Hoje (R$)": [a.valor_atual for a in ajustes],
                "Com os pesos escolhidos (R$)": [a.valor_alvo for a in ajustes],
                "Comprar (+) ou vender (−) (R$)": [a.diferenca for a in ajustes],
                "Ações (aprox.)": [a.quantidade for a in ajustes],
            }
        ),
        column_config={
            c: st.column_config.NumberColumn(format="%.2f")
            for c in (
                "Hoje (R$)",
                "Com os pesos escolhidos (R$)",
                "Comprar (+) ou vender (−) (R$)",
            )
        },
        hide_index=True,
        width="stretch",
    )
    st.caption(ac.AVISO_DO_REBALANCEAMENTO)


def pagina_carteira_b3():
    cabecalho_da_pagina("carteira_b3")
    carteira = _pedir_carteira()
    if carteira is None:
        return
    if carteira.posicoes.empty:
        st.info(
            "O arquivo só tem Tesouro e renda fixa, sem ativos com cotação para analisar."
        )
        return
    _mostrar_concentracao(carteira)
    _mostrar_raio_x(carteira)
    _mostrar_comportamento(carteira)
    _mostrar_rebalanceamento(carteira)
