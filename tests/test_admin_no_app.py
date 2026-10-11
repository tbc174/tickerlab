"""O painel de administração dentro do app: só para administradores, com mudanças auditadas."""

from src import auditoria
from src.banco.conexao import criar_engine  # noqa: F401
from src.banco.usuarios import buscar_por_id
from tests.ajudantes_da_conta import (
    abrir_app,
    entrar_como,
    id_do_usuario,
    ir_para,
)


def _urls_do_menu(app):
    return {i["url_pathname"] for i in app._registered_pages.values()}


def _virar_admin(monkeypatch, banco, sub, email):
    """Cria a conta e a promove no banco (como o `TICKERLAB_ADMINS` faria no primeiro login)."""
    entrar_como(monkeypatch, sub, email)
    abrir_app()
    from src.banco.usuarios import mudar_papel

    with banco.begin() as conexao:
        mudar_papel(conexao, id_do_usuario(banco, sub), "admin")


def test_usuario_comum_nao_ve_nem_abre_a_administracao(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app()
    assert "admin" not in _urls_do_menu(app)
    # mesmo sabendo o endereço, a página não existe para quem não é administrador
    assert not any(
        i.get("url_pathname") == "admin" for i in app._registered_pages.values()
    )


def test_administrador_ve_o_painel(banco, monkeypatch):
    _virar_admin(monkeypatch, banco, "chefe", "chefe@exemplo.com")
    app = abrir_app("admin")
    assert not app.exception
    assert "admin" in _urls_do_menu(app)
    metricas = {m.label: m.value for m in app.metric}
    assert metricas["Usuários"] == "1"
    assert metricas["Plano Pro"] == "0"
    assert len(app.dataframe) >= 1  # a lista de usuários


def test_administrador_muda_o_plano_de_alguem_e_fica_registrado(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    abrir_app()
    _virar_admin(monkeypatch, banco, "chefe", "chefe@exemplo.com")
    app = abrir_app("admin")
    ana = id_do_usuario(banco, "ana")
    app.selectbox(key="admin_alvo").select(ana).run()
    app.selectbox(key="admin_plano").select("pro").run()
    app.button(key="admin_aplicar_plano").click().run()
    assert not app.exception
    with banco.connect() as conexao:
        assert buscar_por_id(conexao, ana).plano == "pro"
        registro = auditoria.listar_recentes(conexao)[0]
    assert registro.acao == auditoria.ACAO_PLANO_ALTERADO
    assert registro.alvo_id == ana
    assert registro.detalhes == {"de": "gratuito", "para": "pro"}


def test_administrador_nao_se_rebaixa_pelo_painel(banco, monkeypatch):
    _virar_admin(monkeypatch, banco, "chefe", "chefe@exemplo.com")
    app = abrir_app("admin")
    chefe = id_do_usuario(banco, "chefe")
    app.selectbox(key="admin_alvo").select(chefe).run()
    app.selectbox(key="admin_papel").select("usuario").run()
    app.button(key="admin_aplicar_papel").click().run()
    assert not app.exception
    with banco.connect() as conexao:
        assert buscar_por_id(conexao, chefe).e_admin


def test_quem_perde_o_papel_no_banco_perde_o_acesso_na_hora(banco, monkeypatch):
    """A sessão guarda o papel de quando entrou; o painel confere de novo no banco."""
    _virar_admin(monkeypatch, banco, "chefe", "chefe@exemplo.com")
    app = abrir_app("admin")
    assert not app.error
    from src.banco.usuarios import mudar_papel

    with banco.begin() as conexao:
        mudar_papel(conexao, id_do_usuario(banco, "chefe"), "usuario")
    app.run()  # a sessão ainda acha que é admin
    assert not app.exception
    assert any("só para administradores" in e.value for e in app.error)


def test_a_pagina_de_administracao_nao_abre_no_modo_local():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file("../app.py", default_timeout=90)
    app.session_state["usar_exemplo"] = True
    app.run()
    assert "admin" not in _urls_do_menu(app)
    _ = ir_para  # (sem página a visitar: ela nem existe no menu)
