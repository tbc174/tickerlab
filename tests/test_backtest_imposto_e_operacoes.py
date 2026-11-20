"""Backtest na tela: legenda do imposto e tabela de operações (funções da tela, com o Streamlit trocado)."""

from contextlib import nullcontext
from types import SimpleNamespace

import pandas as pd

from telas.estrategias import backtest


def _imposto(total: float, meses: pd.DataFrame):
    return {"Cruzamento de médias": SimpleNamespace(imposto_total=total, meses=meses)}


def _espiar_streamlit(monkeypatch):
    chamadas = {"caption": [], "expander": [], "dataframe": []}
    monkeypatch.setattr(backtest.st, "caption", chamadas["caption"].append)
    monkeypatch.setattr(
        backtest.st,
        "expander",
        lambda titulo: chamadas["expander"].append(titulo) or nullcontext(),
    )
    monkeypatch.setattr(
        backtest.st,
        "dataframe",
        lambda tabela, **_: chamadas["dataframe"].append(tabela),
    )
    return chamadas


def test_imposto_mostra_o_valor_em_reais_com_formato_brasileiro(monkeypatch):
    chamadas = _espiar_streamlit(monkeypatch)
    meses = pd.DataFrame({"Mês": ["2024-03"], "Imposto (R$)": [1234567.891]})

    backtest._mostrar_imposto("Cruzamento de médias", _imposto(1234567.891, meses))

    assert "R\\$ 1.234.567,89" in chamadas["caption"][0]
    assert "não é orientação tributária" in chamadas["caption"][0]


def test_imposto_com_meses_oferece_o_detalhe_formatado(monkeypatch):
    chamadas = _espiar_streamlit(monkeypatch)
    meses = pd.DataFrame({"Mês": ["2024-03"], "Imposto (R$)": [1500.5]})

    backtest._mostrar_imposto("Cruzamento de médias", _imposto(1500.5, meses))

    assert chamadas["expander"] == ["Ver o imposto mês a mês"]
    assert chamadas["dataframe"][0]["Imposto (R$)"].tolist() == ["1,500.50"]
    assert meses["Imposto (R$)"].tolist() == [1500.5]  # a tabela original não muda


def test_imposto_sem_meses_nao_abre_o_detalhe(monkeypatch):
    chamadas = _espiar_streamlit(monkeypatch)
    meses = pd.DataFrame({"Mês": [], "Imposto (R$)": []})

    backtest._mostrar_imposto("Cruzamento de médias", _imposto(0.0, meses))

    assert "R\\$ 0,00" in chamadas["caption"][0]
    assert chamadas["expander"] == []
    assert chamadas["dataframe"] == []


def test_tabela_de_operacoes_traduz_colunas_datas_e_em_aberto(monkeypatch):
    chamadas = _espiar_streamlit(monkeypatch)
    botoes = []
    monkeypatch.setattr(
        backtest.st, "download_button", lambda *args, **kw: botoes.append((args, kw))
    )
    operacoes = pd.DataFrame(
        {
            "entrada": pd.to_datetime(["2024-01-02", "2024-05-06"]),
            "saida": pd.to_datetime(["2024-03-04", "2024-06-07"]),
            "dias": [62, 32],
            "retorno": [0.1, -0.05],
            "aberta": [False, True],
        }
    )

    backtest._tabela_de_operacoes(SimpleNamespace(operacoes=operacoes))

    tabela = chamadas["dataframe"][0]
    assert list(tabela.columns) == [
        "Primeiro dia",
        "Último dia",
        "Dias",
        "Retorno",
        "Em aberto",
    ]
    assert tabela["Primeiro dia"].tolist() == ["02/01/2024", "06/05/2024"]
    assert tabela["Em aberto"].tolist() == ["não", "sim"]
    assert botoes[0][1]["file_name"] == "operacoes.csv"
    assert operacoes["entrada"].dtype.kind == "M"  # a tabela original não muda
