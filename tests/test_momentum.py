"""Testes de src/momentum.py."""

import numpy as np
import pandas as pd
import pytest

from src.momentum import calcular_momentos, montar_tabela_de_momentum


def _serie(valores):
    return pd.Series(valores, index=pd.bdate_range("2021-01-04", periods=len(valores)))


def test_momentos_com_numeros_conferidos_a_mao():
    # sobe 1% ao dia, composto, por 300 dias
    serie = _serie(100 * 1.01 ** np.arange(300))
    m = calcular_momentos(serie)
    assert m["1 mês"] == pytest.approx(1.01**21 - 1)
    assert m["3 meses"] == pytest.approx(1.01**63 - 1)
    assert m["6 meses"] == pytest.approx(1.01**126 - 1)
    # 12-1: de 252 dias atrás até 21 dias atrás são 231 dias
    assert m["12-1 meses"] == pytest.approx(1.01**231 - 1)


def test_momentum_12_1_ignora_o_ultimo_mes():
    base = 100 * 1.001 ** np.arange(300)
    caiu_no_fim = base.copy()
    caiu_no_fim[-15:] *= 0.7  # queda forte só nas últimas semanas
    a, b = calcular_momentos(_serie(base)), calcular_momentos(_serie(caiu_no_fim))
    assert b["12-1 meses"] == pytest.approx(a["12-1 meses"])
    assert b["1 mês"] < a["1 mês"]


def test_zscore_alto_quando_o_preco_dispara_acima_da_media():
    valores = np.r_[np.full(299, 100.0), 120.0]
    valores = valores + np.random.default_rng(0).normal(0, 0.1, 300)
    assert calcular_momentos(_serie(valores))["Z-score (20 dias)"] > 3


def test_historico_curto_da_erro():
    with pytest.raises(ValueError, match="253"):
        calcular_momentos(_serie(np.linspace(100, 110, 100)))


def test_tabela_ordena_pelo_momentum_e_separa_quem_nao_tem_historico():
    fechamentos = {
        "FRACO": _serie(100 * 1.0005 ** np.arange(300)),
        "FORTE": _serie(100 * 1.003 ** np.arange(300)),
        "CURTO": _serie(np.linspace(100, 120, 50)),
    }
    tabela, sem = montar_tabela_de_momentum(fechamentos)
    assert list(tabela.index) == ["FORTE", "FRACO"]
    assert list(tabela["Posição"]) == [1, 2]
    assert sem == ["CURTO"]
    with pytest.raises(ValueError, match="Nenhum ativo"):
        montar_tabela_de_momentum({"CURTO": fechamentos["CURTO"]})
