"""A página Ranking dentro do app (modo local, dados de exemplo): a contagem de tentativas."""

from streamlit.testing.v1 import AppTest

from src.estrategias import ESTRATEGIAS
from tests.ajudantes_da_conta import ir_para


def _ranking_local() -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=180)
    app.session_state["usar_exemplo"] = True
    app.run()
    ir_para(app, "ranking")
    assert not app.exception
    return app


def _legendas(app) -> str:
    return " ".join(c.value for c in app.caption)


def test_ranking_conta_uma_tentativa_por_estrategia():
    app = _ranking_local()
    assert f"{len(ESTRATEGIAS)} tentativas contadas." in _legendas(app)
    assert app.dataframe


def test_ideias_ja_testadas_entram_na_contagem_de_tentativas():
    app = _ranking_local()
    app.number_input(key="ranking_extras").set_value(30).run()
    assert not app.exception
    assert f"{len(ESTRATEGIAS) + 30} tentativas contadas." in _legendas(app)
