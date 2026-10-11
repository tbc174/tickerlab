"""A página "Gerar relatório" dentro do app: gera, oferece o download e respeita o plano."""

from streamlit.testing.v1 import AppTest

from src.banco import dados_do_usuario as repo
from tests.ajudantes_da_conta import abrir_app, entrar_como, id_do_usuario, ir_para


def _app_local() -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    return ir_para(app, "relatorio")


def _baixar(app):
    return [b for b in app.get("download_button") if b.proto.label == "Baixar o PDF"]


def test_no_modo_local_gera_o_pdf_e_oferece_o_download():
    app = _app_local()
    assert not app.exception
    app.button(key="gerar_pdf").click().run()
    assert not app.exception and not app.error
    nome, pdf = app.session_state["pdf_pronto"]
    assert nome == "tickerlab-PETR4.SA.pdf" and pdf.startswith(b"%PDF")
    assert _baixar(app)


def test_atalho_da_visao_geral_abre_o_relatorio_do_ativo():
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.session_state["usar_exemplo"] = True
    app.run()
    ir_para(app, "visao_geral")
    app.button(key="atalho_relatorio_ativo").click().run()
    assert not app.exception
    assert app.session_state["tipo_de_relatorio"] == "ativo"
    assert any(b.key == "gerar_pdf" for b in app.button)  # já na página do relatório


def test_gratuito_nao_gera_backtest_e_ve_o_convite_do_pro(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app("relatorio")
    app.button_group(key="tipo_de_relatorio").set_value("backtest").run()
    assert not app.exception
    assert "faz parte do plano Pro" in " ".join(i.value for i in app.info)
    assert not any(b.key == "gerar_pdf" for b in app.button)


def test_gratuito_conta_o_uso_e_para_no_limite(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app("relatorio")
    app.button(key="gerar_pdf").click().run()
    assert not app.exception
    assert "1 de 3 relatórios" in " ".join(c.value for c in app.caption)
    with banco.begin() as conexao:
        ana = id_do_usuario(banco, "ana")
        for _ in range(2):
            repo.registrar_relatorio(conexao, ana, "ativo")
    app.run()
    assert "3 de 3 relatórios" in " ".join(c.value for c in app.caption)
    assert app.button(key="gerar_pdf").disabled
