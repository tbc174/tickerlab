"""Testes de src/estilo.py: o CSS cobre o que o tema não cobre e só usa as cores da marca."""

import re

import pytest

from src import marca
from src.estilo import CSS_DO_APP


@pytest.mark.parametrize(
    "trecho",
    [
        '[data-testid="stMetric"]',  # cartões das métricas
        "tabular-nums",  # números alinhados
        ".stTabs",  # abas
        "hr {",  # divisórias
        marca.AZUL,  # azul da marca
        ".tl-olho",  # o grupo acima do título de cada página
        ".st-key-tl-numero-principal",  # o número principal de cada página
    ],
)
def test_css_estiliza_os_elementos_principais(trecho):
    assert trecho in CSS_DO_APP


def test_css_tem_chaves_balanceadas():
    # um erro de chave deixaria o navegador ignorar parte do estilo
    assert CSS_DO_APP.count("{") == CSS_DO_APP.count("}")


def test_css_so_usa_cores_da_marca():
    """Identidade aprovada em 11/10/2026: toda cor vem de src/marca.py.

    (A direção anterior proibia laranja e amarelo; a nova usa âmbar só para "atenção" e nas
    séries dos gráficos, e verde e vermelho só para alta e queda.)
    """
    da_marca = {
        v.lower()
        for v in vars(marca).values()
        if isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", v)
    }
    usadas = {c.lower() for c in re.findall(r"#[0-9a-fA-F]{6}\b", CSS_DO_APP)}
    assert usadas <= da_marca, usadas - da_marca
    assert "orange" not in CSS_DO_APP.lower() and "yellow" not in CSS_DO_APP.lower()
