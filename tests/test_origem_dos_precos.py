"""Achados 5d e 5e do Codex: a origem dos preços (cache antigo ou exemplo) não se perde.

5d: o dólar que converte o ativo para reais pode vir do cache antigo; a tela precisa avisar.
5e: o PDF diz "Yahoo Finance" só quando os preços vieram mesmo do Yahoo, não do exemplo automático.
"""

from types import SimpleNamespace

import pandas as pd

from telas import comum
from telas.relatorios import estudio


def _precos(inicio, dias, origem=None, ate=None):
    datas = pd.bdate_range(inicio, periods=dias)
    tabela = pd.DataFrame({"Close": [10.0] * dias, "Volume": [1] * dias}, index=datas)
    if origem:
        tabela.attrs = {"origem": origem, "ate": ate}
    return tabela


def _usar_precos(monkeypatch, por_ticker):
    monkeypatch.setattr(
        comum,
        "_carregar_dados_em_cache",
        lambda ticker, periodo, exemplo: por_ticker[ticker],
    )
    monkeypatch.setattr(comum.st, "session_state", {"usar_exemplo": False})


def test_dolar_do_cache_antigo_fica_marcado_na_conversao(monkeypatch):
    _usar_precos(
        monkeypatch,
        {
            "AAPL": _precos("2026-01-01", 60),
            "USDBRL=X": _precos("2026-01-01", 50, "cache_antigo", "10/03/2026"),
        },
    )
    dados = comum.carregar_dados_de("AAPL", "1y", True)
    assert dados.attrs["moeda"] == "BRL"
    assert dados.attrs["cambio_ate"] == "10/03/2026"


def test_dolar_atualizado_nao_marca_nada(monkeypatch):
    _usar_precos(
        monkeypatch,
        {"AAPL": _precos("2026-01-01", 60), "USDBRL=X": _precos("2026-01-01", 60)},
    )
    assert "cambio_ate" not in comum.carregar_dados_de("AAPL", "1y", True).attrs


def test_aviso_do_dolar_guardado_diz_a_data():
    from src.analises import aviso_do_cambio

    assert "10/03/2026" in aviso_do_cambio("10/03/2026")


def test_relatorio_do_ativo_com_exemplo_automatico_nao_diz_yahoo(monkeypatch):
    monkeypatch.setattr(estudio.st, "session_state", {"usar_exemplo": False})
    vistos = []
    monkeypatch.setattr(
        estudio.relatorios,
        "relatorio_do_ativo",
        lambda ticker, dados, **opcoes: vistos.append(opcoes["exemplo"]) or b"",
    )
    c = SimpleNamespace(
        ticker="PETR4.SA",
        periodo="1y",
        taxa_livre_de_risco=0.1,
        dados=_precos("2026-01-01", 60, "exemplo", "31/03/2026"),  # o Yahoo falhou
    )
    pedido = estudio._montar_relatorio(estudio.relatorios.ATIVO, c)
    pedido.montar(None, None)
    assert vistos == [True]


def test_comparacao_com_um_ativo_de_exemplo_nao_diz_yahoo(monkeypatch):
    monkeypatch.setattr(estudio.st, "session_state", {"usar_exemplo": False})
    por_ticker = {
        "PETR4.SA": _precos("2026-01-01", 60),
        "^BVSP": _precos("2026-01-01", 60, "exemplo", "31/03/2026"),
    }
    monkeypatch.setattr(estudio, "carregar_dados", lambda t, p: por_ticker[t])
    monkeypatch.setattr(estudio.st, "text_input", lambda *a, **k: "^BVSP")
    vistos = []
    monkeypatch.setattr(
        estudio.relatorios,
        "relatorio_de_comparacao",
        lambda tabela, **opcoes: vistos.append(opcoes["exemplo"]) or b"",
    )
    c = SimpleNamespace(
        ticker="PETR4.SA", periodo="1y", taxa_livre_de_risco=0.1, dados=None
    )
    pedido = estudio._montar_relatorio(estudio.relatorios.COMPARACAO, c)
    pedido.montar(None, None)
    assert vistos == [True]
