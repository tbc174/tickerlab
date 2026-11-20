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


def _abrir(
    monkeypatch,
    dias=DIAS_SUFICIENTES,
    favoritos="",
    sem_dados="",
    dias_de=None,
    salto=0.0,
):
    """`dias_de`: dias de histórico de um ticker específico; `salto`: pulo do último fechamento."""

    def dados_de_teste(ticker, periodo):
        if ticker == sem_dados:
            raise DadosIndisponiveisError(ticker)
        n = (dias_de or {}).get(ticker, dias)
        fechamento = [100.0 + i for i in range(n)]
        fechamento[-1] += salto
        return pd.DataFrame(
            {"Close": fechamento}, index=pd.bdate_range("2024-01-01", periods=n)
        )

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


def test_ativo_com_historico_curto_e_nomeado_e_o_resto_segue(monkeypatch):
    app = _abrir(monkeypatch, favoritos="VALE3.SA", dias_de={"VALE3.SA": 50})
    assert not app.exception
    legendas = [c.value for c in app.caption]
    assert any(
        "Sem histórico suficiente (menos de 1 ano): VALE3.SA." in c for c in legendas
    )
    assert len(app.dataframe) == 1
    assert list(app.dataframe[0].value.index) == ["PETR4.SA"]


def test_reversao_a_media_so_aparece_quando_marcada(monkeypatch):
    app = _abrir(monkeypatch, salto=100.0)
    assert "Z-score (20 dias)" not in app.dataframe[0].value.columns

    app.checkbox(key="momentum_reversao").check().run()

    assert not app.exception
    tabela = app.dataframe[0].value
    assert "Z-score (20 dias)" in tabela.columns
    assert tabela["Leitura da reversão"].tolist() == ["esticado para cima"]
    assert any("aposta que ele volta" in c.value for c in app.caption)
