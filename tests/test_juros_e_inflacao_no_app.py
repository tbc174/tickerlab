"""A página Juros e inflação dentro do app (modo local, banco de teste semeado)."""

from datetime import date

import pandas as pd
from streamlit.testing.v1 import AppTest

from src import juros_e_inflacao as ji
from src.banco import series as acervo
from tests.ajudantes_da_conta import ir_para

SEMEADAS = {
    ji.SELIC_META: (
        "Meta da Selic",
        "% ao ano",
        pd.Series([15.0], index=pd.to_datetime(["2026-10-10"])),
    ),
    ji.IPCA: (
        "IPCA",
        "% no mês",
        pd.Series(
            [0.5] * 12, index=pd.date_range(end="2026-09-01", periods=12, freq="MS")
        ),
    ),
    ji.FOCUS_IPCA: (
        "Focus IPCA",
        "%",
        pd.Series([4.8], index=pd.to_datetime(["2026-12-31"])),
    ),
}


def _semear(banco):
    with banco.begin() as conexao:
        for codigo, (nome, unidade, valores) in SEMEADAS.items():
            acervo.garantir_serie(
                conexao, acervo.SerieDoAcervo(codigo, nome, unidade, "mensal")
            )
            acervo.gravar(conexao, codigo, valores, date(2026, 10, 10))


def _sem_internet_para_o_cdi(monkeypatch):
    from src.cdi import CDIIndisponivelError

    def falhar(inicio, fim):
        raise CDIIndisponivelError("sem internet no teste")

    monkeypatch.setattr("telas.comum.baixar_cdi", falhar)


def _abrir_local():
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    return ir_para(app, "juros_e_inflacao")


def test_juros_e_inflacao_mostra_selic_ipca_e_focus(banco, monkeypatch):
    _semear(banco)
    _sem_internet_para_o_cdi(monkeypatch)
    app = _abrir_local()
    assert not app.exception
    rotulos = {m.label: m.value for m in app.metric}
    assert rotulos[ji.NOME_SELIC] == "15,00% ao ano"
    assert rotulos[ji.NOME_IPCA_12M] == "6,17%"
    textos = " ".join(m.value for m in app.markdown) + " ".join(
        c.value for c in app.caption
    )
    assert "Banco Central, SGS 432" in textos
    assert "O CDI não veio do Banco Central agora" in textos  # o aviso, sem quebrar
    assert any(
        "IPCA" in str(t.value) for t in app.dataframe
    )  # as expectativas do Focus


def test_sem_series_coletadas_explica_e_nao_quebra(banco, monkeypatch):
    _sem_internet_para_o_cdi(monkeypatch)
    app = _abrir_local()
    assert not app.exception
    assert "ainda não foram coletadas" in " ".join(i.value for i in app.info)
