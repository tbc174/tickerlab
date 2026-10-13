"""Calendário de eventos da rede do Bitcoin (série 1; exigência 5)."""

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from base.cripto.blocos import BLOCOS_POR_HALVING, emissao
from base.cripto.eventos import (
    EVENTOS,
    dias_que_nao_batem,
    saltos_nos_eventos,
    tabela_de_eventos,
)


def test_halvings_do_calendario_batem_com_a_regra_da_emissao():
    for evento in (e for e in EVENTOS if e.tipo == "halving"):
        assert evento.altura % BLOCOS_POR_HALVING == 0
        assert emissao(evento.altura) * 2 == emissao(evento.altura - 1)


def test_calendario_em_ordem_e_com_fonte():
    dias = [evento.dia for evento in EVENTOS]
    assert dias == sorted(dias)
    assert all(evento.fonte.startswith("https://") for evento in EVENTOS)
    assert len(tabela_de_eventos()) == len(EVENTOS)


def test_dia_do_evento_que_nao_bate_com_o_no_e_apontado():
    blocos = pd.DataFrame(
        {
            "altura": [210_000, 420_000],
            "hora": [
                datetime(2012, 11, 28, 15, tzinfo=UTC),
                datetime(2016, 7, 10, 1, tzinfo=UTC),
            ],
        }
    )

    problemas = dias_que_nao_batem(blocos)

    assert len(problemas) == 1
    assert "2º halving" in problemas[0]


def test_saltos_compara_o_dia_com_a_mediana_dos_7_anteriores():
    dia = date(2020, 5, 11)
    dias = [dia - timedelta(days=i) for i in range(7, -1, -1)]
    rede = pd.DataFrame(
        {
            "dia": dias,
            "n_transacoes": [100] * 7 + [300],
            "taxas_total": [10] * 8,
            "valor_movimentado": [5] * 8,
            "dias_moeda_destruidos": [1.0] * 8,
        }
    )

    saltos = saltos_nos_eventos(rede).set_index("metrica")

    assert saltos.loc["n_transacoes", "razao"] == pytest.approx(3.0)
    assert saltos.loc["taxas_total", "razao"] == pytest.approx(1.0)
    assert (saltos["evento"] == "3º halving: de 12,5 para 6,25 BTC").all()
