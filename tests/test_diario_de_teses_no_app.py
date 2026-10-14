"""A página Diário de Teses dentro do app: login simulado e banco de teste."""

import pytest
from streamlit.testing.v1 import AppTest

from src import diario_de_teses as diario
from src.banco import dados_do_usuario as repo
from src.banco import teses as repo_teses
from src.banco.usuarios import entrar
from tests.ajudantes_da_conta import abrir_app, entrar_como, id_do_usuario, ir_para

TEXTO_HOSTIL = "**Comprei** pelo dividendo <b>alto</b> e $x$\n# não é título"


@pytest.fixture
def ana(banco, monkeypatch):
    entrar_como(monkeypatch, "g-ana", "ana@exemplo.com")
    app = abrir_app()
    return app, id_do_usuario(banco, "g-ana")


def _teses(banco, usuario_id):
    with banco.connect() as c:
        return repo_teses.listar(c, usuario_id)


def _escrever(app, ativo, texto, estrategias=()):
    app.text_input(key="diario_ativo").set_value(ativo).run()
    if estrategias:
        app.multiselect(key="diario_estrategias").set_value(list(estrategias)).run()
    app.text_area(key="diario_texto").set_value(texto).run()
    app.button(key="diario_guardar").click().run()


def test_sem_login_pede_para_entrar(banco):
    app = AppTest.from_file("../app.py", default_timeout=120)
    app.run()
    ir_para(app, "diario_de_teses")
    assert not app.exception
    assert "Entre com a sua conta" in " ".join(i.value for i in app.info)


def test_sem_anotacoes_explica_o_diario(banco, ana):
    app, _ = ana
    ir_para(app, "diario_de_teses")
    assert not app.exception and not app.error
    assert "Nenhuma anotação ainda" in " ".join(i.value for i in app.info)


def test_escrever_mostra_na_lista_como_texto_puro(banco, ana):
    app, ana_id = ana
    ir_para(app, "diario_de_teses")
    _escrever(app, "petr4", TEXTO_HOSTIL)
    assert not app.exception and not app.error
    (anotacao,) = _teses(banco, ana_id)
    assert anotacao.ticker == "PETR4.SA" and anotacao.texto == TEXTO_HOSTIL
    assert [t.value for t in app.text] == [
        TEXTO_HOSTIL
    ]  # st.text: sem Markdown nem HTML
    assert all("Comprei" not in m.value for m in app.markdown)
    assert (
        app.text_area(key="diario_texto").value == ""
    )  # o campo fica pronto para outra


def test_ligar_um_backtest_do_mesmo_ativo(banco, ana):
    app, ana_id = ana
    with banco.begin() as c:
        petr = repo.salvar_simulacao(
            c, ana_id, "backtest", "Cruzamento PETR4", {"ticker": "PETR4.SA"}, {}
        )
        repo.salvar_simulacao(
            c, ana_id, "backtest", "Cruzamento VALE3", {"ticker": "VALE3.SA"}, {}
        )
    ir_para(app, "diario_de_teses")
    app.text_input(key="diario_ativo").set_value("PETR4").run()
    assert app.multiselect(key="diario_estrategias").options == ["Cruzamento PETR4"]
    _escrever(app, "PETR4", "Tese com teste", [str(petr.id)])
    assert not app.exception and not app.error
    (anotacao,) = _teses(banco, ana_id)
    assert anotacao.estrategias == (petr.id,)
    assert "Cruzamento PETR4" in " ".join(c.value for c in app.caption)


def test_apagar_uma_anotacao(banco, ana):
    app, ana_id = ana
    with banco.begin() as c:
        anotacao = repo_teses.escrever(c, ana_id, "PETR4", "Para apagar")
    ir_para(app, "diario_de_teses")
    app.button(key=f"diario_apagar_{anotacao.id}").click().run()
    assert not app.exception
    assert _teses(banco, ana_id) == []


def test_limite_atingido_avisa_e_nao_guarda(banco, ana, monkeypatch):
    app, ana_id = ana
    monkeypatch.setattr(diario, "MAXIMO_DE_ANOTACOES", 1)
    with banco.begin() as c:
        repo_teses.escrever(c, ana_id, "PETR4", "A única")
    ir_para(app, "diario_de_teses")
    _escrever(app, "PETR4", "Mais uma")
    assert not app.exception
    assert len(_teses(banco, ana_id)) == 1
    assert "até 1 anotações" in " ".join(t.value for t in app.toast)


def test_nao_ve_o_diario_de_outra_conta(banco, ana):
    app, _ = ana
    with banco.begin() as c:
        bia = entrar(c, "g-bia", "bia@exemplo.com", "Bia")[0]
        repo_teses.escrever(c, bia.id, "PETR4", "Segredo da Bia")
    ir_para(app, "diario_de_teses")
    assert not app.exception
    assert "Segredo da Bia" not in " ".join(t.value for t in app.text)
