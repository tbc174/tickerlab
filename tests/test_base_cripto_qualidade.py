"""Regras fixas de qualidade da base de cripto, C1 a C8 (série 1, PR 5).

Cada regra só aponta, nunca corrige nem apaga (como as regras da CVM em `base/regras.py`).
"""

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from base.cripto import qualidade
from base.cripto.qualidade import (
    c1_dias_faltando,
    c2_preco_impossivel,
    c3_salto,
    c4_volume_fora_do_padrao,
    c5_corretoras_divergem,
    c6_bloco_sem_metrica,
    c7_oferta_nao_bate,
    c8_semana_sem_cot,
    rodar,
)


def _precos(
    fechamentos: list[float], inicio: date = date(2024, 1, 1), **outras
) -> pd.DataFrame:
    dias = [inicio + timedelta(days=i) for i in range(len(fechamentos))]
    tabela = pd.DataFrame(
        {
            "dia": dias,
            "abertura": fechamentos,
            "maxima": [f * 1.01 for f in fechamentos],
            "minima": [f * 0.99 for f in fechamentos],
            "fechamento": fechamentos,
            "volume": [10.0] * len(fechamentos),
            "divulgado_em": [
                datetime(d.year, d.month, d.day, tzinfo=UTC) + timedelta(days=1)
                for d in dias
            ],
        }
    )
    for coluna, valores in outras.items():
        tabela[coluna] = valores
    return tabela


def test_c1_aponta_cada_dia_faltando():
    precos = _precos([100, 101, 102, 103]).drop(index=[1, 2])

    achados = c1_dias_faltando(precos, "kraken")

    assert [a.chave for a in achados] == ["2024-01-02", "2024-01-03"]
    assert achados[0].regra == "C1"
    assert achados[0].tabela == "kraken"


def test_c2_preco_zero_ou_maxima_abaixo_da_minima():
    precos = _precos([100, 0, 102])
    precos.loc[2, "maxima"] = 90.0  # máxima abaixo da mínima

    achados = c2_preco_impossivel(precos, "mb")

    assert [a.chave for a in achados] == ["2024-01-02", "2024-01-03"]


def test_c3_salto_de_mais_de_30_por_cento_num_dia():
    achados = c3_salto(_precos([100, 129, 200, 140]), "kraken")

    # 129 → 200 (+55%) e 200 → 140 (-30% fica no limite e não dispara)
    assert [a.chave for a in achados] == ["2024-01-03"]
    assert achados[0].valor == 200
    assert achados[0].valor_esperado == 129


def test_c4_volume_dez_vezes_a_mediana_dos_90_dias_anteriores():
    volumes = [10.0] * 95 + [101.0, 99.0]
    achados = c4_volume_fora_do_padrao(_precos([100.0] * 97, volume=volumes), "kraken")

    assert [a.chave for a in achados] == [
        (date(2024, 1, 1) + timedelta(days=95)).isoformat()
    ]


def test_c4_nao_olha_o_futuro():
    # o pico de volume no último dia não muda os achados dos dias anteriores
    volumes = [10.0] * 95 + [101.0]
    sem_o_ultimo = c4_volume_fora_do_padrao(
        _precos([100.0] * 95, volume=volumes[:95]), "x"
    )
    com_o_ultimo = c4_volume_fora_do_padrao(_precos([100.0] * 96, volume=volumes), "x")

    assert [a.chave for a in com_o_ultimo][: len(sem_o_ultimo)] == [
        a.chave for a in sem_o_ultimo
    ]


def test_c5_kraken_e_mercado_bitcoin_pela_ptax():
    kraken = _precos([100.0, 100.0, 100.0])
    mb = _precos([520.0, 510.0, 540.0])  # em reais
    ptax = pd.DataFrame(
        {"dia": [date(2024, 1, 1), date(2024, 1, 2)], "ptax": [5.0, 5.0]}
    )

    achados = c5_corretoras_divergem(kraken, mb, ptax)

    # dia 1: 520 / 500 = +4%; dia 2: +2% fica no limite; dia 3 usa a PTAX do dia 2: +8%
    assert [a.chave for a in achados] == ["2024-01-01", "2024-01-03"]
    assert achados[0].valor == pytest.approx(0.04)


def test_c6_bloco_sem_metrica():
    blocos = pd.DataFrame(
        {"altura": [1, 2], "taxas_total": [10, None], "valor_movimentado": [5, 5]}
    )

    achados = c6_bloco_sem_metrica(blocos)

    assert [a.chave for a in achados] == ["2"]


def test_c7_oferta_que_nao_bate_com_o_no():
    assert c7_oferta_nao_bate(0, 850_000) == []
    achado = c7_oferta_nao_bate(-100, 850_000)[0]
    assert achado.chave == "850000"
    assert achado.valor == -100


def test_c8_semana_sem_cot():
    cot = pd.DataFrame(
        {
            "relatorio": [date(2024, 1, 2), date(2024, 1, 9), date(2024, 1, 23)],
            "contrato": ["bitcoin"] * 3,
        }
    )

    achados = c8_semana_sem_cot(cot)

    assert [a.chave for a in achados] == ["bitcoin 2024-01-23"]


def test_rodar_deixa_de_fora_a_regra_quebrada_e_segue(monkeypatch):
    def quebra(*_):
        raise KeyError("coluna")

    monkeypatch.setattr(qualidade, "c3_salto", quebra)

    rodada = rodar(precos={"kraken": _precos([100, 0, 102])})

    assert "C3" in rodada.falhas
    assert any(a.regra == "C2" for a in rodada.achados)
