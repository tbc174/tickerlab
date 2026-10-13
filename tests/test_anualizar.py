"""Retorno "ao ano" só com pelo menos ~1 ano de dados (padrão GIPS), na tela, no PDF e na API.

Com pouco tempo, anualizar exagera: 1 mês de +14% vira "+438% ao ano". Abaixo do mínimo, o
retorno anualizado fica vazio ("—") e o texto explica; volatilidade e Sharpe continuam.
"""

from io import BytesIO

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pypdf import PdfReader
from streamlit.testing.v1 import AppTest

from src import analise, relatorios
from src import indicadores as ind
from src.analises import painel_de_numeros
from src.comparacao import alinhar_fechamentos, montar_tabela_comparativa
from src.exemplos import carregar_exemplo
from src.metricas import resumir_desempenho
from tests.ajudantes_da_conta import ir_para


def _retornos(n: int) -> pd.Series:
    sorteio = np.random.default_rng(n)
    return pd.Series(
        sorteio.normal(0.001, 0.02, n), index=pd.bdate_range("2020-01-01", periods=n)
    )


def _texto(pdf: bytes) -> str:
    texto = " ".join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)
    return " ".join(texto.split())


SEIS_MESES = carregar_exemplo("PETR4.SA", "6mo")
UM_ANO = carregar_exemplo("PETR4.SA", "1y")


# --- a regra -----------------------------------------------------------------------------------
def test_o_periodo_um_ano_do_app_e_anualizado_e_seis_meses_nao():
    assert SEIS_MESES is not None and UM_ANO is not None
    seis = ind.calcular_retorno_diario(SEIS_MESES["Close"])
    um = ind.calcular_retorno_diario(UM_ANO["Close"])
    assert np.isnan(ind.retorno_anualizado_para_mostrar(seis))
    assert ind.retorno_anualizado_para_mostrar(um) == ind.calcular_retorno_anualizado(
        um
    )


@settings(max_examples=40, deadline=None)
@given(n=st.integers(2, 400))
def test_abaixo_do_minimo_fica_vazio_e_acima_e_a_conta_de_sempre(n):
    retorno = _retornos(n)
    mostrado = ind.retorno_anualizado_para_mostrar(retorno)
    if n < ind.MIN_RETORNOS_PARA_ANUALIZAR:
        assert np.isnan(mostrado)
    else:
        assert mostrado == ind.calcular_retorno_anualizado(retorno)


def test_sharpe_e_volatilidade_continuam_com_periodo_curto():
    retorno = _retornos(60)
    assert not np.isnan(ind.calcular_indice_sharpe(retorno))
    assert not np.isnan(ind.calcular_volatilidade_anual(retorno))


# --- onde o número aparece ---------------------------------------------------------------------
def test_visao_geral_e_api_ficam_sem_ao_ano_com_seis_meses():
    fechamento = SEIS_MESES["Close"]
    painel = painel_de_numeros(
        fechamento, ind.calcular_retorno_diario(fechamento), 0.0, 95
    )
    assert np.isnan(painel.retorno_anualizado)
    assert not np.isnan(painel.sharpe)


def test_tabela_da_comparacao_fica_sem_ao_ano_com_seis_meses():
    alinhado, _ = alinhar_fechamentos(
        {t: carregar_exemplo(t, "6mo")["Close"] for t in ("PETR4.SA", "VALE3.SA")}
    )
    tabela = montar_tabela_comparativa(alinhado)
    assert tabela["Retorno anualizado"].isna().all()
    assert tabela["Retorno total"].notna().all()


def test_backtest_e_carteira_ficam_sem_ao_ano_com_periodo_curto():
    resumo = resumir_desempenho(_retornos(120))
    assert np.isnan(resumo["Retorno anualizado"])
    assert not np.isnan(resumo["Índice de Sharpe"])
    assert not np.isnan(resumir_desempenho(_retornos(300))["Retorno anualizado"])


def test_research_explica_por_que_nao_anualizou():
    curta = analise.analisar_ativo("PETR4.SA", SEIS_MESES)
    metrica = curta.metricas["retorno_anualizado"]
    assert metrica.valor is None
    assert "menor que 1 ano" in metrica.motivo
    longa = analise.analisar_ativo("PETR4.SA", UM_ANO)
    assert longa.metricas["retorno_anualizado"].valor is not None


def test_pdf_do_ativo_com_seis_meses_nao_projeta_e_explica():
    texto = _texto(relatorios.relatorio_do_ativo("PETR4.SA", SEIS_MESES))
    assert "ao ano" not in texto.split("Números-chave")[0].split("Resumo executivo")[-1]
    assert "menor que 1 ano" in texto
    achados = relatorios.achados_do_ativo("PETR4.SA", SEIS_MESES["Close"])
    assert "menor que 1 ano" in achados[0]


def test_pdf_do_ativo_com_um_ano_continua_com_ao_ano():
    achados = relatorios.achados_do_ativo("PETR4.SA", UM_ANO["Close"])
    assert "ao ano" in achados[0]


@pytest.mark.parametrize("pagina", ["visao_geral", "comparar", "backtest", "ranking"])
def test_paginas_com_seis_meses_abrem_sem_erro(pagina):
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    app.session_state["periodo"] = "6mo"
    ir_para(app, pagina)
    assert not app.exception, [e.value for e in app.exception]
    assert not app.error, [e.value for e in app.error]
    textos = " ".join(e.value for e in [*app.caption, *app.info])
    if pagina in ("visao_geral", "ranking"):
        assert ind.MOTIVO_SEM_ANUALIZAR in textos
