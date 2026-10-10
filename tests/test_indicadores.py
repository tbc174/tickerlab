"""Testes de src/indicadores.py. Os números são pequenos para dar para conferir de cabeça."""

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_series_equal

from src.indicadores import (
    DIAS_POR_ANO,
    calcular_drawdown,
    calcular_media_movel,
    calcular_retorno_acumulado,
    calcular_retorno_diario,
    calcular_volatilidade_anual,
)


def test_retorno_diario():
    # 100 -> 110 sobe 10%; 110 -> 99 cai 10%. O primeiro dia não tem dia anterior.
    fechamento = pd.Series([100.0, 110.0, 99.0])
    esperado = pd.Series([np.nan, 0.10, -0.10])
    assert_series_equal(calcular_retorno_diario(fechamento), esperado)


def test_retorno_acumulado():
    # Subir 10% e cair 10% NÃO volta ao zero: 1,10 x 0,90 = 0,99, ou seja, -1%.
    retorno = pd.Series([np.nan, 0.10, -0.10])
    esperado = pd.Series([np.nan, 0.10, -0.01])
    assert_series_equal(calcular_retorno_acumulado(retorno), esperado)


def test_retorno_acumulado_bate_com_preco_final_sobre_inicial():
    fechamento = pd.Series([50.0, 55.0, 44.0, 60.0])
    acumulado = calcular_retorno_acumulado(calcular_retorno_diario(fechamento))
    assert acumulado.iloc[-1] == pytest.approx(60.0 / 50.0 - 1)


def test_media_movel():
    # Janela 3: média de [1,2,3] = 2, de [2,3,4] = 3, de [3,4,5] = 4.
    # Os dois primeiros dias não têm 3 valores, então ficam vazios.
    fechamento = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    esperado = pd.Series([np.nan, np.nan, 2.0, 3.0, 4.0])
    assert_series_equal(calcular_media_movel(fechamento, 3), esperado)


def test_volatilidade_anual():
    # Desvio padrão (amostral) de [+1%, -1%, +1%, -1%] = raiz(0,0004 / 3).
    retorno = pd.Series([0.01, -0.01, 0.01, -0.01])
    esperado = np.sqrt(0.0004 / 3) * np.sqrt(DIAS_POR_ANO)
    assert calcular_volatilidade_anual(retorno) == pytest.approx(esperado)


def test_volatilidade_ignora_o_primeiro_dia_vazio():
    com_vazio = pd.Series([np.nan, 0.01, -0.01, 0.01, -0.01])
    sem_vazio = pd.Series([0.01, -0.01, 0.01, -0.01])
    assert calcular_volatilidade_anual(com_vazio) == pytest.approx(
        calcular_volatilidade_anual(sem_vazio)
    )


def test_volatilidade_de_preco_parado_e_zero():
    retorno = pd.Series([0.0, 0.0, 0.0, 0.0])
    assert calcular_volatilidade_anual(retorno) == 0.0


def test_drawdown():
    # Picos até cada dia: 100, 120, 120, 120, 120.
    # 90 está 25% abaixo de 120; 60 está 50% abaixo; voltar a 120 zera a queda.
    fechamento = pd.Series([100.0, 120.0, 90.0, 120.0, 60.0])
    esperado = pd.Series([0.0, 0.0, -0.25, 0.0, -0.50])
    assert_series_equal(calcular_drawdown(fechamento), esperado)


def test_drawdown_nunca_e_positivo():
    fechamento = pd.Series([10.0, 12.0, 11.0, 15.0, 9.0, 20.0])
    assert (calcular_drawdown(fechamento) <= 0).all()


def test_drawdown_de_preco_sempre_subindo_e_zero():
    fechamento = pd.Series([10.0, 11.0, 12.0, 13.0])
    assert calcular_drawdown(fechamento).min() == 0.0
