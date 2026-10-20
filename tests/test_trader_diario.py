"""Diário das operações simuladas: cada operação com a decisão, o motivo, o custo e a comparação."""

import numpy as np
import pandas as pd
import pytest

from trader import diario as dr
from trader.backtest import Custos, executar_backtest


def _serie(valores, inicio="2024-01-01"):
    indice = pd.date_range(inicio, periods=len(valores), freq="D")
    return pd.Series(valores, index=indice, dtype=float)


def _rodar(precos, posicao, custos=None, sinal=None):
    p = _serie(precos)
    pos = pd.Series(posicao, index=p.index, dtype=float)
    res = executar_backtest(p, pos, custos)
    sinal = pos if sinal is None else pd.Series(sinal, index=p.index, dtype=float)
    return p, res, dr.diario_de_operacoes(res, p.pct_change().fillna(0.0), sinal, "B1")


def test_entrada_no_fechamento_seguinte_a_decisao():
    p, _, d = _rodar([100, 102, 104, 101, 98, 99], [0, 1, 1, 0, 0, 0])
    assert d["decisao"].iloc[0] == p.index[1]  # decidiu no fim do dia 1
    assert (
        d["entrada"].iloc[0] == p.index[2]
    )  # rende a partir do dia 2 (o shift(1) do backtest)
    assert (d["decisao"] < d["entrada"]).all()


def test_motivo_e_o_sinal_da_decisao():
    sinal = [0.0, 0.8, 0.6, -0.1, 0.0, 0.0]
    _, _, d = _rodar([100, 102, 104, 101, 98, 99], [0, 1, 1, 0, 0, 0], sinal=sinal)
    assert d["sinal_na_decisao"].iloc[0] == pytest.approx(0.8)
    assert d["motivo"].iloc[0] == "B1: sinal +0.80 na decisão"


def test_sinal_ausente_na_decisao_fica_revisar():
    sinal = [0.0, np.nan, 0.6, 0.0, 0.0, 0.0]
    _, _, d = _rodar([100, 102, 104, 101, 98, 99], [0, 1, 1, 0, 0, 0], sinal=sinal)
    assert d["motivo"].iloc[0].startswith("REVISAR")


def test_colunas_de_retorno_batem_com_o_backtest():
    _, res, d = _rodar(
        [100, 102, 104, 101, 98, 99, 103, 100, 100, 100],
        [1, 1, 0, 0, -1, -1, 0, 0, 0, 0],
        Custos(comissao=0.001),
    )
    assert list(d["retorno"]) == pytest.approx(list(res.operacoes["retorno"]))
    assert list(d["lado"]) == [1, -1]


def test_custo_e_swap_das_operacoes_somam_o_total():
    _, res, d = _rodar(
        [100, 100, 101, 100, 100, 99, 100, 100],
        [1, 1, -1, -1, -0.5, 0, 0, 0],  # entra, vira de lado, muda de tamanho, sai
        Custos(comissao=0.01, swap_comprado_anual=-0.05, swap_vendido_anual=-0.03),
    )
    assert not d["aberta"].any()
    assert d["custo"].sum() == pytest.approx(res.custos.sum())
    assert d["swap"].sum() == pytest.approx(res.swap.sum())


def test_virada_de_lado_divide_o_custo_ao_meio():
    _, _, d = _rodar([100] * 6, [1, 1, -1, -1, 0, 0], Custos(comissao=0.01))
    # cada operação paga 1% de entrada e 1% de saída; a virada (2%) fica metade para cada uma
    assert list(d["custo"]) == pytest.approx([0.02, 0.02])


def test_comparacao_nas_mesmas_datas():
    """A comparação é ficar comprado no mesmo ativo exatamente nos dias da operação."""
    _, _, d = _rodar([100, 100, 110, 121, 121, 121], [0, 1, 1, 0, 0, 0])
    assert d["comprado_no_periodo"].iloc[0] == pytest.approx(121 / 100 - 1)
    vendido = _rodar([100, 100, 110, 121, 121, 121], [0, -1, -1, 0, 0, 0])[2]
    assert vendido["comprado_no_periodo"].iloc[0] == pytest.approx(121 / 100 - 1)
    assert vendido["retorno_bruto"].iloc[0] < 0


def test_operacao_aberta_fica_marcada_e_sem_custo_de_saida():
    _, _, d = _rodar([100, 101, 102, 103], [1, 1, 1, 1], Custos(comissao=0.01))
    assert bool(d["aberta"].iloc[0])
    assert d["custo"].iloc[0] == pytest.approx(0.01)  # só a entrada


def test_sem_operacoes_da_diario_vazio_com_as_colunas():
    _, _, d = _rodar([100, 101, 102], [0, 0, 0])
    assert d.empty
    assert list(d.columns) == dr.COLUNAS_DO_DIARIO


def test_resumo_avisa_janela_curta():
    _, _, d = _rodar([100, 102, 104, 101, 98, 99], [0, 1, 1, 0, 0, 0])
    resumo = dr.resumir_diario(d)
    assert resumo["fechadas"] == 1
    assert resumo["janela_curta"] is True
    assert "poucas operações" in resumo["aviso"]


def test_resumo_sem_aviso_com_operacoes_suficientes():
    n = dr.MINIMO_DE_OPERACOES_PARA_JULGAR
    posicao = [1, 1, 0, 0] * n
    precos = 100 + np.arange(len(posicao), dtype=float)
    _, _, d = _rodar(precos, posicao)
    resumo = dr.resumir_diario(d)
    assert resumo["fechadas"] >= n
    assert resumo["janela_curta"] is False
    assert resumo["aviso"] == ""
    assert 0.0 <= resumo["taxa_de_acerto"] <= 1.0


def test_markdown_do_diario():
    _, _, d = _rodar([100, 102, 104, 101, 98, 99], [0, 1, 1, 0, 0, 0])
    texto = dr.diario_em_markdown(d)
    assert "## Diário das operações simuladas" in texto
    assert "| 2024-01-02 | 2024-01-03 |" in texto
    assert "poucas operações" in texto
    assert "não é recomendação de investimento" in texto


@pytest.mark.parametrize("semente", range(20))
def test_custo_e_swap_somam_o_total_com_posicoes_aleatorias(semente):
    """Todo custo cai em alguma operação (entrada, troca de tamanho, virada ou saída), uma vez só."""
    rng = np.random.default_rng(semente)
    n = 60
    precos = 100 * np.cumprod(1 + rng.normal(0, 0.01, n))
    posicao = rng.choice([-1.0, -0.5, 0.0, 0.5, 1.0], size=n)
    custos = Custos(
        spread=0.0004,
        comissao=0.0002,
        swap_comprado_anual=-0.04,
        swap_vendido_anual=0.01,
    )
    _, res, d = _rodar(precos, posicao, custos)
    assert d["custo"].sum() == pytest.approx(res.custos.sum())
    assert d["swap"].sum() == pytest.approx(res.swap.sum())
    assert list(d["retorno"]) == pytest.approx(list(res.operacoes["retorno"]))
