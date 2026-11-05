"""Research: Simulador de trava do café (linha 340), só com o preço de referência mensal e só na memória.

A tela só lê, chama `src/commodities/cafe/trava.py` e mostra os textos de `textos_da_trava.py`. O que o
produtor digita fica só nos campos da página: nada vai para o banco nem para o log. Regra de `telas/`:
nenhum estado mutável no módulo.
"""

import logging
from datetime import date

import pandas as pd
import streamlit as st

from src import relatorios
from src.banco.conexao import obter_engine, tabela_inexistente
from src.commodities.cafe import textos_da_trava as textos
from src.commodities.cafe import trava
from telas.comum import cabecalho_da_pagina

log = logging.getLogger(__name__)

PADRAO_SACAS = 1_000
PADRAO_CUSTO = 1_000.0
PADRAO_MES_DA_COLHEITA = 6  # junho, o meio da colheita do arábica
PADRAO_ANTECEDENCIA = 6
PADRAO_PARTE_TRAVADA = 100  # 100%: cada coluna mostra uma forma de travar sozinha
PADRAO_PREMIO = 5
PORCENTO = 100


def _pedir_a_entrada() -> trava.EntradaDaTrava:
    """Os campos da produção; os valores ficam só nos widgets, enquanto a página está aberta."""
    esquerda, direita = st.columns(2)
    with esquerda:
        tipo = st.radio(
            textos.ROTULO_TIPO,
            trava.TIPOS,
            format_func=textos.NOMES_DOS_TIPOS.__getitem__,
            horizontal=True,
            key="trava_tipo",
        )
        sacas = st.number_input(
            textos.ROTULO_SACAS,
            min_value=1,
            value=PADRAO_SACAS,
            step=100,
            key="trava_sacas",
        )
        custo = st.number_input(
            textos.ROTULO_CUSTO,
            min_value=0.01,
            value=PADRAO_CUSTO,
            step=50.0,
            key="trava_custo",
        )
        mes = st.selectbox(
            textos.ROTULO_MES_DA_COLHEITA,
            range(1, trava.MESES_NO_ANO + 1),
            index=PADRAO_MES_DA_COLHEITA - 1,
            format_func=lambda m: textos.NOMES_DOS_MESES[m - 1],
            key="trava_mes",
        )
    with direita:
        antecedencia = st.slider(
            textos.ROTULO_ANTECEDENCIA, 1, trava.ANTECEDENCIA_MAXIMA, PADRAO_ANTECEDENCIA,
            key="trava_antecedencia",
        )  # fmt: skip
        parte = st.slider(
            textos.ROTULO_FRACAO,
            0,
            PORCENTO,
            PADRAO_PARTE_TRAVADA,
            step=5,
            key="trava_parte",
        )
        premio = st.number_input(
            textos.ROTULO_PREMIO, min_value=0.0, max_value=trava.PREMIO_MAXIMO * PORCENTO,
            value=float(PADRAO_PREMIO), step=0.5, help=textos.AJUDA_PREMIO, key="trava_premio",
        )  # fmt: skip
    return trava.EntradaDaTrava(
        tipo=tipo,
        sacas=float(sacas),
        custo_por_saca=float(custo),
        mes_da_colheita=int(mes),
        meses_de_antecedencia=int(antecedencia),
        fracao_travada=parte / PORCENTO,
        premio_da_opcao=premio / PORCENTO,
    )


def _ler_precos(tipo: str, hoje: date) -> pd.DataFrame | None:
    """Os preços por saca de hoje, ou None (com o aviso) se o acervo ainda não tem as séries."""
    try:
        with obter_engine().connect() as conexao:
            precos = trava.ler_precos(conexao, tipo, hoje)
    except Exception as erro:
        if not tabela_inexistente(erro):
            log.exception("Falha ao ler os preços do simulador de trava")
            st.error("Não consegui ler os preços agora. Tente de novo em instantes.")
            return None
        precos = pd.DataFrame()
    if precos.empty:
        st.info(textos.SEM_PRECOS)
        return None
    return precos


def _mostrar_resultados(simulacao: trava.SimulacaoDaTrava) -> None:
    st.warning(textos.AVISO_DIARIO)
    if not simulacao.safras:
        st.info(textos.SEM_SAFRAS)
        return
    st.subheader(textos.TITULO_DO_RESUMO)
    st.caption(textos.explicacao_do_cenario(simulacao))
    st.dataframe(textos.linhas_do_resumo(simulacao), hide_index=True)
    st.subheader(textos.TITULO_DAS_SAFRAS)
    st.caption(textos.EXPLICACAO_DAS_SAFRAS)
    st.dataframe(textos.linhas_das_safras(simulacao), hide_index=True)


def _mostrar_riscos() -> None:
    st.subheader(textos.TITULO_DOS_RISCOS)
    for instrumento in textos.INSTRUMENTOS:
        with st.expander(instrumento.nome):
            st.markdown(instrumento.como_funciona)
            st.markdown(f"**+** {instrumento.lado_bom}")
            st.markdown(f"**−** {instrumento.lado_ruim}")
            st.markdown(f"**?** {instrumento.o_que_nao_se_sabe}")
    st.subheader(textos.TITULO_DO_QUE_MUDARIA)
    st.markdown("\n".join(f"- {frase}" for frase in textos.O_QUE_MUDARIA))


def pagina_simulador_de_trava() -> None:
    cabecalho_da_pagina("simulador_de_trava")
    st.markdown(textos.INTRODUCAO)
    st.warning(textos.AVISO_SEM_RECOMENDACAO)
    st.caption(textos.AVISO_SO_NA_MEMORIA)
    entrada = _pedir_a_entrada()
    precos = _ler_precos(entrada.tipo, pd.Timestamp.now(tz=relatorios.FUSO).date())
    if precos is not None:
        try:
            _mostrar_resultados(trava.simular_trava(entrada, precos))
        except ValueError as erro:
            st.error(f"Confira os números: {erro}.")
    _mostrar_riscos()
    st.caption(textos.ATRIBUICAO)
    st.caption(textos.FONTE_DO_CAMBIO)
