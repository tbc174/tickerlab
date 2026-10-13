"""A página Backtest dentro do app (modo local, dados de exemplo): a validação fora da amostra."""

from streamlit.testing.v1 import AppTest

from tests.ajudantes_da_conta import ir_para

ESTRATEGIA = "Cruzamento de médias"


def _backtest_local() -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=180)
    app.session_state["usar_exemplo"] = True
    app.run()
    ir_para(app, "backtest")
    app.selectbox(key="backtest_estrategia").select(ESTRATEGIA).run()
    assert not app.exception
    return app


def _rotulos_das_metricas(app) -> list[str]:
    return [m.label for m in app.metric]


def test_walk_forward_com_janelas_curtas_mostra_o_sharpe_fora_da_amostra():
    app = _backtest_local()
    app.slider(key=f"validacao_treino_{ESTRATEGIA}").set_value(126).run()
    # cada janela precisa de pelo menos 30 dias (o controle anda de 21 em 21)
    app.slider(key=f"validacao_teste_{ESTRATEGIA}").set_value(42).run()
    assert not app.exception and not app.error
    rotulos = _rotulos_das_metricas(app)
    assert "Sharpe fora da amostra" in rotulos
    assert "Eficiência" in rotulos


def test_validacao_mostra_treino_e_teste_e_o_sharpe_deflacionado():
    app = _backtest_local()
    rotulos = _rotulos_das_metricas(app)
    assert "Sharpe da melhor, no treino" in rotulos
    assert "Tentativas contadas" in rotulos
