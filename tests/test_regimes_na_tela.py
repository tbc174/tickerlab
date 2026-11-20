"""A página Fases do mercado dentro do app (modo local, dados de exemplo): as três abas."""

from streamlit.testing.v1 import AppTest

from tests.ajudantes_da_conta import ir_para


def _regimes_local() -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=180)
    app.session_state["usar_exemplo"] = True
    app.run()
    ir_para(app, "regimes")
    assert not app.exception
    return app


def _legendas(app) -> str:
    return " ".join(c.value for c in app.caption)


def test_pagina_abre_com_as_tres_abas():
    app = _regimes_local()
    assert [aba.label for aba in app.tabs] == [
        "Regimes do ativo",
        "Estratégia por regime",
        "Disjuntor de drawdown",
    ]
    assert "Regimes e disjuntor" in " ".join(s.value for s in app.subheader)


def test_aba_do_ativo_mostra_a_tabela_por_regime_de_volatilidade():
    app = _regimes_local()
    tabelas = [t.value for t in app.dataframe]
    assert tabelas
    resumo = tabelas[0]
    assert list(resumo.index) == ["Calmo", "Agitado"]
    assert "Volatilidade anual" in resumo.columns
    assert "contado no regime da véspera" in _legendas(app)


def test_trocar_para_tendencia_muda_os_regimes_da_tabela():
    app = _regimes_local()
    app.radio(key="reg_ativo_criterio").set_value("Tendência (alta × baixa)").run()
    assert not app.exception
    resumo = app.dataframe[0].value
    assert set(resumo.index) <= {"Alta", "Baixa"}
    assert "preço contra a média de 200 dias" in _legendas(app)


def test_aba_do_filtro_compara_a_estrategia_filtrada_com_a_original():
    app = _regimes_local()
    legendas = _legendas(app)
    assert "Regimes pelo critério: volatilidade de 20 dias" in legendas
    # a tabela de resultados da aba do filtro vem depois da do ativo
    resultados = app.dataframe[1].value
    assert any("só em calmo" in str(linha) for linha in resultados.index)


def test_aba_do_disjuntor_conta_os_disparos_e_mostra_a_varredura():
    app = _regimes_local()
    assert "travado em caixa" in _legendas(app)
    ultima = app.dataframe[-1].value
    assert "Disparos" in ultima.columns
    assert len(ultima) == 13
