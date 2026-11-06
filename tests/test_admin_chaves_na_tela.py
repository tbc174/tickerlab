"""A tela das chaves da API no painel do admin (N7, linha 169): só admin, e a chave aparece uma vez."""

import logging

import sqlalchemy as sa

from src.banco.modelo import auditoria
from src.banco.usuarios import mudar_papel
from src.chaves_da_api import FORMATO, hash_da_chave
from tests.ajudantes_da_conta import abrir_app, entrar_como, id_do_usuario


def _entrar_como_admin(monkeypatch, banco):
    entrar_como(monkeypatch, "chefe", "chefe@exemplo.com")
    abrir_app()
    with banco.begin() as conexao:
        mudar_papel(conexao, id_do_usuario(banco, "chefe"), "admin")
    return abrir_app("admin")


def _criar_organizacao(app, nome="Alfa Gestora"):
    app.text_input(key="chaves_nome").set_value(nome)
    app.button(key="chaves_criar").click().run()
    assert not app.exception
    return app


def _valores_de_chave(app):
    return [c.value for c in app.code if FORMATO.fullmatch(c.value or "")]


def _estado_da_sessao(app):
    return str({chave: app.session_state[chave] for chave in app.session_state})


def _tudo_que_a_tela_mostra(app):
    elementos = (
        app.markdown,
        app.caption,
        app.success,
        app.warning,
        app.error,
        app.info,
        app.code,
        app.dataframe,
    )
    return " ".join(str(e.value) for lista in elementos for e in lista)


def test_usuario_comum_nao_ve_a_secao_de_chaves(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app()
    # a página do admin nem está no menu; a função recusa mesmo assim, chamada direto
    assert not any(
        i.get("url_pathname") == "admin" for i in app._registered_pages.values()
    )
    assert not [s for s in app.subheader if "API externa" in s.value]


def test_admin_ve_a_secao_e_cria_a_organizacao(banco, monkeypatch):
    app = _entrar_como_admin(monkeypatch, banco)
    assert [s for s in app.subheader if "API externa" in s.value]
    _criar_organizacao(app)
    assert "Organização criada" in _tudo_que_a_tela_mostra(app)
    app.run()
    assert app.selectbox(key="chaves_organizacao").options  # a lista agora tem a Alfa
    with banco.connect() as conexao:
        assert (
            conexao.execute(sa.text("select count(*) from organizacoes")).scalar() == 1
        )


def test_a_chave_aparece_uma_vez_e_nao_fica_em_log_estado_nem_auditoria(
    banco, monkeypatch, caplog
):
    app = _entrar_como_admin(monkeypatch, banco)
    _criar_organizacao(app).run()
    caplog.set_level(logging.DEBUG)
    app.button(key="chaves_emitir").click().run()
    assert not app.exception
    (chave,) = _valores_de_chave(app)  # aparece, na hora da emissão

    # segunda execução da tela (qualquer clique): a chave sumiu de tudo o que se mostra
    app.run()
    assert not _valores_de_chave(app)
    assert chave not in _tudo_que_a_tela_mostra(app)
    # a lista mostra só o prefixo, nunca a chave nem o hash
    prefixo = chave.split("_")[1]
    assert prefixo in _tudo_que_a_tela_mostra(app)
    assert hash_da_chave(chave) not in _tudo_que_a_tela_mostra(app)

    segredo = chave.split("_", 2)[2]
    assert chave not in _estado_da_sessao(app)
    assert segredo not in _estado_da_sessao(app)
    assert chave not in caplog.text
    assert segredo not in caplog.text
    with banco.connect() as conexao:
        registros = repr(conexao.execute(sa.select(auditoria)).fetchall())
    assert chave not in registros
    assert segredo not in registros
    assert hash_da_chave(chave) not in registros


def test_rotacionar_mostra_a_nova_uma_vez_e_revogar_exige_a_confirmacao(
    banco, monkeypatch
):
    app = _entrar_como_admin(monkeypatch, banco)
    _criar_organizacao(app).run()
    app.button(key="chaves_emitir").click().run()
    app.run()
    assert app.button(key="chaves_revogar").disabled  # sem confirmar, não clica
    app.checkbox(key="chaves_confirmo").check().run()
    app.button(key="chaves_rotacionar").click().run()
    assert not app.exception
    assert len(_valores_de_chave(app)) == 1
    app.run()
    assert not _valores_de_chave(app)
    with banco.connect() as conexao:
        assert (
            conexao.execute(sa.text("select count(*) from chaves_da_api")).scalar() == 2
        )


def test_suspender_e_reativar_a_organizacao(banco, monkeypatch):
    app = _entrar_como_admin(monkeypatch, banco)
    _criar_organizacao(app).run()
    app.button(key="chaves_suspender").click().run()
    assert not app.exception
    assert app.button(key="chaves_reativar")
    app.button(key="chaves_reativar").click().run()
    assert not app.exception
    assert app.button(key="chaves_suspender")


def test_organizacao_suspensa_nao_ganha_chave_e_a_tela_explica(banco, monkeypatch):
    app = _entrar_como_admin(monkeypatch, banco)
    _criar_organizacao(app).run()
    app.button(key="chaves_suspender").click().run()
    app.button(key="chaves_emitir").click().run()
    assert not app.exception
    assert not _valores_de_chave(app)
    assert "suspensa" in " ".join(e.value for e in app.error)
