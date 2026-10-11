"""Os limites dos planos funcionando dentro do app."""

from src.banco import dados_do_usuario as repo
from src.banco.usuarios import mudar_plano
from tests.ajudantes_da_conta import (
    abrir_app,
    botao,
    entrar_como,
    id_do_usuario,
)


def _virar_pro(banco, sub):
    with banco.begin() as conexao:
        mudar_plano(conexao, id_do_usuario(banco, sub), "pro")


def _textos(app):
    return " ".join(i.value for i in app.info)


def test_gratuito_nao_ve_aprendizado_de_maquina_nem_pares(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app()
    assert not app.exception
    texto = _textos(app)
    assert "Aprendizado de máquina** faz parte do plano **Pro" in texto
    assert "Pairs trading** faz parte do plano **Pro" in texto


def test_pro_ve_os_recursos(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    abrir_app()
    _virar_pro(banco, "ana")
    app = abrir_app()
    assert not app.exception
    assert "faz parte do plano **Pro" not in _textos(app)


def test_plano_muda_no_meio_da_sessao_depois_de_um_minuto(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app()
    assert "faz parte do plano **Pro" in _textos(app)
    _virar_pro(banco, "ana")
    app.run()  # ainda dentro do minuto: segue no plano antigo
    assert "faz parte do plano **Pro" in _textos(app)
    app.session_state["usuario_em"] = 0  # como se já tivesse passado o minuto
    app.run()
    assert app.session_state["usuario"].plano == "pro"
    assert "faz parte do plano **Pro" not in _textos(app)


def test_gratuito_nao_passa_de_3_favoritos(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app()
    for ticker in ("AAPL", "VALE3.SA", "PETR4.SA", "ITUB4.SA"):
        app.text_input(key="ticker").input(ticker).run()
        botao(app, f"Favoritar {ticker}").click().run()
    assert len(app.session_state["favoritos"]) == 3
    assert "até 3" in app.session_state["erro_favorito"]
    with banco.connect() as conexao:
        assert len(repo.listar_favoritos(conexao, id_do_usuario(banco, "ana"))) == 3


def test_gratuito_guarda_5_simulacoes_e_o_pro_guarda_mais(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app()
    ana = id_do_usuario(banco, "ana")
    for i in range(5):
        app.text_input(key="salvar_nome_backtest").input(f"s{i}").run()
        app.button(key="salvar_backtest").click().run()
    with banco.connect() as conexao:
        assert repo.contar_simulacoes(conexao, ana) == 5
    app.text_input(key="salvar_nome_backtest").input("sexta").run()
    app.button(key="salvar_backtest").click().run()
    assert not app.exception
    with banco.connect() as conexao:
        assert repo.contar_simulacoes(conexao, ana) == 5  # a sexta foi barrada

    _virar_pro(banco, "ana")
    pro = abrir_app()
    pro.text_input(key="salvar_nome_backtest").input("sexta").run()
    pro.button(key="salvar_backtest").click().run()
    with banco.connect() as conexao:
        assert repo.contar_simulacoes(conexao, ana) == 6


def test_carteira_padrao_cabe_no_plano(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    gratuito = abrir_app()
    assert len(gratuito.text_input(key="carteira_ativos").value.split(",")) == 4
    _virar_pro(banco, "ana")
    pro = abrir_app()
    assert len(pro.text_input(key="carteira_ativos").value.split(",")) == 5


def test_carteira_do_gratuito_avisa_quando_passa_do_limite(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app()
    app.text_input(key="carteira_ativos").input(
        "PETR4, VALE3, ITUB4, WEGE3, ABEV3"
    ).run()
    assert not app.exception
    assert "aceita até 4 ativos" in _textos(app)


def test_modo_local_nao_tem_limites():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file("../app.py", default_timeout=90)
    app.session_state["usar_exemplo"] = True
    app.run()
    assert not app.exception
    assert "faz parte do plano **Pro" not in _textos(app)
