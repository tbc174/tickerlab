"""Testes de src/link.py."""

import pytest

from src.link import (
    MAX_FAVORITOS,
    alternar_favorito,
    ler_parametros,
    montar_parametros,
    ticker_valido,
)


def test_ida_e_volta_dos_parametros():
    parametros = montar_parametros(
        "PETR4.SA", "5y", "CDI (Banco Central)", True, False, ["VALE3.SA", "AAPL"]
    )
    assert parametros == {
        "ticker": "PETR4.SA",
        "periodo": "5y",
        "taxa": "CDI (Banco Central)",
        "reais": "1",
        "fav": "VALE3.SA,AAPL",
    }
    assert ler_parametros(parametros) == {
        "ticker": "PETR4.SA",
        "periodo": "5y",
        "taxa": "CDI (Banco Central)",
        "em_reais": True,
        "favoritos": ["VALE3.SA", "AAPL"],
    }


def test_caixas_desligadas_ficam_fora_da_url():
    parametros = montar_parametros("AAPL", "2y", "Zero", False, False, [])
    assert set(parametros) == {"ticker", "periodo", "taxa"}
    assert ler_parametros({**parametros, "exemplo": "1"})["usar_exemplo"] is True


def test_valores_estranhos_na_url_sao_ignorados():
    lidos = ler_parametros(
        {
            "ticker": "<script>alert(1)</script>",
            "periodo": "10y",
            "taxa": "Inventada",
            "reais": "talvez",
            "fav": "OK3.SA,<b>,AAPL,aapl,,../etc",
        }
    )
    assert lidos == {"favoritos": ["OK3.SA", "AAPL"]}


def test_ticker_vem_em_maiusculas_e_sem_espacos():
    assert ler_parametros({"ticker": " petr4.sa "}) == {"ticker": "PETR4.SA"}
    assert ler_parametros({}) == {}


def test_favoritos_da_url_tem_limite():
    muitos = ",".join(f"AAA{i}" for i in range(20))
    assert len(ler_parametros({"fav": muitos})["favoritos"]) == MAX_FAVORITOS


@pytest.mark.parametrize("texto", ["PETR4.SA", "^BVSP", "BTC-USD", "USDBRL=X", "AAPL"])
def test_tickers_validos(texto):
    assert ticker_valido(texto)


@pytest.mark.parametrize("texto", ["", "   ", "a b", "PETR4;DROP", "A" * 16, None])
def test_tickers_invalidos(texto):
    assert not ticker_valido(texto)


def test_alternar_favorito():
    assert alternar_favorito([], " aapl ") == ["AAPL"]
    assert alternar_favorito(["AAPL", "VALE3.SA"], "aapl") == ["VALE3.SA"]
    original = ["AAPL"]
    alternar_favorito(original, "VALE3.SA")
    assert original == ["AAPL"]  # não muda a lista recebida
    with pytest.raises(ValueError, match="válido"):
        alternar_favorito([], "a b")
    cheia = [f"AAA{i}" for i in range(MAX_FAVORITOS)]
    with pytest.raises(ValueError, match="limite"):
        alternar_favorito(cheia, "NOVO")
