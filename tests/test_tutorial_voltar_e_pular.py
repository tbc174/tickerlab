"""Tutorial: os botões "Voltar" e "Pular tutorial" no meio do roteiro (só teste, sem internet).

`tests/test_tutorial.py` cobre o caminho até o fim; aqui ficam os dois botões que saem dele.
"""

from streamlit.testing.v1 import AppTest

from tests.ajudantes_da_conta import ir_para


def _botao(app: AppTest, chave: str):
    return next(b for b in app.button if b.key == chave)


def _no_segundo_passo() -> AppTest:
    """Abre o tutorial "analisar" e anda um passo (escolhe o ativo, vai à Visão geral e continua)."""
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    app.button(key="tut_porta_analisar").click().run()
    app.button_group(key="atalho_do_inicio").set_value("VALE3.SA").run()
    ir_para(app, "visao_geral")
    app.button(key="tut_seguir").click().run()
    assert not app.exception
    assert app.session_state["tutorial"]["passo"] == 1
    return app


def test_voltar_comeca_desligado_no_primeiro_passo():
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    app.button(key="tut_porta_analisar").click().run()
    assert app.session_state["tutorial"]["passo"] == 0
    assert _botao(app, "tut_voltar").disabled


def test_voltar_recua_um_passo_e_nunca_abaixo_de_zero():
    app = _no_segundo_passo()
    assert not _botao(app, "tut_voltar").disabled
    app.button(key="tut_voltar").click().run()
    assert not app.exception
    assert app.session_state["tutorial"]["passo"] == 0
    assert _botao(app, "tut_voltar").disabled


def test_pular_no_meio_encerra_o_tutorial_sem_toast_de_conclusao():
    app = _no_segundo_passo()
    app.button(key="tut_pular").click().run()
    assert not app.exception
    assert "tutorial" not in app.session_state
    assert app.session_state["tutorial_visto"] is True
    assert not any("Tutorial concluído" in t.value for t in app.toast)
