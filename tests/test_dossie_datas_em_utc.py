"""Dossiê: tabelas com a data em UTC (com fuso) contra `hoje` sem fuso não podem quebrar nem errar o dia.

Regressão: a comparação de coluna com fuso e `Timestamp` sem fuso levantava TypeError. As tabelas são de
mentira; o momento fica perto da meia-noite de UTC para o teste pegar erro de dia.
"""

import pandas as pd

from base import dossie

HOJE = pd.Timestamp("2026-06-30")
ANTES = "2026-03-01T23:30:00Z"  # já divulgado
DEPOIS = "2026-07-01T00:30:00Z"  # depois de `hoje`: não pode entrar


def _utc(*momentos: str) -> pd.Series:
    return pd.Series(pd.to_datetime(list(momentos), utc=True))


def test_pareceres_em_vigor_com_data_em_utc():
    pareceres = pd.DataFrame(
        {
            "referencia": ["2024", "2025"],
            "versao": [1, 1],
            "disponivel_em": _utc(ANTES, DEPOIS),
        }
    )
    em_vigor = dossie._pareceres_em_vigor(pareceres, HOJE)
    assert em_vigor["referencia"].tolist() == ["2024"]


def test_publicas_no_dia_com_data_em_utc():
    como_era = pd.DataFrame(
        {
            "documento": [dossie.DOCUMENTO_ANUAL] * 2,
            "grupo": ["con", "con"],
            "exercicio": [2024, 2025],
            "divulgado_em": _utc(ANTES, DEPOIS),
        }
    )
    publicas = dossie._publicas_no_dia(como_era, HOJE)
    assert publicas["exercicio"].tolist() == [2024]
    assert publicas["divulgado_em"].dt.tz is None


def test_trocas_recentes_com_data_em_utc():
    trocas = pd.DataFrame(
        {"conhecido_em": _utc(ANTES, DEPOIS), "efetiva_em": _utc(ANTES, DEPOIS)}
    )
    itens = dossie._trocas_recentes(trocas, HOJE)
    assert [i["valor"] for i in itens] == [
        1
    ]  # a troca conhecida depois de hoje fica fora


def test_entregues_com_data_em_utc():
    tabela = pd.DataFrame(
        {
            "conhecido_em": _utc(ANTES, DEPOIS),
            "referencia": ["a", "a"],
            "versao": [1, 2],
        }
    )
    entregues = dossie._entregues(tabela, HOJE)
    assert entregues["versao"].tolist() == [1]  # a versão 2 só saiu depois


def test_janela_de_12_meses_com_data_em_utc():
    datas = _utc("2025-06-29T23:30:00Z", "2025-06-30T00:30:00Z", DEPOIS)
    dentro = dossie._janela(datas, HOJE)
    assert dentro.tolist() == [False, True, False]
