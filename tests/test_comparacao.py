"""Testes de src/comparacao.py: escolha dos ativos, alinhamento de datas e base 100."""

import numpy as np
import pandas as pd
import pytest

from src.comparacao import (
    COLUNAS_DA_TABELA,
    MAX_ATIVOS,
    alinhar_fechamentos,
    escolher_ativos,
    interpretar_tickers,
    montar_tabela_comparativa,
    rebasear_para_100,
)


def _serie(valores, datas):
    return pd.Series(valores, index=pd.to_datetime(datas), dtype=float)


# --- interpretar o que a pessoa digitou ------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("vale3, aapl", ["VALE3.SA", "AAPL"]),
        ("vale3;aapl  btc-usd", ["VALE3.SA", "AAPL", "BTC-USD"]),
        ("  petr4 , PETR4.SA ", ["PETR4.SA"]),  # repetido depois de normalizar
        ("^bvsp", ["^BVSP"]),
        ("", []),
        ("  ,, ; ", []),
        (None, []),
    ],
)
def test_interpretar_tickers(texto, esperado):
    assert interpretar_tickers(texto) == esperado


# --- escolher a lista final ----------------------------------------------------------


def test_principal_vem_primeiro_depois_atalhos_e_extras():
    usados, ignorados = escolher_ativos("petr4", ["^BVSP", "^GSPC"], "aapl")
    assert usados == ["PETR4.SA", "^BVSP", "^GSPC", "AAPL"]
    assert ignorados == []


def test_ativo_repetido_aparece_uma_vez():
    usados, _ = escolher_ativos("PETR4.SA", ["^BVSP"], "petr4, ^bvsp, vale3")
    assert usados == ["PETR4.SA", "^BVSP", "VALE3.SA"]


def test_o_que_passa_do_maximo_vai_para_os_ignorados():
    usados, ignorados = escolher_ativos("A1", [], "b2, c3, d4, e5, f6, g7")
    assert len(usados) == MAX_ATIVOS
    assert usados[0] == "A1"
    assert ignorados == ["F6", "G7"]


def test_principal_vazio_e_ignorado_sem_quebrar():
    usados, ignorados = escolher_ativos("", ["^BVSP"], "")
    assert usados == ["^BVSP"] and ignorados == []


# --- alinhar as datas (feriados diferentes) -------------------------------------------


def test_alinhamento_usa_so_os_dias_em_que_todos_tem_preco():
    # A B3 fechou no dia 2 (feriado) e a bolsa dos EUA fechou no dia 4.
    b3 = _serie(
        [10, 99, 12, 13], ["2026-07-01", "2026-07-03", "2026-07-06", "2026-07-07"]
    )
    eua = _serie(
        [100, 101, 103, 104], ["2026-07-01", "2026-07-02", "2026-07-06", "2026-07-07"]
    )
    alinhado, descartados = alinhar_fechamentos({"B3": b3, "EUA": eua})
    assert list(alinhado.index.strftime("%Y-%m-%d")) == [
        "2026-07-01",
        "2026-07-06",
        "2026-07-07",
    ]
    assert list(alinhado["B3"]) == [10, 12, 13]  # preços originais, nada inventado
    assert descartados == 2  # 3/7 (só B3) e 2/7 (só EUA)


def test_alinhamento_nao_preenche_buracos_com_o_ultimo_preco():
    a = _serie([1, 2, 3], ["2026-01-05", "2026-01-06", "2026-01-07"])
    b = _serie([10, 30], ["2026-01-05", "2026-01-07"])
    alinhado, _ = alinhar_fechamentos({"A": a, "B": b})
    assert len(alinhado) == 2 and not alinhado.isna().any().any()


def test_alinhamento_ignora_fuso_horario_e_hora():
    com_fuso = pd.Series(
        [1.0, 2.0],
        index=pd.to_datetime(["2026-01-05 03:00", "2026-01-06 03:00"]).tz_localize(
            "UTC"
        ),
    )
    simples = _serie([5, 6], ["2026-01-05", "2026-01-06"])
    alinhado, descartados = alinhar_fechamentos({"X": com_fuso, "Y": simples})
    assert len(alinhado) == 2 and descartados == 0


def test_alinhamento_com_datas_repetidas_e_vazios():
    a = pd.Series(
        [1.0, 2.0, np.nan, 4.0],
        index=pd.to_datetime(["2026-01-05", "2026-01-05", "2026-01-06", "2026-01-07"]),
    )
    b = _serie([1, 2, 3], ["2026-01-05", "2026-01-06", "2026-01-07"])
    alinhado, _ = alinhar_fechamentos({"A": a, "B": b})
    assert list(alinhado.index.strftime("%d")) == ["05", "07"]
    assert alinhado.loc["2026-01-05", "A"] == 2.0  # na data repetida, vale o último


def test_alinhamento_sem_dias_em_comum_devolve_tabela_vazia():
    a = _serie([1, 2], ["2026-01-05", "2026-01-06"])
    b = _serie([1, 2], ["2026-02-05", "2026-02-06"])
    alinhado, descartados = alinhar_fechamentos({"A": a, "B": b})
    assert alinhado.empty and descartados == 4


def test_alinhamento_sem_ativos():
    with pytest.raises(ValueError, match="Nenhum ativo"):
        alinhar_fechamentos({})


# --- base 100 ----------------------------------------------------------------------------


def test_base_100_comeca_todo_mundo_em_100():
    alinhado = pd.DataFrame(
        {"A": [10.0, 11.0, 9.0], "B": [200.0, 220.0, 400.0]},
        index=pd.date_range("2026-01-05", periods=3),
    )
    base = rebasear_para_100(alinhado)
    assert list(base.iloc[0]) == [100.0, 100.0]
    assert list(base["A"]) == pytest.approx([100.0, 110.0, 90.0])
    assert list(base["B"]) == pytest.approx([100.0, 110.0, 200.0])


def test_base_100_sem_dados():
    with pytest.raises(ValueError, match="em comum"):
        rebasear_para_100(pd.DataFrame())


# --- tabela comparativa -------------------------------------------------------------------


def test_tabela_comparativa_tem_uma_linha_por_ativo_e_as_colunas_combinadas():
    datas = pd.date_range("2026-01-05", periods=30, freq="B")
    alinhado = pd.DataFrame(
        {"SOBE": np.linspace(10, 20, 30), "OSCILA": [10.0, 12.0] * 15}, index=datas
    )
    tabela = montar_tabela_comparativa(alinhado)
    assert list(tabela.index) == ["SOBE", "OSCILA"]
    assert list(tabela.columns) == COLUNAS_DA_TABELA
    assert tabela.loc["SOBE", "Retorno total"] == pytest.approx(1.0)  # 10 -> 20
    assert tabela.loc["SOBE", "Maior queda"] == 0  # só sobe
    assert tabela.loc["OSCILA", "Maior queda"] == pytest.approx(
        10 / 12 - 1
    )  # de 12 para 10
    assert (
        tabela.loc["OSCILA", "Volatilidade anual"]
        > tabela.loc["SOBE", "Volatilidade anual"]
    )


def test_tabela_comparativa_sem_dados():
    tabela = montar_tabela_comparativa(pd.DataFrame())
    assert tabela.empty and list(tabela.columns) == COLUNAS_DA_TABELA
