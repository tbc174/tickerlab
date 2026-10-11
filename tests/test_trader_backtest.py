"""Motor de backtest do trader: posição de -1 a +1, custos separados e swap."""

import numpy as np
import pandas as pd
import pytest

from src import backtest as backtest_do_app
from trader.backtest import Custos, executar_backtest, resumir, spread_relativo


def _precos(valores, inicio="2024-01-01", freq="D"):
    indice = pd.date_range(inicio, periods=len(valores), freq=freq)
    return pd.Series(valores, index=indice, dtype=float)


def _posicao(valores, precos):
    return pd.Series(valores, index=precos.index, dtype=float)


# --- regras de entrada ---------------------------------------------------------------------


def test_aceita_posicao_vendida_e_recusa_fora_do_limite():
    p = _precos([100, 101, 102])
    executar_backtest(p, _posicao([-1, 0, 1], p))
    with pytest.raises(ValueError, match="entre -1 e 1"):
        executar_backtest(p, _posicao([0, 1.5, 0], p))
    with pytest.raises(ValueError, match="entre -1 e 1"):
        executar_backtest(p, _posicao([0, -1.5, 0], p))
    executar_backtest(p, _posicao([0, 2, -2], p), limite=2)  # alavancagem de propósito


def test_recusa_entradas_invalidas():
    p = _precos([100, 101, 102])
    with pytest.raises(ValueError, match="mesmas datas"):
        executar_backtest(p, _posicao([0, 1, 0], p).iloc[:2])
    with pytest.raises(ValueError, match="vazios"):
        executar_backtest(p, _posicao([0, np.nan, 0], p))
    with pytest.raises(ValueError, match="Não há preços"):
        executar_backtest(p.iloc[0:0], p.iloc[0:0])
    with pytest.raises(ValueError, match="limite"):
        executar_backtest(p, _posicao([0, 0, 0], p), limite=0)
    with pytest.raises(ValueError, match="negativos"):
        Custos(spread=-0.1)
    with pytest.raises(ValueError, match="negativos"):
        Custos(comissao=-0.1)


# --- a regra de ouro -----------------------------------------------------------------------


def test_posicao_de_hoje_so_rende_amanha():
    p = _precos([100, 110, 99, 120])
    r = executar_backtest(p, _posicao([1, 1, 1, 1], p))
    assert r.retorno.iloc[0] == 0  # nada foi decidido antes do dia 0
    assert r.retorno.iloc[1] == pytest.approx(0.10)  # a posição do dia 0 rende no dia 1
    assert r.posicao.iloc[0] == 0 and r.posicao.iloc[1] == 1


def test_a_decisao_do_ultimo_dia_nao_muda_nenhum_retorno():
    p = _precos([100, 105, 103, 108, 107])
    a = executar_backtest(p, _posicao([1, -1, 1, -1, 1], p))
    b = executar_backtest(p, _posicao([1, -1, 1, -1, -1], p))
    pd.testing.assert_series_equal(a.retorno, b.retorno)


# --- vendido -------------------------------------------------------------------------------


def test_vendido_ganha_quando_o_preco_cai_e_perde_quando_sobe():
    p = _precos([100, 90, 99])
    r = executar_backtest(p, _posicao([-1, -1, 0], p))
    assert r.retorno.iloc[1] == pytest.approx(0.10)
    assert r.retorno.iloc[2] == pytest.approx(-0.10)  # 90 -> 99 contra a venda


def test_perda_no_dia_nunca_passa_de_100_por_cento():
    p = _precos([100, 300, 100])
    r = executar_backtest(p, _posicao([-1, -1, -1], p))  # preço triplica contra a venda
    assert r.retorno.min() == -1.0
    assert r.curva_de_capital.min() >= 0


# --- custos --------------------------------------------------------------------------------


def test_sem_custos_igual_ao_motor_do_app_para_posicoes_de_0_a_1():
    rng = np.random.default_rng(1)
    p = _precos(100 * np.cumprod(1 + rng.normal(0, 0.01, 300)))
    pos = _posicao(rng.integers(0, 2, 300), p)
    app = backtest_do_app.executar_backtest(p, pos, custo_por_operacao=0.0005)
    novo = executar_backtest(p, pos, Custos(comissao=0.0005))
    pd.testing.assert_series_equal(novo.retorno, app.retorno)
    assert novo.giro == pytest.approx(app.giro)


def test_spread_ida_e_volta_custa_o_spread_inteiro():
    p = _precos([100, 100, 100, 100])
    r = executar_backtest(p, _posicao([1, 1, 0, 0], p), Custos(spread=0.002))
    assert r.custos.sum() == pytest.approx(0.002)
    assert r.custos.iloc[1] == pytest.approx(0.001)  # entrada: metade
    assert r.custos.iloc[3] == pytest.approx(0.001)  # saída: metade


def test_virar_de_comprado_para_vendido_paga_o_custo_em_dobro():
    p = _precos([100, 100, 100])
    r = executar_backtest(p, _posicao([1, -1, -1], p), Custos(comissao=0.001))
    assert r.custos.iloc[1] == pytest.approx(0.001)  # abriu a compra
    assert r.custos.iloc[2] == pytest.approx(0.002)  # fechou a compra e abriu a venda
    assert r.giro == pytest.approx(3.0)


def test_comissao_e_deslizamento_somam_por_lado():
    p = _precos([100, 100, 100])
    r = executar_backtest(
        p, _posicao([1, 0, 0], p), Custos(comissao=0.0003, deslizamento=0.0002)
    )
    assert r.custos.sum() == pytest.approx(2 * 0.0005)


def test_spread_pode_variar_por_dia():
    p = _precos([100, 100, 100, 100])
    spread = pd.Series([0.001, 0.001, 0.004, 0.004], index=p.index)
    r = executar_backtest(p, _posicao([1, 1, 0, 0], p), Custos(spread=spread))
    assert r.custos.iloc[1] == pytest.approx(0.0005)
    assert r.custos.iloc[3] == pytest.approx(0.002)


def test_custo_so_piora_o_resultado():
    rng = np.random.default_rng(2)
    p = _precos(100 * np.cumprod(1 + rng.normal(0.0003, 0.01, 400)))
    pos = _posicao(rng.integers(-1, 2, 400), p)
    sem = executar_backtest(p, pos).curva_de_capital.iloc[-1]
    com = executar_backtest(p, pos, Custos(spread=0.0002)).curva_de_capital.iloc[-1]
    assert com < sem


# --- swap ----------------------------------------------------------------------------------


def test_swap_corre_em_dias_corridos_e_pagar_reduz_o_retorno():
    # sexta -> segunda são 3 dias corridos
    indice = pd.to_datetime(["2024-01-05", "2024-01-08", "2024-01-09"])
    p = pd.Series([100.0, 100.0, 100.0], index=indice)
    r = executar_backtest(
        p,
        pd.Series([1.0, 1.0, 1.0], index=indice),
        Custos(swap_comprado_anual=-0.0365),
    )
    assert r.swap.iloc[1] == pytest.approx(-0.0365 * 3 / 365)
    assert r.swap.iloc[2] == pytest.approx(-0.0365 * 1 / 365)


def test_swap_vendido_tem_taxa_propria_e_pode_ser_recebido():
    p = _precos([100, 100, 100])
    r = executar_backtest(
        p,
        _posicao([-1, -1, -1], p),
        Custos(swap_comprado_anual=-0.10, swap_vendido_anual=0.0365),
    )
    assert r.swap.iloc[2] == pytest.approx(0.0365 / 365)
    assert r.swap.iloc[2] > 0  # recebeu


def test_sem_posicao_nao_paga_swap():
    p = _precos([100, 100, 100])
    r = executar_backtest(
        p,
        _posicao([0, 0, 0], p),
        Custos(swap_comprado_anual=-1, swap_vendido_anual=-1),
    )
    assert (r.swap == 0).all()


# --- operações -----------------------------------------------------------------------------


def test_operacoes_tem_lado_e_a_soma_fecha_com_a_curva():
    p = _precos([100, 102, 104, 101, 98, 99, 103, 100, 100, 100])
    pos = _posicao([1, 1, 0, 0, -1, -1, 0, 0, 0, 0], p)
    r = executar_backtest(p, pos, Custos(comissao=0.001))
    assert list(r.operacoes["lado"]) == [1, -1]
    assert not r.operacoes["aberta"].any()
    produto = (1 + r.operacoes["retorno"]).prod()
    assert produto == pytest.approx(r.curva_de_capital.iloc[-1])


def test_virada_de_lado_divide_o_custo_entre_as_duas_operacoes():
    p = _precos([100, 100, 100, 100, 100, 100])
    pos = _posicao([1, 1, -1, -1, 0, 0], p)
    r = executar_backtest(p, pos, Custos(comissao=0.01))
    assert list(r.operacoes["lado"]) == [1, -1]
    # preço parado: cada operação paga a entrada e a saída (1% + 1%), aproximadamente
    assert r.operacoes["retorno"].iloc[0] == pytest.approx(-0.02, abs=2e-4)
    assert r.operacoes["retorno"].iloc[1] == pytest.approx(-0.02, abs=2e-4)
    total = (1 + r.operacoes["retorno"]).prod()
    assert total == pytest.approx(r.curva_de_capital.iloc[-1], abs=2e-4)


def test_operacao_ainda_aberta_e_marcada():
    p = _precos([100, 101, 102, 103])
    r = executar_backtest(p, _posicao([-1, -1, -1, -1], p))
    assert len(r.operacoes) == 1 and bool(r.operacoes["aberta"].iloc[0])
    assert r.operacoes["lado"].iloc[0] == -1


def test_sem_nenhuma_posicao_nao_ha_operacoes():
    p = _precos([100, 101, 102])
    r = executar_backtest(p, _posicao([0, 0, 0], p))
    assert r.operacoes.empty and r.giro == 0


# --- spread do MT5 e resumo ----------------------------------------------------------------


def test_spread_relativo_converte_pontos_em_fracao_do_preco():
    candles = pd.DataFrame(
        {"Close": [1.1000, 1.2000], "Spread": [10, 20]}, index=_precos([0, 0]).index
    )
    s = spread_relativo(candles, 0.00001)
    assert s.iloc[0] == pytest.approx(10 * 0.00001 / 1.1)
    assert s.iloc[1] == pytest.approx(20 * 0.00001 / 1.2)
    with pytest.raises(ValueError, match="positivo"):
        spread_relativo(candles, 0)


def test_resumo_traz_metricas_do_app_e_as_do_trader():
    rng = np.random.default_rng(3)
    p = _precos(100 * np.cumprod(1 + rng.normal(0.0002, 0.01, 504)))
    pos = _posicao(rng.integers(-1, 2, 504), p)
    r = executar_backtest(p, pos, Custos(spread=0.0002, swap_comprado_anual=-0.02))
    resumo = resumir(r)
    for chave in ("Índice de Sharpe", "Maior queda", "Operações", "Exposição média"):
        assert chave in resumo
    assert resumo["Exposição média"] == pytest.approx(r.posicao.abs().mean())
    assert resumo["Giro por ano"] == pytest.approx(r.giro / 2, rel=0.01)
    assert resumo["Custos por ano"] > 0


def test_retorno_do_ativo_dado_substitui_a_variacao_do_preco():
    p = _precos([18.0, -37.63, 10.0, 11.0])  # o pct_change explodiria
    seguro = pd.Series([0.0, 0.0, 0.0, 0.1], index=p.index)
    r = executar_backtest(p, _posicao([1, 1, 1, 1], p), retorno_do_ativo=seguro)
    assert r.retorno.tolist() == pytest.approx([0.0, 0.0, 0.0, 0.1])


def test_retorno_do_ativo_com_datas_diferentes_e_recusado():
    p = _precos([100, 101, 102])
    with pytest.raises(ValueError, match="mesmas datas"):
        executar_backtest(
            p, _posicao([0, 0, 0], p), retorno_do_ativo=pd.Series([0.0, 0.0])
        )


def test_sem_operacoes_da_o_mesmo_retorno_e_e_mais_leve():
    rng = np.random.default_rng(8)
    p = _precos(100 * np.cumprod(1 + rng.normal(0, 0.01, 500)))
    pos = _posicao(rng.integers(-1, 2, 500), p)
    com = executar_backtest(p, pos, Custos(spread=0.0002))
    sem = executar_backtest(p, pos, Custos(spread=0.0002), com_operacoes=False)
    pd.testing.assert_series_equal(com.retorno, sem.retorno)
    assert sem.operacoes.empty and not com.operacoes.empty
