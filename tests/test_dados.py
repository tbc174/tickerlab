"""Testes de src/dados.py. Rode com: python -m pytest"""

import pytest

from src.dados import normalizar_ticker


@pytest.mark.parametrize(
    ("digitado", "esperado"),
    [
        ("PETR4", "PETR4.SA"),  # B3 sem sufixo ganha .SA
        ("petr4", "PETR4.SA"),  # minúsculas viram maiúsculas
        ("  vale3  ", "VALE3.SA"),  # espaços nas pontas somem
        ("BOVA11", "BOVA11.SA"),  # B3 com dois números (ETF)
        ("PETR4.SA", "PETR4.SA"),  # já tem .SA: não duplica
        ("petr4.sa", "PETR4.SA"),  # .sa minúsculo também
        ("AAPL", "AAPL"),  # EUA: sem número, não mexe
        ("aapl", "AAPL"),  # EUA em minúsculas
        ("BRK-B", "BRK-B"),  # tem hífen: não mexe
        ("BTC-USD", "BTC-USD"),  # cripto: não mexe
        ("^BVSP", "^BVSP"),  # índice (^): não mexe
        ("^gspc", "^GSPC"),  # índice em minúsculas
        ("^N225", "^N225"),  # índice japonês: não mexe
        ("ABC12", "ABC12")
    ],
)
def test_normalizar_ticker(digitado, esperado):
    assert normalizar_ticker(digitado) == esperado

