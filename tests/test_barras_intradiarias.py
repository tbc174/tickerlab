"""Barras de 1 minuto e as conferências de qualidade."""

import pandas as pd
import pytest

from src.barras_intradiarias import (
    barras_parciais_b3,
    cobertura_por_simbolo,
    conferir_fechamentos,
    juntar_barras_b3,
    montar_barras,
    montar_barras_b3,
    selo_dos_fechamentos,
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


# --- B3: sessão do after, cancelamento e empate de hora (plano dos intradiários, PR 2) ----------

FUSO_SP = "America/Sao_Paulo"


def negocios_b3(
    linhas: list[tuple[str, str, float, int, int, int, bool]],
) -> pd.DataFrame:
    tabela = pd.DataFrame(
        linhas,
        columns=[
            "instante",
            "simbolo",
            "preco",
            "quantidade",
            "sessao",
            "identificador",
            "cancelado",
        ],
    )
    tabela["instante"] = pd.to_datetime(tabela["instante"]).dt.tz_localize(FUSO_SP)
    return tabela


def test_after_soma_a_parte_e_nao_mexe_nos_precos():
    barras = montar_barras_b3(
        negocios_b3(
            [
                ("2026-10-13 17:54:10", "PETR4", 30.0, 100, 1, 10, False),
                ("2026-10-13 17:54:50", "PETR4", 32.0, 200, 6, 20, False),
            ]
        )
    )
    barra = barras.iloc[0]
    assert (barra["abertura"], barra["maxima"], barra["fechamento"]) == (
        30.0,
        30.0,
        30.0,
    )
    assert (barra["volume"], barra["negocios"]) == (100, 1)
    assert (barra["volume_after"], barra["negocios_after"]) == (200, 1)


def test_minuto_so_com_after_fica_sem_preco():
    barras = montar_barras_b3(
        negocios_b3([("2026-10-13 18:30:00", "PETR4", 30.5, 300, 6, 40, False)])
    )
    barra = barras.iloc[0]
    assert pd.isna(barra["abertura"]) and pd.isna(barra["fechamento"])
    assert (barra["volume"], barra["volume_after"]) == (0, 300)


def test_cancelado_sai_junto_com_o_original():
    barras = montar_barras_b3(
        negocios_b3(
            [
                ("2026-10-13 10:43:00", "RADL3", 25.0, 5_000_000, 1, 30, False),
                ("2026-10-13 10:43:20", "RADL3", 26.0, 100, 1, 40, False),
                ("2026-10-13 16:56:00", "RADL3", 25.0, 5_000_000, 1, 30, True),
            ]
        )
    )
    assert barras["volume"].sum() == 100
    assert barras["abertura"].tolist() == [26.0]


def test_cancelamento_vale_so_para_o_mesmo_simbolo():
    """O identificador é por instrumento: o 30 do PETR4 não é o 30 do VALE3."""
    barras = montar_barras_b3(
        negocios_b3(
            [
                ("2026-10-13 10:00:00", "VALE3", 70.0, 100, 1, 30, False),
                ("2026-10-13 10:00:00", "PETR4", 30.0, 100, 1, 30, False),
                ("2026-10-13 11:00:00", "PETR4", 30.0, 100, 1, 30, True),
            ]
        )
    )
    assert barras["simbolo"].tolist() == ["VALE3"]


def test_empate_de_hora_resolvido_pelo_identificador():
    """Vários negócios no mesmo milésimo (uma ordem grande): o identificador diz a ordem."""
    barras = montar_barras_b3(
        negocios_b3(
            [
                ("2026-10-13 17:10:31.645", "PETR4", 48.6, 100, 1, 312420, False),
                ("2026-10-13 17:10:31.645", "PETR4", 48.4, 100, 1, 312410, False),
            ]
        )
    )
    barra = barras.iloc[0]
    assert (barra["abertura"], barra["fechamento"]) == (48.4, 48.6)


def test_barras_parciais_juntadas_iguais_as_de_uma_vez():
    negocios = negocios_b3(
        [
            ("2026-10-13 10:00:01", "PETR4", 30.0, 100, 1, 10, False),
            ("2026-10-13 10:00:30", "PETR4", 31.0, 100, 1, 20, False),
            ("2026-10-13 10:00:59", "PETR4", 29.0, 100, 1, 30, False),
            ("2026-10-13 18:30:00", "PETR4", 30.5, 50, 6, 40, False),
        ]
    )
    juntas = juntar_barras_b3(
        [
            barras_parciais_b3(negocios.iloc[[2, 3]]),
            barras_parciais_b3(negocios.iloc[[0, 1]]),
        ]
    )
    pd.testing.assert_frame_equal(juntas, montar_barras_b3(negocios))


# --- selo da IEX (plano dos intradiários grátis, PR 5) -----------------------------------------


def barras_da_iex(fechamentos: dict[str, float]) -> pd.DataFrame:
    linhas = [
        (f"2026-10-09 15:59:{segundo:02d}", simbolo, preco, 10)
        for segundo, (simbolo, preco) in enumerate(fechamentos.items())
    ]
    return montar_barras(negocios(linhas), FUSO_NY)


def test_fechamento_perto_do_oficial_confere():
    barras = barras_da_iex({"AAPL": 227.50})
    selo = selo_dos_fechamentos(barras, pd.Series({"AAPL": 227.55})).set_index(
        "simbolo"
    )
    assert selo.loc["AAPL", "selo"] == "confere"
    assert selo.loc["AAPL", "diferenca"] == pytest.approx(227.50 / 227.55 - 1)
    assert (
        "fechamento_oficial" not in selo.columns
    )  # o número do Yahoo não fica guardado


def test_fechamento_longe_do_oficial_nao_confere():
    """Pior caso medido em 13/10, 09/10 e 04/09/2026: 0,23%. Acima de 0,5% é outra coisa
    (desdobramento depois do dia, símbolo trocado, barras faltando)."""
    barras = barras_da_iex({"AAPL": 227.50})
    selo = selo_dos_fechamentos(barras, pd.Series({"AAPL": 455.0})).set_index("simbolo")
    assert selo.loc["AAPL", "selo"] == "nao_confere"


def test_selo_da_iex_ausente_e_sem_boletim():
    barras = barras_da_iex({"AAPL": 227.50})
    selo = selo_dos_fechamentos(barras, pd.Series({"MSFT": 500.0})).set_index("simbolo")
    assert selo.loc["AAPL", "selo"] == "sem_boletim"
    assert selo.loc["MSFT", "selo"] == "ausente"
    assert selo.loc["AAPL", "cobertura"] == pytest.approx(1 / 390)
