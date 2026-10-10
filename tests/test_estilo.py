"""Testes de src/estilo.py: confere que o CSS cobre os elementos que queremos estilizar."""

import pytest

from src.estilo import COR_AZUL, CSS_DO_APP


@pytest.mark.parametrize(
    "trecho",
    [
        "Manrope",  # fonte da direção visual
        '[data-testid="stMetric"]',  # cartões das métricas
        ".stTabs",  # abas
        "hr {",  # divisórias
        COR_AZUL,  # azul vivo do app
        "stIconMaterial",  # os ícones não podem perder a fonte de ícones
    ],
)
def test_css_estiliza_os_elementos_principais(trecho):
    assert trecho in CSS_DO_APP


def test_css_tem_chaves_balanceadas():
    # um erro de chave deixaria o navegador ignorar parte do estilo
    assert CSS_DO_APP.count("{") == CSS_DO_APP.count("}")


def test_css_nao_usa_laranja_nem_amarelo():
    # a direção visual proíbe laranja e amarelo; verde e vermelho só para alta e queda
    for cor in ("orange", "yellow", "#ff9800", "#ffeb3b"):
        assert cor not in CSS_DO_APP.lower()
