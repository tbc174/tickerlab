"""O app exige login quando o `[auth]` está configurado e não bloqueia no modo local."""

from streamlit import user_info
from streamlit.testing.v1 import AppTest

from src.banco.conexao import migrar_para
from tests.test_autenticacao import AUTH_COMPLETO


def _abrir_app() -> AppTest:
    return AppTest.from_file("../app.py", default_timeout=60)


def test_com_login_configurado_e_sem_entrar_mostra_so_a_tela_de_entrada():
    app = _abrir_app()
    app.secrets["auth"] = AUTH_COMPLETO
    app.run()
    assert not app.exception
    assert [b.label for b in app.button] == ["Entrar com o Google"]
    # nada do app de verdade aparece antes do login
    assert not app.get("unknown")
    assert not app.text_input


def test_com_login_o_usuario_e_criado_e_aparece_no_topo(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'contas.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    migrar_para("head", url=url)
    monkeypatch.setattr(
        user_info,
        "_get_user_info",
        lambda: {
            "is_logged_in": True,
            "sub": "123",
            "email": "ana@exemplo.com",
            "name": "Ana",
        },
    )
    app = _abrir_app()
    app.secrets["auth"] = AUTH_COMPLETO
    app.session_state["usar_exemplo"] = True
    app.run()
    assert not app.exception
    assert app.session_state["usuario"].email == "ana@exemplo.com"
    assert app.session_state["usuario"].plano == "gratuito"
    assert "Entrar com o Google" not in [b.label for b in app.button]
    # no primeiro acesso o app pede o aceite dos termos antes de abrir
    assert [b.label for b in app.button] == ["Continuar", "Sair"]
    app.checkbox(key="aceite_dos_termos").check().run()
    next(b for b in app.button if b.label == "Continuar").click().run()
    assert not app.exception
    assert "Analisar" in [b.label for b in app.button]  # o app abriu


def test_sem_login_configurado_o_app_abre_direto_no_modo_local():
    app = _abrir_app()
    app.session_state["usar_exemplo"] = True
    app.run()
    assert not app.exception
    assert "Analisar" in [b.label for b in app.button]
    assert "Entrar com o Google" not in [b.label for b in app.button]
    assert "usuario" not in app.session_state
