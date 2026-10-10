"""Testes de src/imposto.py, com preços pequenos para conferir de cabeça."""

import numpy as np
import pandas as pd
import pytest

from src.backtest import executar_backtest
from src.imposto import aplicar_imposto


def _backtest(precos, desejada, datas=None):
    indice = (
        datas
        if datas is not None
        else pd.bdate_range("2026-01-05", periods=len(precos))
    )
    fechamento = pd.Series(precos, index=indice, dtype=float)
    posicao = pd.Series(desejada, index=indice, dtype=float)
    return executar_backtest(fechamento, posicao, custo_por_operacao=0.0)


def test_lucro_grande_paga_quinze_por_cento():
    r = _backtest([100, 100, 200, 200, 200], [1, 1, 0, 0, 0])
    saida = aplicar_imposto(r, 100_000)
    assert saida.imposto_total == pytest.approx(15_000)
    assert 100_000 * saida.resultado.curva_de_capital.iloc[-1] == pytest.approx(185_000)


def test_vendas_ate_vinte_mil_no_mes_sao_isentas():
    r = _backtest([100, 100, 200, 200, 200], [1, 1, 0, 0, 0])
    saida = aplicar_imposto(r, 5_000)  # vende 10 mil
    assert saida.imposto_total == 0
    assert saida.resultado.retorno.equals(r.retorno)


def test_prejuizo_nao_paga_e_abate_o_lucro_do_mes_seguinte():
    datas = pd.to_datetime(
        [
            "2026-01-05",
            "2026-01-06",
            "2026-01-07",
            "2026-01-08",
            "2026-02-02",
            "2026-02-03",
            "2026-02-04",
            "2026-02-05",
        ]
    )
    # janeiro: dobra e cai pela metade; fevereiro: dobra de novo
    precos = [100, 100, 50, 50, 50, 50, 100, 100]
    desejada = [1, 1, 0, 0, 1, 1, 0, 0]
    r = _backtest(precos, desejada, datas)
    saida = aplicar_imposto(r, 100_000)
    meses = saida.meses.set_index("Mês")
    assert meses.loc["2026-01", "Imposto (R$)"] == 0
    assert meses.loc["2026-01", "Prejuízo a compensar (R$)"] == pytest.approx(50_000)
    # fevereiro: lucro de 50 mil menos o prejuízo de 50 mil = zero
    assert meses.loc["2026-02", "Imposto (R$)"] == pytest.approx(0)
    assert saida.imposto_total == pytest.approx(0)


def test_operacao_aberta_nao_paga_imposto():
    r = _backtest([100, 100, 200, 300, 400], [1, 1, 1, 1, 1])
    saida = aplicar_imposto(r, 100_000)
    assert saida.imposto_total == 0 and saida.meses.empty


def test_liquido_nunca_supera_o_bruto():
    rng = np.random.default_rng(1)
    precos = 100 * np.cumprod(1 + rng.normal(0.0005, 0.02, 500))
    desejada = (rng.random(500) > 0.5).astype(float)
    r = _backtest(precos, desejada)
    saida = aplicar_imposto(r, 500_000)
    assert saida.imposto_total >= 0
    assert (
        saida.resultado.curva_de_capital.iloc[-1] <= r.curva_de_capital.iloc[-1] + 1e-12
    )
    assert (saida.resultado.retorno <= r.retorno + 1e-12).all()


def test_o_original_nao_e_alterado():
    r = _backtest([100, 100, 200, 200, 200], [1, 1, 0, 0, 0])
    antes = r.retorno.copy()
    aplicar_imposto(r, 100_000)
    assert r.retorno.equals(antes)


def test_entradas_invalidas():
    r = _backtest([100, 100, 200, 200, 200], [1, 1, 0, 0, 0])
    with pytest.raises(ValueError, match="capital"):
        aplicar_imposto(r, 0)
    with pytest.raises(ValueError, match="alíquota"):
        aplicar_imposto(r, 1000, aliquota=1.5)
    with pytest.raises(ValueError, match="isenção"):
        aplicar_imposto(r, 1000, isencao_mensal=-1)
