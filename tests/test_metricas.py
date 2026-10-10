"""Testes de src/metricas.py, com números pequenos conferíveis de cabeça."""

import numpy as np
import pandas as pd
import pytest

from src import indicadores as ind
from src.metricas import (
    calcular_calmar,
    calcular_duracao_maxima_do_drawdown,
    calcular_exposicao,
    calcular_fator_de_recuperacao,
    calcular_gain_to_pain,
    calcular_indice_ulcer,
    calcular_intervalo_do_sharpe,
    calcular_razao_de_cauda,
    calcular_retorno_total,
    calcular_sortino,
    resumir_desempenho,
    resumir_operacoes,
)


def _serie(valores):
    return pd.Series(
        valores, index=pd.date_range("2026-01-05", periods=len(valores), freq="B")
    )


# --- retorno, Sortino, Calmar -------------------------------------------------------


def test_retorno_total_compoe_os_retornos():
    assert calcular_retorno_total(_serie([0.10, -0.10])) == pytest.approx(
        1.10 * 0.90 - 1
    )


def test_sortino_usa_so_a_volatilidade_das_perdas():
    retorno = _serie([0.01, -0.02, 0.01, -0.02])
    desvio_das_perdas = np.sqrt((0.02**2 * 2) / 4) * np.sqrt(252)
    esperado = ind.calcular_retorno_anualizado(retorno) / desvio_das_perdas
    assert calcular_sortino(retorno) == pytest.approx(esperado)


def test_sortino_sem_nenhuma_perda_nao_existe():
    assert np.isnan(calcular_sortino(_serie([0.01, 0.02, 0.03])))


def test_calmar_divide_o_retorno_anual_pela_maior_queda():
    retorno = _serie(
        [0.10, -0.20, 0.05]
    )  # curva 1,10 / 0,88 / 0,924: maior queda = 20%
    esperado = ind.calcular_retorno_anualizado(retorno) / 0.20
    assert calcular_calmar(retorno) == pytest.approx(esperado)


def test_calmar_sem_queda_nao_existe():
    assert np.isnan(calcular_calmar(_serie([0.01, 0.01, 0.01])))


# --- quedas ---------------------------------------------------------------------------


def test_duracao_maxima_debaixo_dagua():
    # curva: 1,10 / 1,045 / 1,0346 / 1,0552 / 1,1607 (novo topo) / 1,1375
    retorno = _serie([0.10, -0.05, -0.01, 0.02, 0.10, -0.02])
    assert calcular_duracao_maxima_do_drawdown(retorno) == 3  # dias 2, 3 e 4


def test_duracao_sem_nenhuma_queda_e_zero():
    assert calcular_duracao_maxima_do_drawdown(_serie([0.01, 0.02])) == 0


def test_indice_ulcer():
    # curva 1,10 e 0,99: drawdowns de 0% e -10% -> raiz((0² + 10²) / 2)
    assert calcular_indice_ulcer(_serie([0.10, -0.10])) == pytest.approx(np.sqrt(50))


def test_fator_de_recuperacao():
    retorno = _serie(
        [0.10, -0.20, 0.05]
    )  # total = 1,1 x 0,8 x 1,05 - 1 = -7,6%; queda 20%
    assert calcular_fator_de_recuperacao(retorno) == pytest.approx(-0.076 / 0.20)


# --- distribuição -----------------------------------------------------------------------


def test_razao_de_cauda_simetrica_e_um():
    assert calcular_razao_de_cauda(_serie(np.arange(-50, 51) / 100)) == pytest.approx(
        1.0
    )


def test_razao_de_cauda_com_ganhos_maiores_que_as_perdas():
    # de -10% a +90%: percentil 95 = +85%, percentil 5 = -5%
    assert calcular_razao_de_cauda(_serie(np.arange(-10, 91) / 100)) == pytest.approx(
        17.0
    )


def test_gain_to_pain():
    # soma = 0,06; perdas somam 0,06
    assert calcular_gain_to_pain(_serie([0.10, -0.05, 0.02, -0.01])) == pytest.approx(
        1.0
    )


@pytest.mark.parametrize(
    "funcao",
    [
        calcular_sortino,
        calcular_calmar,
        calcular_indice_ulcer,
        calcular_razao_de_cauda,
        calcular_gain_to_pain,
        calcular_fator_de_recuperacao,
        calcular_retorno_total,
    ],
)
def test_sem_dados_devolve_nan(funcao):
    assert np.isnan(funcao(pd.Series([], dtype=float)))


# --- Sharpe com intervalo -------------------------------------------------------------------


def test_intervalo_do_sharpe_envolve_o_sharpe():
    retorno = _serie(np.tile([0.02, -0.01], 125))
    sharpe, minimo, maximo = calcular_intervalo_do_sharpe(retorno)
    assert minimo < sharpe < maximo
    assert sharpe == pytest.approx(ind.calcular_indice_sharpe(retorno))


def test_com_quatro_vezes_mais_dados_o_intervalo_fica_metade():
    curto = calcular_intervalo_do_sharpe(_serie(np.tile([0.02, -0.01], 125)))
    longo = calcular_intervalo_do_sharpe(_serie(np.tile([0.02, -0.01], 500)))
    largura_curta = curto[2] - curto[1]
    largura_longa = longo[2] - longo[1]
    assert largura_longa / largura_curta == pytest.approx(0.5, rel=0.02)


def test_intervalo_do_sharpe_com_poucos_dados():
    assert all(np.isnan(v) for v in calcular_intervalo_do_sharpe(_serie([0.01, 0.02])))


# --- exposição e operações ------------------------------------------------------------------


def test_exposicao_media():
    assert calcular_exposicao(_serie([0, 1, 1, 0])) == pytest.approx(0.5)
    assert calcular_exposicao(_serie([1, 1, 1])) == pytest.approx(1.0)


def _operacoes(retornos, abertas=None):
    abertas = abertas or [False] * len(retornos)
    return pd.DataFrame(
        {
            "entrada": pd.date_range("2026-01-05", periods=len(retornos)),
            "saida": pd.date_range("2026-01-06", periods=len(retornos)),
            "dias": [1] * len(retornos),
            "retorno": retornos,
            "aberta": abertas,
        }
    )


def test_resumo_das_operacoes():
    resumo = resumir_operacoes(_operacoes([0.10, -0.05, 0.02]))
    assert resumo["Operações"] == 3
    assert resumo["Taxa de acerto"] == pytest.approx(2 / 3)
    assert resumo["Payoff médio"] == pytest.approx(
        0.06 / 0.05
    )  # ganho médio / perda média
    assert resumo["Profit factor"] == pytest.approx(0.12 / 0.05)
    assert resumo["Expectativa por operação"] == pytest.approx(0.07 / 3)


def test_resumo_sem_operacoes():
    resumo = resumir_operacoes(_operacoes([]))
    assert resumo["Operações"] == 0
    assert np.isnan(resumo["Taxa de acerto"])


def test_resumo_so_com_ganhos_nao_tem_payoff_nem_profit_factor():
    resumo = resumir_operacoes(_operacoes([0.10, 0.02]))
    assert resumo["Taxa de acerto"] == 1.0
    assert np.isnan(resumo["Payoff médio"]) and np.isnan(resumo["Profit factor"])


def test_resumo_inclui_a_operacao_ainda_aberta():
    resumo = resumir_operacoes(_operacoes([0.10, -0.05], abertas=[False, True]))
    assert resumo["Operações"] == 2


def test_resumo_de_desempenho_traz_as_metricas_na_ordem_da_tela():
    retorno = _serie(np.tile([0.02, -0.01], 50))
    posicao = _serie([1.0] * 100)
    resumo = resumir_desempenho(retorno, posicao, _operacoes([0.10]))
    chaves = list(resumo)
    assert chaves[:3] == ["Retorno total", "Retorno anualizado", "Volatilidade anual"]
    assert "Índice de Sortino" in resumo and "Exposição média" in resumo
    assert "Profit factor" in resumo or "Expectativa por operação" in resumo
