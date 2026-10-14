"""Carteira da B3: a posição da Área do Investidor lida só na memória, para todos os planos.

Concentração, a carteira no passado, Raio-X e Rebalanceamento; com a planilha de movimentação,
proventos recebidos e custo médio. A tela só lê, chama `src/analise_da_carteira.py` e
`src/dividendos_e_custo.py` e mostra; nada das planilhas é guardado (nem em banco, nem em log).
Regra de `telas/`: nenhum estado mutável no módulo.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

import pandas as pd
import streamlit as st

from src import analise_da_carteira as ac
from src import dividendos_e_custo as dc
from src import graficos, relatorios
from src import proventos_a_receber as par
from src import resultado_por_mes as rpm
from src.analise import FUSO  # "hoje" é o do Brasil, não o do servidor
from src.banco.conexao import obter_engine, tabela_inexistente
from src.banco.demonstracoes import setores_dos_tickers
from src.carteira_b3 import ArquivoDaB3Error, CarteiraB3, ler_carteira
from src.dados import DadosIndisponiveisError
from src.movimentacao_b3 import MovimentacaoB3, ler_movimentacao
from src.negociacao_b3 import ler_negociacao
from src.proventos_a_receber import ProventosAReceber, ler_proventos_a_receber
from telas.comum import (
    PERIODOS_DO_TOPO,
    cabecalho_da_pagina,
    carregar_dados,
    formatar_pct,
    mostrar_grafico,
)
from telas.relatorios.estudio import ARQUIVO_DA_CARTEIRA_DE_EXEMPLO

ARQUIVO_DA_MOVIMENTACAO_DE_EXEMPLO = (
    ARQUIVO_DA_CARTEIRA_DE_EXEMPLO.parent / "movimentacao_de_exemplo.xlsx"
)
ARQUIVO_DOS_PROVENTOS_DE_EXEMPLO = (
    ARQUIVO_DA_CARTEIRA_DE_EXEMPLO.parent / "proventos_a_receber_de_exemplo.xlsx"
)
ARQUIVO_DA_NEGOCIACAO_DE_EXEMPLO = (
    ARQUIVO_DA_CARTEIRA_DE_EXEMPLO.parent / "negociacao_de_exemplo.xlsx"
)

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


class _ComAvisos(Protocol):
    @property
    def avisos(self) -> tuple[str, ...]: ...


@dataclass(frozen=True)
class _Planilha:
    """Como pedir uma planilha da B3: o passo a passo, o exemplo fictício e o campo de arquivo."""

    como_baixar: str
    rotulo_do_exemplo: str
    aviso_do_exemplo: str
    arquivo_de_exemplo: Path
    rotulo_do_campo: str
    chave: str  # do campo de arquivo; o botão do exemplo usa a chave + "_exemplo"


_MOVIMENTACAO = _Planilha(
    dc.COMO_BAIXAR_A_MOVIMENTACAO,
    "Usar a movimentação de exemplo (fictícia)",
    dc.AVISO_DA_MOVIMENTACAO_DE_EXEMPLO,
    ARQUIVO_DA_MOVIMENTACAO_DE_EXEMPLO,
    "Planilha de movimentação da B3",
    "carteira_b3_movimentacao",
)
_PROVENTOS_A_RECEBER = _Planilha(
    par.COMO_BAIXAR_OS_PROVENTOS,
    "Usar os proventos a receber de exemplo (fictícios)",
    par.AVISO_DOS_PROVENTOS_DE_EXEMPLO,
    ARQUIVO_DOS_PROVENTOS_DE_EXEMPLO,
    "Planilha de proventos a receber da B3",
    "carteira_b3_proventos",
)
_NEGOCIACAO = _Planilha(
    rpm.COMO_BAIXAR_A_NEGOCIACAO,
    "Usar a negociação de exemplo (fictícia)",
    rpm.AVISO_DA_NEGOCIACAO_DE_EXEMPLO,
    ARQUIVO_DA_NEGOCIACAO_DE_EXEMPLO,
    "Planilha de negociação da B3",
    "carteira_b3_negociacao",
)


def _pedir_planilha[T: _ComAvisos](
    planilha: _Planilha, ler: Callable[[bytes, str], T]
) -> T | None:
    """Pede a planilha (ou liga o exemplo), lê com `ler` e mostra os avisos; None sem arquivo."""
    st.markdown(planilha.como_baixar)
    if st.toggle(planilha.rotulo_do_exemplo, key=f"{planilha.chave}_exemplo"):
        st.warning(planilha.aviso_do_exemplo, icon=":material/science:")
        conteudo = planilha.arquivo_de_exemplo.read_bytes()
        nome = planilha.arquivo_de_exemplo.name
    else:
        arquivo = st.file_uploader(
            planilha.rotulo_do_campo, type=["xlsx", "csv"], key=planilha.chave
        )
        if arquivo is None:
            return None
        conteudo, nome = arquivo.getvalue(), arquivo.name
    try:
        lido = ler(conteudo, nome)
    except ArquivoDaB3Error as erro:
        st.error(str(erro))
        return None
    for aviso in lido.avisos:
        st.warning(aviso)
    return lido


def _dinheiro(colunas):
    return {c: st.column_config.NumberColumn(format="%.2f") for c in colunas}


def _mostrar_proventos(lancamentos):
    proventos = dc.proventos(lancamentos, hoje=datetime.now(FUSO).date())
    st.markdown("**Proventos recebidos**")
    if not proventos:
        st.info(dc.SEM_PROVENTOS)
        return
    c1, c2 = st.columns(2)
    c1.metric(
        "Proventos no período", dc.formatar_reais(sum(p.total for p in proventos))
    )
    c2.metric(
        "Últimos 12 meses",
        dc.formatar_reais(sum(p.ultimos_12_meses for p in proventos)),
    )
    tipos = [t for t in dc.TIPOS_DE_PROVENTO if any(t in p.por_tipo for p in proventos)]
    colunas_dos_tipos = [f"{dc.NOMES_DOS_PROVENTOS[t]} (R$)" for t in tipos]
    tabela = pd.DataFrame(
        {
            "Ativo": [p.codigo for p in proventos],
            "Total (R$)": [p.total for p in proventos],
            "Últimos 12 meses (R$)": [p.ultimos_12_meses for p in proventos],
            **{
                coluna: [p.por_tipo.get(t, 0.0) for p in proventos]
                for t, coluna in zip(tipos, colunas_dos_tipos, strict=True)
            },
        }
    )
    st.dataframe(
        tabela,
        column_config=_dinheiro(
            ["Total (R$)", "Últimos 12 meses (R$)", *colunas_dos_tipos]
        ),
        hide_index=True,
        width="stretch",
    )
    por_ano = dc.total_por_ano(proventos)
    st.dataframe(
        pd.DataFrame(
            {"Ano": [str(a) for a in por_ano], "Proventos (R$)": list(por_ano.values())}
        ),
        column_config=_dinheiro(["Proventos (R$)"]),
        hide_index=True,
    )
    st.caption(dc.NOTA_DOS_PROVENTOS)


def _mostrar_custo_sem_a_posicao(custos):
    custos = dc.custos_de_hoje(custos)
    st.dataframe(
        pd.DataFrame(
            {
                "Ativo": [c.codigo for c in custos],
                "Quantidade": [c.quantidade for c in custos],
                "Preço médio (R$)": [c.preco_medio for c in custos],
                "Custo total (R$)": [c.custo_total for c in custos],
                "Observação": [c.motivo or "" for c in custos],
            }
        ),
        column_config=_dinheiro(["Preço médio (R$)", "Custo total (R$)"]),
        hide_index=True,
        width="stretch",
    )
    st.info(dc.SEM_A_POSICAO)


def _mostrar_custo_com_a_posicao(resultados):
    st.dataframe(
        pd.DataFrame(
            {
                "Ativo": [r.codigo for r in resultados],
                "Quantidade": [r.quantidade for r in resultados],
                "Preço médio (R$)": [r.preco_medio for r in resultados],
                "Custo (R$)": [r.custo_total for r in resultados],
                "Valor hoje (R$)": [r.valor_hoje for r in resultados],
                "Ganho ou perda (R$)": [r.resultado for r in resultados],
                "Ganho ou perda (%)": [
                    None
                    if r.resultado_percentual is None
                    else r.resultado_percentual * 100
                    for r in resultados
                ],
                "Observação": [r.motivo or "" for r in resultados],
            }
        ),
        column_config={
            **_dinheiro(
                [
                    "Preço médio (R$)",
                    "Custo (R$)",
                    "Valor hoje (R$)",
                    "Ganho ou perda (R$)",
                ]
            ),
            "Ganho ou perda (%)": st.column_config.NumberColumn(format="%.1f%%"),
        },
        hide_index=True,
        width="stretch",
    )


def _mostrar_dividendos_e_custo(carteira: CarteiraB3 | None) -> MovimentacaoB3 | None:
    st.subheader("Dividendos e custo médio")
    movimentacao = _pedir_planilha(_MOVIMENTACAO, ler_movimentacao)
    if movimentacao is None:
        return None
    if movimentacao.primeira_data and movimentacao.ultima_data:
        st.caption(
            f"Movimentação de {movimentacao.primeira_data:%d/%m/%Y} a "
            f"{movimentacao.ultima_data:%d/%m/%Y}."
        )
    lancamentos = list(movimentacao.lancamentos)
    _mostrar_proventos(lancamentos)
    st.markdown("**Custo médio**")
    custos = dc.custo_medio(lancamentos)
    if carteira is None:
        _mostrar_custo_sem_a_posicao(custos)
    else:
        _mostrar_custo_com_a_posicao(dc.com_a_posicao(custos, carteira))
    for aviso in dict.fromkeys(a for c in custos for a in c.avisos):
        st.caption(aviso)
    st.caption(dc.NOTA_DO_CUSTO)
    return movimentacao


def _mostrar_proventos_a_receber() -> ProventosAReceber | None:
    st.subheader("Proventos a receber")
    proventos = _pedir_planilha(_PROVENTOS_A_RECEBER, ler_proventos_a_receber)
    if proventos is None:
        return None
    if not proventos.itens:
        st.info(par.SEM_PROVENTOS_A_RECEBER)
        return proventos
    st.metric("Total a receber", dc.formatar_reais(proventos.total))
    st.dataframe(
        pd.DataFrame(
            {
                "Ativo": [i.codigo for i in proventos.itens],
                "Provento": [i.tipo for i in proventos.itens],
                "Data prevista": [
                    f"{i.data:%d/%m/%Y}" if i.data else "sem data"
                    for i in proventos.itens
                ],
                "Quantidade": [i.quantidade or None for i in proventos.itens],
                "Valor (R$)": [i.valor for i in proventos.itens],
            }
        ),
        column_config=_dinheiro(["Valor (R$)"]),
        hide_index=True,
        width="stretch",
    )
    st.caption(par.NOTA_DOS_PROVENTOS_A_RECEBER)
    return proventos


# campo de `rpm.Mes` → coluna da tabela (só aparecem as que têm algum valor)
_COLUNAS_DO_RESULTADO = {
    "acoes_comum": "Ações (R$)",
    "acoes_day_trade": "Day trade (R$)",
    "fiis": "FIIs (R$)",
    "futuros": "Futuros (R$)",
    "outros": "Outros (R$)",
}


def _mostrar_resultado_por_mes(
    movimentacao: MovimentacaoB3 | None, proventos: ProventosAReceber | None
):
    st.subheader("Resultado por mês")
    # o nome de cada ativo diz se um código terminado em 11 é FII
    nomes = {
        **(proventos.nomes if proventos else {}),
        **(movimentacao.nomes if movimentacao else {}),
    }
    negociacao = _pedir_planilha(
        _NEGOCIACAO, lambda conteudo, nome: ler_negociacao(conteudo, nome, nomes)
    )
    if negociacao is None:
        return
    if not negociacao.negocios:
        st.info(rpm.SEM_NEGOCIOS)
        return
    if negociacao.primeira_data and negociacao.ultima_data:
        st.caption(
            f"Negociação de {negociacao.primeira_data:%d/%m/%Y} a "
            f"{negociacao.ultima_data:%d/%m/%Y}."
        )
    resultado = rpm.resultado_por_mes(
        negociacao, movimentacao.lancamentos if movimentacao else None
    )
    for aviso in resultado.avisos:
        st.warning(aviso)
    meses = list(reversed(resultado.meses))  # do mais novo ao mais velho
    st.metric("Resultado no período", dc.formatar_reais(sum(m.total for m in meses)))
    colunas = {
        campo: coluna
        for campo, coluna in _COLUNAS_DO_RESULTADO.items()
        if any(getattr(m, campo) for m in meses)
    }
    st.dataframe(
        pd.DataFrame(
            {
                "Mês": [f"{m.mes:02d}/{m.ano}" for m in meses],
                **{
                    coluna: [getattr(m, campo) for m in meses]
                    for campo, coluna in colunas.items()
                },
                "Total (R$)": [m.total for m in meses],
                "Vendas de ações (R$)": [m.vendas_de_acoes for m in meses],
            }
        ),
        column_config=_dinheiro(
            [*colunas.values(), "Total (R$)", "Vendas de ações (R$)"]
        ),
        hide_index=True,
        width="stretch",
    )
    if resultado.sem_resultado:
        st.markdown("**Ativos sem resultado**")
        st.dataframe(
            pd.DataFrame(
                {
                    "Ativo": [codigo for codigo, _ in resultado.sem_resultado],
                    "Por quê": [motivo for _, motivo in resultado.sem_resultado],
                }
            ),
            hide_index=True,
            width="stretch",
        )
    st.caption(rpm.NOTA_DO_RESULTADO)


def pagina_carteira_b3():
    cabecalho_da_pagina("carteira_b3")
    carteira = _pedir_carteira()
    if carteira is not None and carteira.posicoes.empty:
        st.info(
            "O arquivo só tem Tesouro e renda fixa, sem ativos com cotação para analisar."
        )
        carteira = None
    elif carteira is not None:
        _mostrar_concentracao(carteira)
        _mostrar_raio_x(carteira)
        _mostrar_comportamento(carteira)
        _mostrar_rebalanceamento(carteira)
    movimentacao = _mostrar_dividendos_e_custo(carteira)
    proventos = _mostrar_proventos_a_receber()
    _mostrar_resultado_por_mes(movimentacao, proventos)
