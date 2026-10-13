"""O que cada página de análise mostra (src/analises.py): os mesmos números que a tela calculava."""

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal

from src import analises
from src import indicadores as ind
from src.comparacao import (
    alinhar_fechamentos,
    montar_tabela_comparativa,
    rebasear_para_100,
)
from src.exemplos import carregar_exemplo

TAXA = 0.10


@pytest.fixture(scope="module")
def petr4():
    dados = carregar_exemplo("PETR4.SA", "5y")
    assert dados is not None
    fechamento = dados["Close"]
    return fechamento, ind.calcular_retorno_diario(fechamento)


def test_painel_de_numeros_igual_as_contas_da_tela(petr4):
    fechamento, retorno = petr4
    painel = analises.painel_de_numeros(fechamento, retorno, TAXA, 95)

    assert painel.retorno_total == ind.calcular_retorno_acumulado(retorno).iloc[-1]
    assert painel.retorno_anualizado == ind.calcular_retorno_anualizado(retorno)
    assert painel.volatilidade_anual == ind.calcular_volatilidade_anual(retorno)
    assert painel.maior_queda == ind.calcular_drawdown(fechamento).min()
    assert painel.sharpe == ind.calcular_indice_sharpe(retorno, TAXA)
    assert (painel.data_do_melhor_dia, painel.melhor_dia) == ind.encontrar_melhor_dia(
        retorno
    )
    assert (painel.data_do_pior_dia, painel.pior_dia) == ind.encontrar_pior_dia(retorno)
    assert painel.dias_de_alta == ind.calcular_percentual_dias_positivos(retorno)
    assert painel.confianca_do_var == 95
    assert painel.var == ind.calcular_var_historico(retorno, 0.95)
    assert painel.cvar == ind.calcular_cvar_historico(retorno, 0.95)


def test_painel_usa_a_confianca_pedida(petr4):
    fechamento, retorno = petr4
    painel = analises.painel_de_numeros(fechamento, retorno, TAXA, 99)
    assert painel.var == ind.calcular_var_historico(retorno, 0.99)
    assert painel.var <= analises.painel_de_numeros(fechamento, retorno, TAXA, 95).var


def test_painel_so_com_tipos_simples(petr4):
    """Pronto para virar JSON (ADR 0044): números, datas e nada de série do pandas."""
    painel = analises.painel_de_numeros(*petr4, TAXA, 95)
    for valor in vars(painel).values():
        assert isinstance(valor, (int, float, pd.Timestamp)), type(valor)


def test_risco_ao_longo_do_tempo_igual_as_contas_da_tela(petr4):
    fechamento, retorno = petr4
    risco = analises.risco_ao_longo_do_tempo(fechamento, retorno, 63)
    assert_series_equal(risco.drawdown, ind.calcular_drawdown(fechamento))
    assert risco.pior_drawdown == ind.encontrar_pior_drawdown(fechamento)
    assert risco.janela == 63
    assert_series_equal(
        risco.volatilidade_movel, ind.calcular_volatilidade_movel(retorno, 63)
    )


def test_retorno_mensal_igual_as_contas_da_tela(petr4):
    _, retorno = petr4
    mensal = analises.retorno_mensal(retorno)
    esperado = ind.calcular_retorno_mensal(retorno)
    assert_series_equal(mensal.retornos, esperado)
    assert_frame_equal(mensal.tabela, ind.montar_tabela_retornos(esperado))
    (mes_melhor, melhor), (mes_pior, pior) = ind.encontrar_melhor_e_pior_mes(esperado)
    assert (mensal.mes_melhor, mensal.melhor) == (mes_melhor, melhor)
    assert (mensal.mes_pior, mensal.pior) == (mes_pior, pior)
    assert mensal.meses_de_alta == ind.calcular_percentual_dias_positivos(esperado)


def _fechamentos(*tickers):
    return {t: carregar_exemplo(t, "2y")["Close"] for t in tickers}


def test_comparacao_igual_as_contas_da_tela():
    fechamentos = _fechamentos("PETR4.SA", "VALE3.SA", "AAPL")
    comparacao = analises.comparacao_de_ativos(fechamentos, TAXA)
    alinhado, descartados = alinhar_fechamentos(fechamentos)
    assert comparacao.dias_em_comum == len(alinhado)
    assert comparacao.dias_descartados == descartados
    assert comparacao.suficiente
    assert_frame_equal(comparacao.base_100, rebasear_para_100(alinhado))
    assert_frame_equal(comparacao.tabela, montar_tabela_comparativa(alinhado, TAXA))


def test_comparacao_curta_demais_nao_calcula_nada():
    """Com até MIN_DIAS_PARA_ANALISE dias em comum, os números não dizem nada."""
    fechamentos = {
        t: s.iloc[-analises.MIN_DIAS_PARA_ANALISE :]
        for t, s in _fechamentos("PETR4.SA", "VALE3.SA").items()
    }
    comparacao = analises.comparacao_de_ativos(fechamentos, TAXA)
    assert comparacao.dias_em_comum <= analises.MIN_DIAS_PARA_ANALISE
    assert not comparacao.suficiente
    assert comparacao.base_100 is None and comparacao.tabela is None


# --- textos da visão geral que a tela nova (React) recebe prontos (série 3 da ADR 0048) ---


def test_aviso_da_origem_dos_precos():
    assert analises.aviso_da_origem("atual", "2026-10-10") is None
    antigo = analises.aviso_da_origem("cache_antigo", "2026-10-10")
    assert antigo is not None and "2026-10-10" in antigo and "Yahoo" in antigo
    exemplo = analises.aviso_da_origem("exemplo", "2025-12-30")
    assert exemplo is not None and "dados de exemplo" in exemplo


def test_itens_do_painel_cobrem_os_numeros_da_visao_geral():
    from dataclasses import fields

    from src.conteudo import carregar_glossario

    campos = {f.name for f in fields(analises.PainelDeNumeros)}
    glossario = carregar_glossario()
    for item in analises.ITENS_DO_PAINEL:
        assert item.campo in campos, item.campo
        assert item.termo in glossario, item.termo
        assert item.formato in ("pct", "pct_com_sinal", "decimal")
        assert item.campo_da_data is None or item.campo_da_data in campos
    numeros = {i.campo for i in analises.ITENS_DO_PAINEL}
    datas = {i.campo_da_data for i in analises.ITENS_DO_PAINEL}
    # tudo do painel aparece: como número, como data de um número, ou o CVaR na frase de baixo
    assert campos - numeros - datas == {"cvar", "confianca_do_var"}
