"""O ciclo da conta no app: favoritos e preferências que voltam, simulações salvas, reabertas e apagadas."""

import pytest
from streamlit import user_info
from streamlit.testing.v1 import AppTest

from src.banco import dados_do_usuario as repo
from src.banco.conexao import criar_engine, migrar_para
from src.banco.usuarios import buscar_por_google_sub
from tests.test_autenticacao import AUTH_COMPLETO


@pytest.fixture
def banco(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'conta.sqlite').as_posix()}"
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", url)
    migrar_para("head", url=url)
    motor = criar_engine(url)
    yield motor
    motor.dispose()


def _entrar_como(monkeypatch, sub, email):
    monkeypatch.setattr(
        user_info,
        "_get_user_info",
        lambda: {"is_logged_in": True, "sub": sub, "email": email, "name": sub},
    )


def _abrir_app() -> AppTest:
    app = AppTest.from_file("../app.py", default_timeout=90)
    app.secrets["auth"] = AUTH_COMPLETO
    app.session_state["usar_exemplo"] = True
    return app.run()


def _id_do_usuario(banco, sub):
    with banco.connect() as conexao:
        return buscar_por_google_sub(conexao, sub).id


def _botao(app, rotulo):
    return next(b for b in app.button if b.label == rotulo)


def test_favoritos_e_preferencias_voltam_na_proxima_sessao(banco, monkeypatch):
    _entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = _abrir_app()
    assert not app.exception
    _botao(app, "Favoritar PETR4.SA").click().run()
    app.selectbox(key="periodo").select("5y").run()
    ana = _id_do_usuario(banco, "ana")
    with banco.connect() as conexao:
        assert repo.listar_favoritos(conexao, ana) == ["PETR4.SA"]
        assert repo.carregar_preferencias(conexao, ana)["periodo"] == "5y"

    outra_sessao = _abrir_app()
    assert not outra_sessao.exception
    assert outra_sessao.session_state["favoritos"] == ["PETR4.SA"]
    assert outra_sessao.session_state["periodo"] == "5y"


def test_so_grava_quando_ha_mudanca(banco, monkeypatch):
    _entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = _abrir_app()
    app.run()  # outra execução sem mudar nada
    ana = _id_do_usuario(banco, "ana")
    with banco.connect() as conexao:
        assert repo.listar_favoritos(conexao, ana) == []
        assert repo.carregar_preferencias(conexao, ana) == {}


def test_link_compartilhado_nao_apaga_os_favoritos_da_conta(banco, monkeypatch):
    _entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    ana = _id_do_usuario_depois_de(banco, monkeypatch)
    with banco.begin() as conexao:
        repo.salvar_favoritos(conexao, ana, ["AAPL"])
    app = AppTest.from_file("../app.py", default_timeout=90)
    app.secrets["auth"] = AUTH_COMPLETO
    app.session_state["usar_exemplo"] = True
    app.query_params["fav"] = "VALE3.SA"
    app.run()
    assert not app.exception
    with banco.connect() as conexao:
        assert repo.listar_favoritos(conexao, ana) == ["AAPL"]


def _id_do_usuario_depois_de(banco, monkeypatch):
    _abrir_app()  # cria o usuário
    return _id_do_usuario(banco, "ana")


def test_salvar_reabrir_e_apagar_uma_simulacao(banco, monkeypatch):
    _entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = _abrir_app()
    app.selectbox(key="backtest_estrategia").select("Cruzamento de médias").run()
    app.text_input(key="salvar_nome_backtest").input("Meu cruzamento").run()
    app.button(key="salvar_backtest").click().run()
    assert not app.exception

    ana = _id_do_usuario(banco, "ana")
    with banco.connect() as conexao:
        salvas = repo.listar_simulacoes(conexao, ana)
    assert [s.nome for s in salvas] == ["Meu cruzamento"]
    assert salvas[0].parametros["backtest_estrategia"] == "Cruzamento de médias"
    assert "Retorno total" in salvas[0].resultado["numeros"]

    # outra sessão: a simulação aparece na lista e reabrir restaura os campos
    nova = _abrir_app()
    assert nova.session_state["backtest_estrategia"] != "Cruzamento de médias"
    nova.button(key=f"reabrir_{salvas[0].id}").click().run()
    assert not nova.exception
    assert nova.session_state["backtest_estrategia"] == "Cruzamento de médias"

    nova.button(key=f"apagar_{salvas[0].id}").click().run()
    assert not nova.exception
    with banco.connect() as conexao:
        assert repo.listar_simulacoes(conexao, ana) == []


def test_simulacao_de_outro_usuario_nao_aparece(banco, monkeypatch):
    _entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    ana_app = _abrir_app()
    ana_app.button(key="salvar_backtest").click().run()
    ana = _id_do_usuario(banco, "ana")
    with banco.connect() as conexao:
        da_ana = repo.listar_simulacoes(conexao, ana)[0]

    _entrar_como(monkeypatch, "bia", "bia@exemplo.com")
    bia_app = _abrir_app()
    assert not bia_app.exception
    chaves = [b.key for b in bia_app.button]
    assert f"reabrir_{da_ana.id}" not in chaves
    assert "Você ainda não salvou nenhuma simulação" in " ".join(
        i.value for i in bia_app.info
    )


def test_reabrir_ignora_estrategia_que_nao_existe_mais(banco, monkeypatch):
    _entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = _abrir_app()
    ana = _id_do_usuario(banco, "ana")
    with banco.begin() as conexao:
        simulacao = repo.salvar_simulacao(
            conexao,
            ana,
            "backtest",
            "Antiga",
            {"backtest_estrategia": "Extinta", "backtest_capital": 5000.0},
            {"numeros": {}},
        )
    app = _abrir_app()
    app.button(key=f"reabrir_{simulacao.id}").click().run()
    assert not app.exception
    assert app.session_state["backtest_estrategia"] != "Extinta"
    assert app.session_state["backtest_capital"] == 5000.0


def test_no_modo_local_a_aba_pede_login():
    app = AppTest.from_file("../app.py", default_timeout=90)
    app.session_state["usar_exemplo"] = True
    app.run()
    assert not app.exception
    assert any("Entre com a sua conta" in i.value for i in app.info)
