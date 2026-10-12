"""Barras de 1 minuto e as conferências de qualidade."""

import pandas as pd
import pytest

from src.barras_intradiarias import (
    cobertura_por_simbolo,
    conferir_fechamentos,
    montar_barras,
)

FUSO_NY = "America/New_York"


def negocios(linhas: list[tuple[str, str, float, int]]) -> pd.DataFrame:
    tabela = pd.DataFrame(
        linhas, columns=["instante", "simbolo", "preco", "quantidade"]
    )
    tabela["instante"] = (
        pd.to_datetime(tabela["instante"], format="ISO8601")
        .dt.tz_localize(FUSO_NY)
        .dt.tz_convert("UTC")
    )
    return tabela


def test_barra_junta_os_negocios_do_mesmo_minuto():
    barras = montar_barras(
        negocios(
            [
                ("2026-10-09 09:30:01", "AAPL", 10.0, 100),
                ("2026-10-09 09:30:20", "AAPL", 12.0, 50),
                ("2026-10-09 09:30:40", "AAPL", 9.0, 10),
                ("2026-10-09 09:30:59.999", "AAPL", 11.0, 40),
            ]
        ),
        FUSO_NY,
    )
    assert len(barras) == 1
    barra = barras.iloc[0]
    assert barra["minuto"] == pd.Timestamp("2026-10-09 09:30")
    assert (
        barra["abertura"],
        barra["maxima"],
        barra["minima"],
        barra["fechamento"],
    ) == (10.0, 12.0, 9.0, 11.0)
    assert barra["volume"] == 200
    assert barra["negocios"] == 4


def test_abertura_e_fechamento_seguem_o_horario_mesmo_fora_de_ordem():
    barras = montar_barras(
        negocios(
            [
                ("2026-10-09 09:30:50", "AAPL", 2.0, 1),
                ("2026-10-09 09:30:10", "AAPL", 1.0, 1),
            ]
        ),
        FUSO_NY,
    )
    assert barras.iloc[0]["abertura"] == 1.0
    assert barras.iloc[0]["fechamento"] == 2.0


def test_minuto_seguinte_e_outro_simbolo_viram_barras_separadas():
    barras = montar_barras(
        negocios(
            [
                ("2026-10-09 09:30:59", "AAPL", 1.0, 1),
                ("2026-10-09 09:31:00", "AAPL", 2.0, 1),
                ("2026-10-09 09:30:30", "MSFT", 3.0, 1),
            ]
        ),
        FUSO_NY,
    )
    assert list(
        zip(barras["simbolo"], barras["minuto"].dt.strftime("%H:%M"), strict=True)
    ) == [
        ("AAPL", "09:30"),
        ("AAPL", "09:31"),
        ("MSFT", "09:30"),
    ]


def test_sem_negocios_devolve_tabela_vazia_com_as_colunas():
    vazio = pd.DataFrame(columns=["instante", "simbolo", "preco", "quantidade"])
    assert montar_barras(vazio, FUSO_NY).empty


def test_sem_olhar_o_futuro_cortar_o_dia_nao_muda_as_barras_anteriores():
    dia = negocios(
        [
            ("2026-10-09 09:30:10", "AAPL", 1.0, 1),
            ("2026-10-09 09:31:10", "AAPL", 2.0, 1),
            ("2026-10-09 09:32:10", "AAPL", 3.0, 1),
        ]
    )
    inteiro = montar_barras(dia, FUSO_NY)
    cortado = montar_barras(dia.iloc[:2], FUSO_NY)
    pd.testing.assert_frame_equal(inteiro.iloc[:2], cortado)


def test_cobertura_conta_minutos_com_barra():
    barras = montar_barras(
        negocios(
            [
                ("2026-10-09 09:30:00", "AAPL", 1.0, 1),
                ("2026-10-09 09:31:00", "AAPL", 1.0, 1),
            ]
        ),
        FUSO_NY,
    )
    assert cobertura_por_simbolo(barras, minutos_no_pregao=4)["AAPL"] == 0.5


def test_conferencia_compara_o_ultimo_preco_com_o_oficial():
    barras = montar_barras(
        negocios(
            [
                ("2026-10-09 15:59:58", "AAPL", 101.0, 1),
                ("2026-10-09 10:00:00", "AAPL", 90.0, 1),
            ]
        ),
        FUSO_NY,
    )
    tabela = conferir_fechamentos(barras, pd.Series({"AAPL": 100.0, "MSFT": 50.0}))
    assert list(tabela.index) == ["AAPL"]
    assert tabela.loc["AAPL", "diferenca"] == pytest.approx(0.01)
