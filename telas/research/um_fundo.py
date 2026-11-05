"""Research: Donos e fundos, aba "Um fundo" (linha 664, d): taxas, custo da taxa e carteira de um fundo da CVM.

A conta e o portão ficam em `src/fundo_no_app.py`; aqui só a cola com o Streamlit. Regra de `telas/`:
nenhum estado mutável no módulo.
"""

from datetime import datetime

import streamlit as st

from src import relatorios
from src.fundo_no_app import (
    ATRIBUICAO,
    FundoIndisponivelError,
    FundoNaTela,
    fundo_na_tela,
)
from telas.research.comum import _dinheiro, _numero_br

RETORNO_DO_EXEMPLO_EM_PCT = 10.0
RETORNO_MAXIMO_EM_PCT = 50.0
POSICOES_MOSTRADAS = 50


def _pct(valor: object) -> str:
    return "sem informação" if valor is None else f"{_numero_br(float(valor), 2)}%"  # type: ignore[arg-type]


def _cadastro(fundo: FundoNaTela) -> None:
    cadastro = fundo.cadastro
    if not cadastro:
        st.info("O cadastro deste fundo ainda não é público para o dia de hoje.")
        return
    st.subheader(str(cadastro.get("nome", fundo.cnpj)))
    colunas = st.columns(4)
    colunas[0].metric("Classe", str(cadastro.get("classe") or "sem informação"))
    colunas[1].metric(
        "Taxa de administração", _pct(cadastro.get("taxa_administracao_pct_ao_ano"))
    )
    colunas[2].metric("Taxa de performance", _pct(cadastro.get("taxa_performance_pct")))
    patrimonio = cadastro.get("patrimonio_liquido")
    colunas[3].metric(
        "Patrimônio líquido",
        "sem informação" if patrimonio is None else _dinheiro(float(patrimonio)),  # type: ignore[arg-type]
    )
    st.caption(
        f"Situação: {cadastro.get('situacao') or 'sem informação'}. Cadastro da CVM visto em "
        f"{fundo.cadastro_publico_em:%d/%m/%Y}."
    )
    if cadastro.get("texto_taxa_performance"):
        st.caption(f"Taxa de performance: {cadastro['texto_taxa_performance']}")


def _custo(fundo: FundoNaTela) -> None:
    if not fundo.custo_da_taxa:
        return
    retorno = _numero_br((fundo.retorno_suposto or 0) * 100, 1)
    st.markdown(
        f"**Quanto a taxa de administração come**, para R$ 10.000 e um retorno de {retorno}% ao ano "
        "antes da taxa. É uma conta com a hipótese que você deu, não uma previsão."
    )
    st.dataframe(
        [
            {
                "Prazo": f"{int(linha['anos'])} anos",
                "Sem taxa": f"R$ {_numero_br(linha['sem_taxa'], 0)}",
                "Com taxa": f"R$ {_numero_br(linha['com_taxa'], 0)}",
                "Fica com a taxa": f"R$ {_numero_br(linha['ficou_com_a_taxa'], 0)}",
                "Parte do resultado": _pct(linha["fracao_do_resultado"] * 100),
            }
            for linha in fundo.custo_da_taxa
        ],
        hide_index=True,
        width="stretch",
    )


def _carteira(fundo: FundoNaTela) -> None:
    if not fundo.carteira:
        st.info("A carteira deste fundo ainda não é pública na base.")
        return
    competencia = str(fundo.carteira[0]["competencia"])[:7]
    st.markdown(f"**Carteira de {competencia}** (o mês mais novo já público)")
    maiores = sorted(fundo.carteira, key=lambda p: -(p.get("valor") or 0))
    st.dataframe(
        [
            {
                "Código": p.get("codigo") or p.get("isin") or "",
                "Emissor": p.get("emissor") or "",
                "Tipo": p.get("tipo") or "",
                "Quantidade": _numero_br(p["quantidade"], 0)
                if p.get("quantidade")
                else "",
                "Valor": _dinheiro(p["valor"]) if p.get("valor") else "",
            }
            for p in maiores[:POSICOES_MOSTRADAS]
        ],
        hide_index=True,
        width="stretch",
    )
    if fundo.carteira_cortada or len(maiores) > POSICOES_MOSTRADAS:
        st.caption(f"As {POSICOES_MOSTRADAS} maiores posições por valor.")


def _retorno_suposto() -> float | None:
    if not st.checkbox(
        "Calcular quanto a taxa come com um retorno que eu suponho",
        key="fundo_com_retorno",
    ):
        return None
    pct = st.number_input(
        "Retorno suposto ao ano, antes da taxa (%)",
        min_value=0.0,
        max_value=RETORNO_MAXIMO_EM_PCT,
        value=RETORNO_DO_EXEMPLO_EM_PCT,
        step=0.5,
        key="fundo_retorno",
    )
    return pct / 100


def aba_um_fundo() -> None:
    st.caption(
        "Taxas, patrimônio e carteira de um fundo registrado na CVM, pelo CNPJ. Nada aqui é "
        "recomendação de investimento."
    )
    cnpj = st.text_input(
        "CNPJ do fundo", placeholder="00.000.000/0000-00", key="fundo_cnpj"
    )
    retorno = _retorno_suposto()
    if not cnpj.strip():
        return
    hoje = datetime.now(relatorios.FUSO).date()
    try:
        fundo = fundo_na_tela(cnpj, hoje, retorno)
    except ValueError:
        st.warning("Esse CNPJ não é válido. Confira os números.")
        return
    except FundoIndisponivelError:
        st.info(
            "A base dos fundos não está disponível agora. Tente de novo mais tarde."
        )
        return
    if fundo is None:
        st.info("Não achamos esse fundo na base da CVM.")
        return
    _cadastro(fundo)
    _custo(fundo)
    _carteira(fundo)
    st.caption(f"{ATRIBUICAO}. Uma lista de fatos, não de recomendações.")
