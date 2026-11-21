"""Início: o botão sem escolha e a reabertura do tutorial (sem internet).

`tests/test_paginas_no_app.py` cobre o caminho feliz (ativo escolhido na lista); aqui ficam
os dois caminhos em que nada deve acontecer ou o tutorial volta.
"""

from streamlit.testing.v1 import AppTest


def _inicio() -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    return app.run()


def test_analisar_sem_escolher_nada_fica_no_inicio():
    app = _inicio()
    antes = app.session_state["ticker"]
    app.button(key="comecar").click().run()
    assert not app.exception
    assert app.session_state["ticker"] == antes
    assert not app.session_state.get("ir_para_visao_geral")
    assert "escolheu_ativo" not in app.session_state.get("tutorial_feitos", set())
    assert [s.key for s in app.selectbox] == ["ativo_do_inicio"]  # segue no Início


def test_reabrir_o_tutorial_so_aparece_depois_de_visto_e_o_religa():
    app = _inicio()
    assert not [b for b in app.button if b.key == "tut_reabrir"]
    app.session_state["tutorial_visto"] = True
    app.run()
    app.button(key="tut_reabrir").click().run()
    assert not app.exception
    assert app.session_state["tutorial_visto"] is False
    assert not [b for b in app.button if b.key == "tut_reabrir"]
    assert app.button(key="tut_porta_analisar")  # as portas de entrada voltam
