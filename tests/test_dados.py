"""Testes de src/dados.py. Rode com: python -m pytest"""

import pandas as pd
import pytest

from src.dados import DadosIndisponiveisError, baixar_dados, normalizar_ticker


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
        ("ABC12", "ABC12"),
    ],
)
def test_normalizar_ticker(digitado, esperado):
    assert normalizar_ticker(digitado) == esperado


# --- baixar_dados -------------------------------------------------------------
# Estes testes NÃO usam a internet: o `monkeypatch` troca o yf.download por uma
# função falsa que devolve o que quisermos. Assim o teste é rápido e sempre igual.


def _tabela_do_yahoo():
    """Imita o formato do Yahoo: colunas em dois níveis (preço e ticker)."""
    colunas = pd.MultiIndex.from_tuples(
        [("Close", "PETR4.SA"), ("Volume", "PETR4.SA")], names=["Price", "Ticker"]
    )
    indice = pd.date_range("2026-01-01", periods=2)
    return pd.DataFrame([[10.0, 100], [11.0, 200]], index=indice, columns=colunas)


def test_baixar_dados_devolve_colunas_simples(monkeypatch):
    monkeypatch.setattr("src.dados.yf.download", lambda *a, **k: _tabela_do_yahoo())
    dados = baixar_dados("PETR4.SA")
    assert list(dados.columns) == ["Close", "Volume"]


def test_baixar_dados_normaliza_o_ticker(monkeypatch):
    pedidos = []

    def falso(ticker, **kwargs):
        pedidos.append(ticker)
        return _tabela_do_yahoo()

    monkeypatch.setattr("src.dados.yf.download", falso)
    baixar_dados("  petr4 ")
    assert pedidos == ["PETR4.SA"]


@pytest.mark.parametrize("resposta", [pd.DataFrame(), None])
def test_baixar_dados_ticker_sem_dados(monkeypatch, resposta):
    monkeypatch.setattr("src.dados.yf.download", lambda *a, **k: resposta)
    with pytest.raises(DadosIndisponiveisError, match="XXXX9"):
        baixar_dados("XXXX9")


def test_baixar_dados_periodo_invalido():
    with pytest.raises(ValueError):
        baixar_dados("PETR4.SA", periodo="10 anos")


@pytest.mark.parametrize("vazio", ["", "   ", None])
def test_baixar_dados_ticker_vazio(vazio):
    with pytest.raises(DadosIndisponiveisError, match="Digite um ticker"):
        baixar_dados(vazio)
