"""Números no estilo brasileiro (src/formatos.py): a tela do Streamlit e o app em React usam o mesmo."""

import math

import pytest

from src import formatos


@pytest.mark.parametrize(
    ("valor", "com_sinal", "esperado"),
    [
        (0.1234, False, "12,34%"),
        (0.1234, True, "+12,34%"),
        (-0.05, True, "-5,00%"),
        (0.0, True, "+0,00%"),
        (12.5, False, "1250,00%"),
        (float("nan"), False, "—"),
        (None, True, "—"),
    ],
)
def test_formatar_pct(valor, com_sinal, esperado):
    assert formatos.formatar_pct(valor, com_sinal=com_sinal) == esperado


def test_formatar_decimal():
    assert formatos.formatar_decimal(1.2345) == "1,23"
    assert formatos.formatar_decimal(-0.5) == "-0,50"
    assert formatos.formatar_decimal(math.inf) == "—"
    assert formatos.formatar_decimal(None) == "—"


def test_casos_para_o_react_cobrem_os_empates_de_arredondamento():
    """O Python arredonda o empate exato para o par (12,125 → 12,12); o toFixed do JS, para cima."""
    casos = formatos.casos_de_formatacao()
    textos = {c["texto"] for c in casos}
    assert "12,12%" in textos and "—" in textos
    for caso in (c for c in casos if c["formato"] != "inteiro"):
        funcao = (
            formatos.formatar_pct
            if caso["formato"] != "decimal"
            else formatos.formatar_decimal
        )
        argumentos = {"com_sinal": True} if caso["formato"] == "pct_com_sinal" else {}
        assert funcao(caso["valor"], **argumentos) == caso["texto"]
    inteiros = {c["valor"]: c["texto"] for c in casos if c["formato"] == "inteiro"}
    assert inteiros[123.456789] == "123" and inteiros[None] == "—"


def test_formato_de_cada_metrica_do_backtest():
    assert formatos.formato_da_metrica("Retorno total") == "pct_com_sinal"
    assert formatos.formato_da_metrica("Maior queda") == "pct"
    assert formatos.formato_da_metrica("Operações") == "inteiro"
    assert (
        formatos.formato_da_metrica("Índice de Sharpe") == "decimal"
    )  # o resto: duas casas
    assert formatos.formatar(12.0, "inteiro") == "12"
    assert formatos.formatar(float("nan"), "inteiro") == "—"
    assert any(c["formato"] == "inteiro" for c in formatos.casos_de_formatacao())
