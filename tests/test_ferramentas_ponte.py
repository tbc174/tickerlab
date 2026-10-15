"""A conta da ferramenta "Quanto daria? Foi sorte?" (src/ferramentas/ponte.py), sem rede.

Só números soltos (valor final, retorno, valor em poder de compra e o resumo das janelas), nunca a
série (ADR 0070). As janelas são todas as datas de início com o mesmo prazo até hoje; elas se
sobrepõem, então não são sorteios independentes.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.ferramentas import ponte

DIAS = pd.to_datetime(
    ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]
)
CURVA = pd.Series([1.0, 1.1, 0.9, 1.2, 1.5], index=DIAS)


def test_janelas_sao_todas_as_datas_de_inicio_com_o_mesmo_prazo():
    assert ponte.janelas(CURVA, 2) == pytest.approx([0.9, 1.2 / 1.1, 1.5 / 0.9])


def test_resultado_da_data_escolhida_e_a_posicao_dela_entre_as_janelas():
    r = ponte.resultado_do_ativo(
        "ibovespa", CURVA, date(2026, 1, 7), 1000, fator_do_ipca=1.2
    )
    assert r.inicio == date(2026, 1, 7)
    assert r.fim == date(2026, 1, 9)
    assert r.valor_final == pytest.approx(1000 * 1.5 / 0.9)
    assert r.retorno == pytest.approx(1.5 / 0.9 - 1)
    assert r.valor_real == pytest.approx(1000 * 1.5 / 0.9 / 1.2)
    j = r.janelas
    assert j is not None
    assert j.quantas == 3
    assert j.pior == pytest.approx(900)
    assert j.mediana == pytest.approx(1000 * 1.2 / 1.1)
    assert j.melhor == pytest.approx(1000 * 1.5 / 0.9)
    assert j.abaixo_da_sua == pytest.approx(2 / 3)


def test_data_sem_pregao_comeca_no_proximo_dia_com_dado():
    fim_de_semana = date(2026, 1, 4)  # domingo: começa na segunda, 05/01
    assert ponte.resultado_do_ativo(
        "cdi", CURVA, fim_de_semana, 1000, 1.0
    ).inicio == date(2026, 1, 5)


def test_parado_nao_rende_e_perde_para_a_inflacao_sem_janelas():
    constante = pd.Series(1.0, index=DIAS)
    r = ponte.resultado_do_ativo(
        "parado", constante, date(2026, 1, 5), 1000, fator_do_ipca=1.25
    )
    assert r.valor_final == 1000
    assert r.valor_real == pytest.approx(800)
    assert r.janelas is None


def test_data_antes_do_primeiro_dado_ou_sem_prazo_e_erro():
    with pytest.raises(ValueError, match="começam em"):
        ponte.resultado_do_ativo("ibovespa", CURVA, date(2025, 12, 1), 1000, 1.0)
    with pytest.raises(ValueError, match="prazo"):
        ponte.resultado_do_ativo("ibovespa", CURVA, date(2026, 1, 9), 1000, 1.0)


@pytest.mark.parametrize(
    ("desde", "valor", "mensagem"),
    [
        (date(2020, 1, 2), 0, "valor"),
        (date(2020, 1, 2), 20_000_000, "valor"),
        (date(2026, 10, 1), 1000, "30 dias"),
        (date(2026, 12, 1), 1000, "30 dias"),
    ],
)
def test_conferir_o_pedido(desde, valor, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        ponte.conferir_pedido(desde, valor, hoje=date(2026, 10, 15))


def test_pedido_valido_passa():
    ponte.conferir_pedido(date(2020, 1, 2), 1000, hoje=date(2026, 10, 15))


def test_ativos_e_fontes():
    assert set(ponte.ATIVOS) == {
        "cdi",
        "poupanca",
        "dolar",
        "parado",
        "ibovespa",
        "bitcoin",
    }
    assert set(ponte.ATIVOS_DO_YAHOO) == {"ibovespa", "bitcoin"}
    assert (
        "Yahoo" in ponte.FONTES["bitcoin"]
        and "Banco Central" in ponte.FONTES["bitcoin"]
    )
    assert "Banco Central" in ponte.FONTES["cdi"]


@given(
    st.lists(st.floats(0.5, 2.0), min_size=3, max_size=60),
    st.data(),
)
@settings(max_examples=60, deadline=None)
def test_a_posicao_fica_entre_0_e_1_e_as_janelas_sao_as_que_cabem(retornos, dados):
    curva = pd.Series(
        np.cumprod(retornos), index=pd.bdate_range("2020-01-01", periods=len(retornos))
    )
    inicio = dados.draw(st.integers(0, len(curva) - 2))
    r = ponte.resultado_do_ativo(
        "bitcoin", curva, curva.index[inicio].date(), 1000, 1.0
    )
    assert r.janelas is not None
    assert r.janelas.quantas == inicio + 1
    assert 0 <= r.janelas.abaixo_da_sua < 1
    assert r.janelas.pior <= r.valor_final <= r.janelas.melhor


def test_data_antes_do_plano_real_e_recusada():
    # sem dado antes de jul/1994; e cada mês vira uma entrada no cache da rota: limitar os meses
    # limita a memória que um pedido de fora pode gastar
    with pytest.raises(ValueError, match="1994"):
        ponte.conferir_pedido(date(1990, 1, 1), 1000, hoje=date(2026, 10, 15))
    ponte.conferir_pedido(date(1994, 7, 1), 1000, hoje=date(2026, 10, 15))
