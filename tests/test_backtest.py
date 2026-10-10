"""Testes de src/backtest.py. Os números são pequenos para dar para conferir de cabeça."""

import numpy as np
import pandas as pd
import pytest

from src.backtest import executar_backtest


def _datas(n):
    return pd.date_range("2026-01-05", periods=n, freq="B")


def _precos(valores):
    return pd.Series(valores, index=_datas(len(valores)), dtype=float)


def _posicao(valores, como):
    return pd.Series(valores, index=como.index, dtype=float)


# --- comprar e segurar -----------------------------------------------------------


def test_comprar_e_segurar_sem_custo_rende_o_mesmo_que_o_preco():
    fechamento = _precos([100, 110, 121])
    resultado = executar_backtest(fechamento, _posicao([1, 1, 1], fechamento), 0.0)
    assert resultado.curva_de_capital.iloc[-1] == pytest.approx(121 / 100)


def test_entrar_custa_uma_vez():
    fechamento = _precos([100, 100, 100])
    resultado = executar_backtest(fechamento, _posicao([1, 1, 1], fechamento), 0.01)
    # preço parado: só sobra o custo da compra
    assert resultado.curva_de_capital.iloc[-1] == pytest.approx(0.99)
    assert resultado.giro == pytest.approx(1.0)


# --- NÃO olhar o futuro ------------------------------------------------------------


def test_a_decisao_de_hoje_so_rende_a_partir_de_amanha():
    # O preço sobe 10% nos dias 2 e 3 e cai 10% no dia 4. Decidir comprar no fim do dia 2
    # (índice 1) significa pegar a alta do dia 3 e não a do dia 2.
    fechamento = _precos([100, 110, 121, 108.9, 108.9])
    resultado = executar_backtest(
        fechamento, _posicao([0, 1, 0, 0, 0], fechamento), 0.0
    )
    assert list(resultado.posicao) == [0, 0, 1, 0, 0]
    assert list(resultado.retorno) == pytest.approx([0, 0, 0.10, 0, 0])
    assert resultado.curva_de_capital.iloc[-1] == pytest.approx(1.10)


def test_sinal_trapaceiro_que_usa_o_retorno_do_proprio_dia_nao_ganha_de_graca():
    # Um sinal "comprado se HOJE sobe" é trapaça. O motor adia a posição em 1 dia, então
    # ele só compra no dia seguinte e perde o ganho que "viu". Aqui o preço alterna
    # +10% / -10%: comprar depois de uma alta cai sempre na baixa seguinte.
    fechamento = _precos([100, 110, 99, 108.9, 98.01, 107.811])
    sobe_hoje = (fechamento.pct_change() > 0).astype(float)
    resultado = executar_backtest(fechamento, sobe_hoje, 0.0)
    assert resultado.curva_de_capital.iloc[-1] < 1.0


def test_primeiro_dia_nunca_tem_posicao():
    fechamento = _precos([100, 105, 110])
    resultado = executar_backtest(fechamento, _posicao([1, 1, 1], fechamento), 0.0)
    assert resultado.posicao.iloc[0] == 0


# --- custos e operações ---------------------------------------------------------------


def test_custo_de_entrada_e_de_saida():
    fechamento = _precos([100, 100, 110, 99, 99])
    resultado = executar_backtest(
        fechamento, _posicao([0, 1, 1, 0, 0], fechamento), 0.01
    )
    # posição: [0,0,1,1,0]; dia 3: +10% - 1% de entrada = 9%; dia 4: -10%; dia 5: -1% de saída
    assert list(resultado.retorno) == pytest.approx([0, 0, 0.09, -0.10, -0.01])
    assert resultado.curva_de_capital.iloc[-1] == pytest.approx(1.09 * 0.90 * 0.99)
    assert resultado.giro == pytest.approx(2.0)


def test_operacao_fechada_carrega_os_custos_de_entrada_e_saida():
    fechamento = _precos([100, 100, 110, 99, 99])
    resultado = executar_backtest(
        fechamento, _posicao([0, 1, 1, 0, 0], fechamento), 0.01
    )
    operacoes = resultado.operacoes
    assert len(operacoes) == 1
    linha = operacoes.iloc[0]
    assert linha["entrada"] == fechamento.index[2]
    assert linha["saida"] == fechamento.index[3]
    assert linha["dias"] == 2
    assert linha["retorno"] == pytest.approx(1.09 * 0.90 * 0.99 - 1)
    assert not linha["aberta"]


def test_operacao_ainda_aberta_no_fim_dos_dados():
    fechamento = _precos([100, 100, 110, 121, 121])
    resultado = executar_backtest(
        fechamento, _posicao([0, 1, 1, 1, 1], fechamento), 0.0
    )
    operacoes = resultado.operacoes
    assert len(operacoes) == 1
    assert bool(operacoes.iloc[0]["aberta"]) is True
    assert operacoes.iloc[0]["retorno"] == pytest.approx(1.10 * 1.10 - 1)  # +10% e +10%


def test_duas_operacoes_separadas():
    fechamento = _precos([100, 100, 110, 110, 100, 100, 110])
    resultado = executar_backtest(
        fechamento, _posicao([0, 1, 0, 0, 1, 0, 0], fechamento), 0.0
    )
    assert len(resultado.operacoes) == 2
    assert list(resultado.operacoes["dias"]) == [1, 1]


def test_sem_nenhuma_compra_nao_ha_operacoes():
    fechamento = _precos([100, 101, 102])
    resultado = executar_backtest(fechamento, _posicao([0, 0, 0], fechamento), 0.01)
    assert resultado.operacoes.empty
    assert list(resultado.operacoes.columns) == [
        "entrada",
        "saida",
        "dias",
        "retorno",
        "aberta",
    ]
    assert resultado.curva_de_capital.iloc[-1] == pytest.approx(1.0)


def test_posicao_parcial_rende_proporcionalmente():
    fechamento = _precos([100, 110, 121])
    resultado = executar_backtest(
        fechamento, _posicao([0.5, 0.5, 0.5], fechamento), 0.0
    )
    assert list(resultado.retorno) == pytest.approx([0, 0.05, 0.05])


# --- entradas inválidas -------------------------------------------------------------------


def test_custo_negativo():
    fechamento = _precos([100, 101])
    with pytest.raises(ValueError, match="custo"):
        executar_backtest(fechamento, _posicao([1, 1], fechamento), -0.01)


@pytest.mark.parametrize("posicao", [[1.5, 1], [-0.1, 1], [np.nan, 1]])
def test_posicao_fora_de_zero_a_um_ou_vazia(posicao):
    fechamento = _precos([100, 101])
    with pytest.raises(ValueError, match="entre 0 e 1"):
        executar_backtest(fechamento, _posicao(posicao, fechamento), 0.0)


def test_datas_diferentes():
    fechamento = _precos([100, 101])
    outra = pd.Series([1.0, 1.0], index=pd.date_range("2030-01-01", periods=2))
    with pytest.raises(ValueError, match="mesmas datas"):
        executar_backtest(fechamento, outra, 0.0)


def test_sem_precos():
    vazio = pd.Series([], dtype=float)
    with pytest.raises(ValueError, match="preços"):
        executar_backtest(vazio, vazio, 0.0)


# --- conferência cruzada: motor vetorizado x laço dia a dia ---------------------------


def _simulacao_dia_a_dia(fechamento, desejada, custo):
    """Versão lenta e ingênua, feita à mão, só para conferir o motor vetorizado."""
    capital = 1.0
    posicao_atual = 0.0
    decisao_de_ontem = 0.0
    curva = []
    for i in range(len(fechamento)):
        # a posição de hoje é a decisão de ontem
        nova = decisao_de_ontem
        retorno_do_ativo = (
            0.0 if i == 0 else fechamento.iloc[i] / fechamento.iloc[i - 1] - 1
        )
        capital *= 1 + nova * retorno_do_ativo - abs(nova - posicao_atual) * custo
        posicao_atual = nova
        decisao_de_ontem = desejada.iloc[i]
        curva.append(capital)
    return pd.Series(curva, index=fechamento.index)


@pytest.mark.parametrize("semente", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("custo", [0.0, 0.002])
def test_motor_vetorizado_igual_a_simulacao_dia_a_dia(semente, custo):
    rng = np.random.default_rng(semente)
    fechamento = _precos(50 * np.cumprod(1 + rng.normal(0.0005, 0.02, 120)))
    desejada = pd.Series(rng.choice([0.0, 0.5, 1.0], size=120), index=fechamento.index)
    vetorizado = executar_backtest(fechamento, desejada, custo).curva_de_capital
    lento = _simulacao_dia_a_dia(fechamento, desejada, custo)
    assert vetorizado.to_numpy() == pytest.approx(lento.to_numpy())
