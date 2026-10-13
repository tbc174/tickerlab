"""Resumo diário da rede do Bitcoin (base de cripto, série 1, PR 2)."""

from datetime import date

import pandas as pd
import pytest

from base.cripto.diario import resumo_diario


def _blocos(horas: list[str], medianas: list[str]) -> pd.DataFrame:
    """Blocos nas alturas 0, 1, 2...; cada um com 1 transação, 10 de taxa e 100 movimentados."""
    n = len(horas)
    return pd.DataFrame(
        {
            "altura": range(n),
            "hora": pd.to_datetime(horas, utc=True, format="mixed"),
            "hora_mediana": pd.to_datetime(medianas, utc=True, format="mixed"),
            "n_transacoes": [1] * n,
            "taxas_total": [10] * n,
            "taxa_mediana_por_vbyte": [float(i) for i in range(n)],
            "valor_movimentado": [100] * n,
            "dias_moeda_destruidos": [0.5] * n,
            "emissao": [5] * n,
            "dificuldade": [float(i) for i in range(n)],
            "coletado_em": pd.to_datetime(["2026-10-13 12:00"] * n, utc=True),
        }
    )


def _parado(dias: list[date], fracoes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"dia": dias, "altura": range(len(dias)), "fracao_parada_1_ano": fracoes}
    )


# dia 01 com 3 blocos (um às 23:59:59), dia 02 com 9; a hora mediana passa da meia-noite do dia 01
# no bloco 4, e o dia 02 não fecha (a mediana nunca chega ao dia 03)
HORAS = [
    "2024-01-01 08:00",
    "2024-01-01 16:00",
    "2024-01-01 23:59:59",
    "2024-01-02 00:00",
    "2024-01-02 01:00",
    "2024-01-02 02:00",
    "2024-01-02 03:00",
    "2024-01-02 04:00",
    "2024-01-02 05:00",
    "2024-01-02 06:00",
    "2024-01-02 07:00",
    "2024-01-02 08:00",
]
MEDIANAS = [
    "2024-01-01 07:00",
    "2024-01-01 15:00",
    "2024-01-01 20:00",
    "2024-01-01 23:00",
    "2024-01-02 00:00",
    "2024-01-02 01:00",
    "2024-01-02 02:00",
    "2024-01-02 03:00",
    "2024-01-02 04:00",
    "2024-01-02 05:00",
    "2024-01-02 06:00",
    "2024-01-02 07:00",
]


def test_dia_utc_fecha_a_meia_noite():
    dias = resumo_diario(_blocos(HORAS, MEDIANAS), _parado([], []))

    assert dias["dia"].tolist() == [date(2024, 1, 1)]
    assert dias.iloc[0]["n_blocos"] == 3  # o bloco das 00:00 já é do dia 02


def test_dia_fechado_tem_divulgado_em_na_sexta_confirmacao():
    # o bloco 4 é o primeiro com a mediana na meia-noite; a 6ª confirmação dele é o bloco 9
    dias = resumo_diario(_blocos(HORAS, MEDIANAS), _parado([], []))

    assert dias.iloc[0]["divulgado_em"] == pd.Timestamp("2024-01-02 06:00", tz="UTC")


def test_dia_sem_6_confirmacoes_do_fechamento_fica_de_fora():
    # só até o bloco 8: o bloco 4 ainda tem 5 confirmações
    dias = resumo_diario(_blocos(HORAS[:9], MEDIANAS[:9]), _parado([], []))

    assert dias.empty


def test_bloco_com_hora_fora_de_ordem_fica_no_dia_da_propria_hora():
    horas = list(HORAS)
    # o bloco 3 vem depois do das 23:59:59, mas com hora 23:30 (válido: maior que a mediana, 23:00)
    horas[3] = "2024-01-01 23:30"

    dias = resumo_diario(_blocos(horas, MEDIANAS), _parado([], []))

    assert dias.iloc[0]["n_blocos"] == 4


def test_soma_mediana_e_ultimo_valor_do_dia():
    parado = _parado([date(2024, 1, 1)], [0.25])

    dia = resumo_diario(_blocos(HORAS, MEDIANAS), parado).iloc[0]

    assert dia["n_transacoes"] == 3
    assert dia["taxas_total"] == 30
    assert dia["valor_movimentado"] == 300
    assert dia["dias_moeda_destruidos"] == pytest.approx(1.5)
    assert dia["emissao"] == 15
    assert dia["taxa_mediana_por_vbyte"] == 1.0  # mediana de 0, 1 e 2
    assert dia["dificuldade"] == 2.0  # a do último bloco do dia
    assert dia["fracao_parada_1_ano"] == 0.25
    assert dia["coletado_em"] == pd.Timestamp("2026-10-13 12:00", tz="UTC")


def test_sem_blocos_devolve_tabela_vazia():
    assert resumo_diario(pd.DataFrame(), pd.DataFrame()).empty
