"""Ajudantes dos testes que abrem o app com um usuário logado (Google simulado)."""

from streamlit import user_info
from streamlit.testing.v1 import AppTest

from src.banco.usuarios import buscar_por_google_sub
from tests.test_autenticacao import AUTH_COMPLETO


def entrar_como(monkeypatch, sub, email):
    monkeypatch.setattr(
        user_info,
        "_get_user_info",
        lambda: {"is_logged_in": True, "sub": sub, "email": email, "name": sub},
    )


def abrir_app() -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=90)
    app.secrets["auth"] = AUTH_COMPLETO
    app.session_state["usar_exemplo"] = True
    return app.run()


def id_do_usuario(banco, sub):
    with banco.connect() as conexao:
        return buscar_por_google_sub(conexao, sub).id


def botao(app, rotulo):
    return next(b for b in app.button if b.label == rotulo)
