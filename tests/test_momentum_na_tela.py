"""Tela de Momentum (`telas/momentum.py`): os avisos de favoritos, de ativo sem dados e de histórico curto.

A regra do cálculo já tem teste em `tests/test_momentum.py`; aqui só o que a tela mostra.
"""

import pandas as pd
from streamlit.testing.v1 import AppTest

from src.dados import DadosIndisponiveisError
from telas import momentum

DIAS_SUFICIENTES = 300


def _tela():
    import os

    import streamlit as st

    from telas import momentum

    st.session_state["favoritos"] = os.environ.get("FAVORITOS_DO_TESTE", "").split()
    momentum.secao_momentum("PETR4.SA", "5y")


def _abrir(monkeypatch, dias=DIAS_SUFICIENTES, favoritos="", sem_dados=""):
    indice = pd.bdate_range("2024-01-01", periods=dias)

    def dados_de_teste(ticker, periodo):
        if ticker == sem_dados:
            raise DadosIndisponiveisError(ticker)
        return pd.DataFrame({"Close": [100.0 + i for i in range(dias)]}, index=indice)

    # a tela guarda `carregar_dados` pelo nome: troca onde ela usa
    monkeypatch.setattr(momentum, "carregar_dados", dados_de_teste)
    monkeypatch.setenv("FAVORITOS_DO_TESTE", favoritos)
    return AppTest.from_function(_tela, default_timeout=60).run()


def test_so_o_principal_pede_para_favoritar_e_ainda_mostra_a_tabela(monkeypatch):
    app = _abrir(monkeypatch)
    assert not app.exception
    assert any("Favorite alguns ativos" in i.value for i in app.info)
    assert len(app.dataframe) == 1


def test_favorito_sem_dados_e_nomeado_no_aviso_e_o_resto_segue(monkeypatch):
    app = _abrir(monkeypatch, favoritos="VALE3.SA", sem_dados="VALE3.SA")
    assert not app.exception
    assert [w.value for w in app.warning] == ["Não encontrei dados para: VALE3.SA."]
    assert len(app.dataframe) == 1


def test_historico_curto_em_todos_pede_periodo_maior(monkeypatch):
    app = _abrir(monkeypatch, dias=50)
    assert not app.exception
    assert any("Escolha o período de 2 ou 5 anos." in i.value for i in app.info)
    assert len(app.dataframe) == 0
