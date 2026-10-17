"""O ciclo da conta no app: favoritos e preferências que voltam, simulações salvas, reabertas e apagadas."""

from streamlit.testing.v1 import AppTest

from src import ficha
from src.banco import dados_do_usuario as repo
from src.dados import baixar_dados
from tests.ajudantes_da_conta import (
    abrir_app,
    botao,
    entrar_como,
    id_do_usuario,
    ir_para,
)
from tests.test_autenticacao import AUTH_COMPLETO


def test_favoritos_e_preferencias_voltam_na_proxima_sessao(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app("visao_geral")
    assert not app.exception
    botao(app, "Favoritar PETR4.SA").click().run()
    app.button_group(key="periodo").set_value("5y").run()
    ana = id_do_usuario(banco, "ana")
    with banco.connect() as conexao:
        assert repo.listar_favoritos(conexao, ana) == ["PETR4.SA"]
        assert repo.carregar_preferencias(conexao, ana)["periodo"] == "5y"

    outra_sessao = abrir_app()
    assert not outra_sessao.exception
    assert outra_sessao.session_state["favoritos"] == ["PETR4.SA"]
    assert outra_sessao.session_state["periodo"] == "5y"


def test_so_grava_quando_ha_mudanca(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app("visao_geral")
    app.run()  # outra execução sem mudar nada
    ana = id_do_usuario(banco, "ana")
    with banco.connect() as conexao:
        assert repo.listar_favoritos(conexao, ana) == []
        assert repo.carregar_preferencias(conexao, ana) == {}


def test_link_compartilhado_nao_apaga_os_favoritos_da_conta(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    abrir_app()  # cria o usuário
    ana = id_do_usuario(banco, "ana")
    with banco.begin() as conexao:
        repo.salvar_favoritos(conexao, ana, ["AAPL"])
    app = AppTest.from_file("../app.py", default_timeout=90)
    app.secrets["auth"] = AUTH_COMPLETO
    app.session_state["usar_exemplo"] = True
    app.query_params["fav"] = "VALE3.SA"
    app.run()
    ir_para(app, "visao_geral")
    assert not app.exception
    with banco.connect() as conexao:
        assert repo.listar_favoritos(conexao, ana) == ["AAPL"]


def test_campos_sobrevivem_a_troca_de_pagina(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app("visao_geral")
    app.selectbox(key="ticker").set_value("VALE3.SA").run()
    ir_para(app, "planos")
    ir_para(app, "backtest")
    assert app.session_state["ticker"] == "VALE3.SA"
    app.selectbox(key="backtest_estrategia").select("MACD").run()
    ir_para(app, "ranking")
    ir_para(app, "backtest")
    assert app.session_state["backtest_estrategia"] == "MACD"
    assert app.session_state["ticker"] == "VALE3.SA"


def test_backtest_salvo_guarda_o_pedido_e_o_veredito_da_ficha(banco, monkeypatch):
    """O Pulse recalcula a ficha das estratégias salvas: o pedido vai junto (PR E2)."""
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app("backtest")
    app.selectbox(key="backtest_estrategia").select("Cruzamento de médias").run()
    app.button(key="salvar_backtest").click().run()
    assert not app.exception

    with banco.connect() as conexao:
        (salva,) = repo.listar_simulacoes(conexao, id_do_usuario(banco, "ana"))
    guardada = salva.resultado["ficha"]
    dados = baixar_dados(salva.parametros["ticker"], salva.parametros["periodo"], True)
    pedido = ficha.pedido_guardado(guardada["pedido"], dados)
    assert pedido.estrategia == "Cruzamento de médias"
    assert guardada["veredito"] == (ficha.montar_ficha(pedido).veredito.resultado.value)


def test_salvar_reabrir_e_apagar_uma_simulacao(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app("backtest")
    app.selectbox(key="backtest_estrategia").select("Cruzamento de médias").run()
    app.text_input(key="salvar_nome_backtest").input("Meu cruzamento").run()
    app.button(key="salvar_backtest").click().run()
    assert not app.exception

    ana = id_do_usuario(banco, "ana")
    with banco.connect() as conexao:
        salvas = repo.listar_simulacoes(conexao, ana)
    assert [s.nome for s in salvas] == ["Meu cruzamento"]
    assert salvas[0].parametros["backtest_estrategia"] == "Cruzamento de médias"
    assert "Retorno total" in salvas[0].resultado["numeros"]

    # outra sessão: a simulação aparece na lista e reabrir restaura os campos
    nova = abrir_app("simulacoes")
    assert "backtest_estrategia" not in nova.session_state
    nova.button(key=f"reabrir_{salvas[0].id}").click().run()
    assert not nova.exception
    assert nova.session_state["backtest_estrategia"] == "Cruzamento de médias"
    # e a página do Backtest já abre com a estratégia reaberta
    ir_para(nova, "backtest")
    assert nova.selectbox(key="backtest_estrategia").value == "Cruzamento de médias"

    ir_para(nova, "simulacoes")
    nova.button(key=f"apagar_{salvas[0].id}").click().run()
    assert not nova.exception
    with banco.connect() as conexao:
        assert repo.listar_simulacoes(conexao, ana) == []


def test_simulacao_de_outro_usuario_nao_aparece(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    ana_app = abrir_app("backtest")
    ana_app.button(key="salvar_backtest").click().run()
    ana = id_do_usuario(banco, "ana")
    with banco.connect() as conexao:
        da_ana = repo.listar_simulacoes(conexao, ana)[0]

    entrar_como(monkeypatch, "bia", "bia@exemplo.com")
    bia_app = abrir_app("simulacoes")
    assert not bia_app.exception
    chaves = [b.key for b in bia_app.button]
    assert f"reabrir_{da_ana.id}" not in chaves
    assert "Você ainda não salvou nenhuma simulação" in " ".join(
        i.value for i in bia_app.info
    )


def test_reabrir_ignora_estrategia_que_nao_existe_mais(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    abrir_app()  # cria o usuário
    ana = id_do_usuario(banco, "ana")
    with banco.begin() as conexao:
        simulacao = repo.salvar_simulacao(
            conexao,
            ana,
            "backtest",
            "Antiga",
            {"backtest_estrategia": "Extinta", "backtest_capital": 5000.0},
            {"numeros": {}},
        )
    app = abrir_app("simulacoes")
    app.button(key=f"reabrir_{simulacao.id}").click().run()
    assert not app.exception
    assert "backtest_estrategia" not in app.session_state
    assert app.session_state["backtest_capital"] == 5000.0
    ir_para(app, "backtest")
    assert not app.exception


def test_no_modo_local_a_pagina_de_simulacoes_pede_login():
    app = AppTest.from_file("../app.py", default_timeout=90)
    app.session_state["usar_exemplo"] = True
    app.run()
    ir_para(app, "simulacoes")
    assert not app.exception
    assert any("Entre com a sua conta" in i.value for i in app.info)


def test_falha_ao_carregar_a_conta_nao_apaga_os_favoritos(banco, monkeypatch):
    """Achado 4c do Codex: se a 1ª leitura falha, favoritar depois não sobrescreve a lista guardada."""
    from telas import dados_da_conta

    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    abrir_app()
    ana = id_do_usuario(banco, "ana")
    with banco.begin() as conexao:
        repo.salvar_favoritos(conexao, ana, ["AAPL"])
    original = dados_da_conta.listar_favoritos
    chamadas = []

    def falha_na_primeira(conexao, usuario_id):
        chamadas.append(usuario_id)
        if len(chamadas) == 1:
            raise RuntimeError("banco fora do ar")
        return original(conexao, usuario_id)

    monkeypatch.setattr(dados_da_conta, "listar_favoritos", falha_na_primeira)
    app = abrir_app()  # a 1ª leitura falha: a conta não fica marcada como lida
    assert not app.exception
    assert app.session_state["favoritos"] == []
    with banco.connect() as conexao:
        assert repo.listar_favoritos(conexao, ana) == ["AAPL"]
    ir_para(app, "visao_geral")  # a próxima execução lê de novo, e a conta manda
    assert app.session_state["favoritos"] == ["AAPL"]
    botao(app, "Favoritar PETR4.SA").click().run()
    assert not app.exception
    with banco.connect() as conexao:
        assert repo.listar_favoritos(conexao, ana) == ["AAPL", "PETR4.SA"]
