"""Testes diretos de `src/series_mensais.py`: meses fechados, poupança em duas regras e dólar do 1º dia."""

from datetime import date

import pandas as pd

from src import bcb, series_mensais


def _serie(pares: list[tuple[str, float]]) -> pd.Series:
    return pd.Series(
        [valor for _, valor in pares], index=pd.to_datetime([d for d, _ in pares])
    )


def test_meses_fechados_ignora_mes_corrente_e_dias_fora_do_primeiro():
    serie = _serie(
        [
            ("2024-01-01", 1.0),
            ("2024-01-15", 9.0),
            ("2024-02-01", 2.0),
            ("2024-03-01", 3.0),
        ]
    )
    assert series_mensais.meses_fechados(serie, date(2024, 3, 10)) == [
        ["2024-01", 0.01],
        ["2024-02", 0.02],
    ]


def test_poupanca_usa_regra_antiga_ate_maio_e_nova_de_junho(monkeypatch):
    antiga = _serie([("2012-04-01", 0.6), ("2012-05-01", 0.5), ("2012-06-01", 9.9)])
    nova = _serie([("2012-05-01", 9.9), ("2012-06-01", 0.4), ("2012-07-01", 0.3)])

    def falso(serie: bcb.Serie, *_args, **_kwargs):
        return antiga if serie is series_mensais.POUPANCA_ANTIGA else nova

    monkeypatch.setattr(series_mensais.bcb, "baixar_sgs", falso)
    meses = series_mensais.poupanca_mensal(date(2012, 8, 5))
    assert [m[0] for m in meses] == ["2012-04", "2012-05", "2012-06", "2012-07"]
    assert [m[1] for m in meses] == [0.006, 0.005, 0.004, 0.003]


def test_dolar_mensal_fica_com_o_primeiro_valor_de_cada_mes(monkeypatch):
    serie = _serie([("2024-01-02", 4.9), ("2024-01-03", 5.0), ("2024-02-01", 5.1)])
    monkeypatch.setattr(series_mensais.bcb, "baixar_sgs", lambda *_a, **_k: serie)
    assert series_mensais.dolar_mensal(date(2024, 2, 20)) == [
        ["2024-01", 4.9],
        ["2024-02", 5.1],
    ]
