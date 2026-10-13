"""O que cada página de análise mostra (src/analises.py): os mesmos números que a tela calculava."""

import pandas as pd
import pytest

from src import analises
from src import indicadores as ind
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
