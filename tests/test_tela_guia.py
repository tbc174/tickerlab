"""Tela do Guia: a busca do glossário e das estratégias filtra os verbetes e conta os achados."""

from streamlit.testing.v1 import AppTest

VERBETES = {
    "Sharpe": "Retorno por unidade de risco.",
    "Drawdown": "Maior queda desde o último topo.",
    "Beta": "Sensibilidade ao mercado.",
}


def _tela():
    from telas.guia import _lista_de_verbetes

    verbetes = {
        "Sharpe": "Retorno por unidade de risco.",
        "Drawdown": "Maior queda desde o último topo.",
        "Beta": "Sensibilidade ao mercado.",
    }
    _lista_de_verbetes(verbetes, "Buscar", "busca_teste")


def _abrir() -> AppTest:
    return AppTest.from_function(_tela, default_timeout=30).run()


def _legenda(app: AppTest) -> str:
    return app.caption[0].value


def test_sem_busca_mostra_todos_os_verbetes():
    app = _abrir()
    assert not app.exception
    assert _legenda(app) == f"{len(VERBETES)} de {len(VERBETES)} verbetes."
    assert [e.label for e in app.expander] == list(VERBETES)


def test_busca_acha_pelo_termo_sem_ligar_para_maiuscula():
    app = _abrir()
    app.text_input(key="busca_teste").set_value("  SHARPE ").run()
    assert [e.label for e in app.expander] == ["Sharpe"]
    assert _legenda(app) == "1 de 3 verbetes."


def test_busca_acha_pelo_texto_da_explicacao():
    app = _abrir()
    app.text_input(key="busca_teste").set_value("queda").run()
    assert [e.label for e in app.expander] == ["Drawdown"]


def test_busca_sem_resultado_zera_a_lista_sem_quebrar():
    app = _abrir()
    app.text_input(key="busca_teste").set_value("xyz inexistente").run()
    assert not app.exception
    assert not app.expander
    assert _legenda(app) == "0 de 3 verbetes."
