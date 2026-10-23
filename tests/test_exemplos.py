"""Testes de src/exemplos.py e do plano B de src/dados.py."""

import logging

import pandas as pd
import pytest
import requests

from src import cdi
from src.dados import DadosIndisponiveisError, baixar_dados
from src.exemplos import COLUNAS, carregar_exemplo, tickers_de_exemplo

TICKERS_USADOS_NO_APP = [
    "PETR4.SA",
    "PETR3.SA",
    "VALE3.SA",
    "ITUB4.SA",
    "BBDC4.SA",
    "BBAS3.SA",
    "WEGE3.SA",
    "ABEV3.SA",
    "AAPL",
    "^BVSP",
    "^GSPC",
    "BTC-USD",
    "USDBRL=X",
]


def _sem_yahoo(monkeypatch):
    monkeypatch.setattr("src.dados.yf.download", lambda *a, **k: pd.DataFrame())


def test_os_exemplos_cobrem_os_tickers_que_o_app_sugere():
    assert set(TICKERS_USADOS_NO_APP) <= set(tickers_de_exemplo())


@pytest.mark.parametrize("ticker", TICKERS_USADOS_NO_APP)
def test_cada_exemplo_tem_5_anos_de_precos_validos(ticker):
    dados = carregar_exemplo(ticker, "5y")
    assert list(dados.columns) == COLUNAS
    assert len(dados) > 1200
    assert dados.index.is_monotonic_increasing and dados.index.is_unique
    assert (dados["Close"] > 0).all() and not dados["Close"].isna().any()
    assert (dados["High"] >= dados["Low"]).all()
    assert dados.attrs["origem"] == "exemplo"


def test_periodos_curtos_pegam_o_final_do_historico():
    cinco = carregar_exemplo("PETR4.SA", "5y")
    dois = carregar_exemplo("PETR4.SA", "2y")
    seis_meses = carregar_exemplo("PETR4.SA", "6mo")
    assert dois.index[-1] == cinco.index[-1] == seis_meses.index[-1]
    assert 450 < len(dois) < 520
    assert 110 < len(seis_meses) < 135
    assert dois.attrs["ate"] == cinco.index[-1].strftime("%d/%m/%Y")


def test_exemplo_inexistente_ou_periodo_estranho_devolve_none():
    assert carregar_exemplo("XXXX9.SA") is None
    assert carregar_exemplo("PETR4.SA", "10 anos") is None


def test_arquivo_ilegivel_devolve_none_e_registra_o_erro(tmp_path, caplog):
    (tmp_path / "RUIM.csv").write_text("isto,nao,e,preco\n1,2,3,4\n", encoding="utf-8")
    with caplog.at_level(logging.ERROR):
        assert carregar_exemplo("RUIM", "2y", pasta=tmp_path) is None
    assert "ilegível" in caplog.text


def test_yahoo_vazio_usa_o_exemplo_e_avisa(monkeypatch, caplog):
    _sem_yahoo(monkeypatch)
    with caplog.at_level(logging.WARNING):
        dados = baixar_dados("petr4", "1y")
    assert dados.attrs["origem"] == "exemplo"
    assert "usando dados de exemplo" in caplog.text


def test_erro_de_rede_do_yahoo_tambem_usa_o_exemplo(monkeypatch, caplog):
    def cai(*a, **k):
        raise ConnectionError("sem rede")

    monkeypatch.setattr("src.dados.yf.download", cai)
    with caplog.at_level(logging.WARNING):
        dados = baixar_dados("AAPL", "6mo")
    assert dados.attrs["origem"] == "exemplo"
    assert "sem rede" in caplog.text


def test_ticker_sem_exemplo_continua_dando_erro(monkeypatch):
    _sem_yahoo(monkeypatch)
    with pytest.raises(DadosIndisponiveisError, match="XXXX9"):
        baixar_dados("XXXX9")


def test_forcar_exemplo_nao_chama_o_yahoo(monkeypatch):
    def nao_deve_chamar(*a, **k):
        raise AssertionError("chamou o Yahoo")

    monkeypatch.setattr("src.dados.yf.download", nao_deve_chamar)
    assert baixar_dados("VALE3", "1y", forcar_exemplo=True).attrs["origem"] == "exemplo"
    with pytest.raises(DadosIndisponiveisError, match="exemplo"):
        baixar_dados("XXXX9", forcar_exemplo=True)


def test_dados_do_yahoo_nao_levam_a_marca_de_exemplo(monkeypatch):
    colunas = pd.MultiIndex.from_tuples(
        [("Close", "PETR4.SA")], names=["Price", "Ticker"]
    )
    tabela = pd.DataFrame(
        [[10.0], [11.0]], index=pd.date_range("2026-01-01", periods=2), columns=colunas
    )
    monkeypatch.setattr("src.dados.yf.download", lambda *a, **k: tabela)
    assert "origem" not in baixar_dados("PETR4.SA").attrs


def test_falha_do_banco_central_fica_no_log(monkeypatch, caplog):
    def cai(*a, **k):
        raise requests.ConnectionError("sem rede")

    monkeypatch.setattr("requests.get", cai)
    monkeypatch.setattr("src.bcb.esperar", lambda _: None)
    with caplog.at_level(logging.WARNING), pytest.raises(cdi.CDIIndisponivelError):
        cdi.baixar_cdi(pd.Timestamp("2026-01-01"), pd.Timestamp("2026-02-01"))
    assert "Banco Central" in caplog.text
