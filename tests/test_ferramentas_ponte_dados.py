"""As curvas da ferramenta "Quanto daria?" (src/ferramentas/ponte_dados.py), sem rede: tudo mês a
mês; CDI, poupança, dólar e IPCA do arquivo de dados das ferramentas; Ibovespa e bitcoin do Yahoo
(o bitcoin vezes o dólar do BC do mesmo mês); o cache do dia."""

from datetime import date

import pandas as pd
import pytest
import requests

from src import dados as dados_de_mercado
from src.ferramentas import ponte_dados

ARQUIVO = {
    "cdi_mensal": {
        "meses": [["2025-01", 0.01], ["2025-02", 0.01]],
        "ultimo": "2025-02",
    },
    "poupanca_mensal": {
        "meses": [["2025-01", 0.005], ["2025-02", 0.005]],
        "ultimo": "2025-02",
    },
    "dolar_mensal": {
        "meses": [["2025-01", 5.0], ["2025-02", 6.0], ["2025-03", 5.5]],
        "ultimo": "2025-03",
    },
    "ipca": {"meses": [["2025-01", 0.01], ["2025-02", 0.02]], "ultimo": "2025-02"},
}


def test_curva_mensal_comeca_em_1_e_acumula_mes_a_mes():
    curva = ponte_dados.curva_mensal([["2025-01", 0.01], ["2025-02", 0.02]])
    assert list(curva.index) == list(
        pd.to_datetime(["2025-01-01", "2025-02-01", "2025-03-01"])
    )
    assert curva.to_numpy() == pytest.approx([1.0, 1.01, 1.01 * 1.02])


def test_curvas_do_banco_central_vem_do_arquivo():
    curvas = ponte_dados.curvas_do_banco_central(ARQUIVO)
    assert curvas["cdi"].iloc[-1] == pytest.approx(1.01 * 1.01)
    assert curvas["dolar"].to_numpy() == pytest.approx([5.0, 6.0, 5.5])
    assert (curvas["parado"] == 1).all()
    assert list(curvas["parado"].index) == list(curvas["cdi"].index)


def test_arquivo_sem_uma_parte_e_erro_claro_e_sem_o_dolar_ele_so_fica_de_fora():
    with pytest.raises(ponte_dados.CurvaIndisponivelError, match="cdi_mensal"):
        ponte_dados.curvas_do_banco_central(
            {k: v for k, v in ARQUIVO.items() if k != "cdi_mensal"}
        )
    sem_dolar = {k: v for k, v in ARQUIVO.items() if k != "dolar_mensal"}
    assert "dolar" not in ponte_dados.curvas_do_banco_central(sem_dolar)


def test_primeiro_pregao_de_cada_mes_datado_no_dia_1():
    fechamento = pd.Series(
        [10.0, 11.0, 20.0, 21.0],
        index=pd.to_datetime(["2025-01-02", "2025-01-03", "2025-02-03", "2025-02-04"]),
    )
    mensal = ponte_dados.primeiro_pregao_de_cada_mes(fechamento)
    assert list(mensal.index) == list(pd.to_datetime(["2025-01-01", "2025-02-01"]))
    assert mensal.to_numpy() == pytest.approx([10.0, 20.0])


def test_bitcoin_em_reais_pelo_dolar_do_mesmo_mes(monkeypatch):
    dias = pd.to_datetime(["2025-01-02", "2025-02-03", "2025-03-03"])
    btc = pd.DataFrame({"Close": [100.0, 100.0, 100.0]}, index=dias)
    monkeypatch.setattr(
        dados_de_mercado, "baixar_historico_completo", lambda ticker: btc
    )
    dolar = ponte_dados.niveis_mensais(ARQUIVO["dolar_mensal"]["meses"])
    curva = ponte_dados.curva_do_yahoo("bitcoin", dolar)
    assert curva.to_numpy() == pytest.approx([500, 600, 550])


def test_fator_do_ipca_do_mes_da_data_ate_o_ultimo_divulgado():
    meses = [["2025-01", 0.01], ["2025-02", 0.02], ["2025-03", 0.03]]
    assert ponte_dados.fator_do_ipca(date(2025, 2, 10), meses) == pytest.approx(
        1.02 * 1.03
    )
    assert ponte_dados.fator_do_ipca(date(2025, 4, 10), meses) == 1.0


def test_o_cache_guarda_o_do_dia_e_busca_de_novo_no_dia_seguinte():
    chamadas = []

    def fazer():
        chamadas.append(1)
        return pd.Series([1.0, 2.0])

    cache = ponte_dados.CacheDoDia()
    primeira = cache.obter("cdi", date(2026, 10, 15), fazer)
    assert cache.obter("cdi", date(2026, 10, 15), fazer) is primeira
    cache.obter("cdi", date(2026, 10, 16), fazer)
    assert len(chamadas) == 2


def test_falha_nao_fica_no_cache():
    tentativas = []

    def falha():
        tentativas.append(1)
        raise ponte_dados.CurvaIndisponivelError("fora do ar")

    cache = ponte_dados.CacheDoDia()
    for _ in range(2):
        with pytest.raises(ponte_dados.CurvaIndisponivelError):
            cache.obter("ibovespa", date(2026, 10, 15), falha)
    assert len(tentativas) == 2


def test_arquivo_fora_do_ar_e_erro_da_curva():
    def buscar(url, timeout=None):
        raise requests.ConnectionError("fora")

    with pytest.raises(ponte_dados.CurvaIndisponivelError):
        ponte_dados.baixar_arquivo(buscar)


def test_historico_completo_sem_resposta_do_yahoo_e_erro(monkeypatch):
    monkeypatch.setattr(
        dados_de_mercado, "_baixar_do_yahoo", lambda ticker, **pedido: None
    )
    with pytest.raises(dados_de_mercado.DadosIndisponiveisError):
        dados_de_mercado.baixar_historico_completo("^BVSP")


def test_a_curva_do_yahoo_comeca_no_plano_real(monkeypatch):
    # o ^BVSP do Yahoo começa em 1993, com números da hiperinflação: antes de jul/1994 fica de fora
    dias = pd.to_datetime(["1993-05-03", "1994-06-01", "1994-07-01", "1994-08-01"])
    ibov = pd.DataFrame({"Close": [5.0, 300.0, 4000.0, 4100.0]}, index=dias)
    monkeypatch.setattr(
        dados_de_mercado, "baixar_historico_completo", lambda ticker: ibov
    )
    curva = ponte_dados.curva_do_yahoo("ibovespa", pd.Series(dtype=float))
    assert curva.index[0] == pd.Timestamp("1994-07-01")
    assert curva.to_numpy() == pytest.approx([4000.0, 4100.0])


def test_falha_do_yahoo_vira_erro_da_curva_e_nao_fica_no_cache(monkeypatch):
    def sem_yahoo(ticker):
        raise dados_de_mercado.DadosIndisponiveisError("fora do ar")

    monkeypatch.setattr(dados_de_mercado, "baixar_historico_completo", sem_yahoo)
    monkeypatch.setattr(ponte_dados, "CACHE", ponte_dados.CacheDoDia())
    with pytest.raises(ponte_dados.CurvaIndisponivelError, match="ibovespa"):
        ponte_dados.obter_curva_do_yahoo(
            "ibovespa", date(2026, 10, 15), pd.Series(dtype=float)
        )
