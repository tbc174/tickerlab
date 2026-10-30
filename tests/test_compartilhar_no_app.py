"""Compartilhar no app (onda 4, PR 4): a ficha no backtest, o PDF na biblioteca e a lista em Meus dados."""

import sqlalchemy as sa
from streamlit.testing.v1 import AppTest

from src import compartilhamentos as comp
from src.banco import compartilhamentos as links
from src.banco import dados_do_usuario as repo
from src.banco import pdfs_originais as pdfs
from src.banco.modelo import compartilhamentos
from tests.ajudantes_da_conta import abrir_app, entrar_como, id_do_usuario, ir_para
from tests.test_compartilhamentos import _congelada

PDF = b"%PDF-1.7 relatorio de exemplo"


def _textos(app) -> str:
    return " ".join(
        str(e.value) for tipo in (app.markdown, app.caption, app.success, app.error, app.code)
        for e in tipo
    )  # fmt: skip


def _codigo_mostrado(app) -> str:
    (bloco,) = [c.value for c in app.code if comp.ENDERECO_DA_PAGINA in c.value]
    return bloco.split("#", 1)[1]


def _links(banco):
    with banco.connect() as conexao:
        return conexao.execute(sa.select(compartilhamentos)).all()


def test_compartilhar_a_ficha_mostra_o_link_uma_vez(banco, monkeypatch):
    entrar_como(monkeypatch, "lia", "lia@exemplo.com")
    app = abrir_app("backtest")
    assert not app.exception
    app.button(key="compartilhar_ficha_criar").click().run()
    assert not app.exception
    codigo = _codigo_mostrado(app)
    assert comp.AVISO_DO_LINK_CRIADO in _textos(app)
    (linha,) = _links(banco)
    assert linha.tipo == "ficha" and linha.usuario_id == id_do_usuario(banco, "lia")
    assert linha.codigo_hash == comp.hash_do_codigo(codigo)
    with banco.begin() as conexao:
        aberto = links.abrir_link(conexao, codigo)
    assert aberto is not None and aberto.ficha is not None
    assert aberto.ficha.fonte == "dados de exemplo guardados no projeto"
    assert len(aberto.ficha.checagens) == 5


def test_prazo_escolhido_vale(banco, monkeypatch):
    entrar_como(monkeypatch, "lia", "lia@exemplo.com")
    app = abrir_app("backtest")
    app.selectbox(key="compartilhar_ficha_prazo").select(7).run()
    app.button(key="compartilhar_ficha_criar").click().run()
    (linha,) = _links(banco)
    assert (linha.expira_em - linha.criado_em).days == 7


def test_sem_login_nao_ha_como_compartilhar():
    """No modo local (sem login) não há conta: não há link para criar."""
    app = AppTest.from_file("../app.py", default_timeout=180)
    app.session_state["usar_exemplo"] = True
    ir_para(app.run(), "backtest")
    assert not app.exception
    assert not [b for b in app.button if b.key == "compartilhar_ficha_criar"]


def test_limite_do_plano_aparece_na_tela(banco, monkeypatch):
    entrar_como(monkeypatch, "lia", "lia@exemplo.com")
    app = abrir_app("backtest")
    usuario_id = id_do_usuario(banco, "lia")
    with banco.begin() as conexao:
        for _ in range(3):
            links.criar_link_da_ficha(conexao, usuario_id, "gratuito", _congelada(), 30)
    app.button(key="compartilhar_ficha_criar").click().run()
    assert not app.exception
    assert "até 3 links ativos" in _textos(app)
    assert len(_links(banco)) == 3


def _pdf_guardado(banco, usuario_id):
    with banco.begin() as conexao:
        rid = repo.registrar_relatorio(conexao, usuario_id, "ativo", titulo="PETR4")
        pdfs.guardar_pdf_original(conexao, usuario_id, rid, "gratuito", PDF, {})
    return rid


def test_compartilhar_o_pdf_da_biblioteca(banco, monkeypatch):
    entrar_como(monkeypatch, "lia", "lia@exemplo.com")
    abrir_app()
    rid = _pdf_guardado(banco, id_do_usuario(banco, "lia"))
    app = abrir_app("relatorio")
    assert not app.exception
    app.button(key=f"compartilhar_pdf_{rid}_criar").click().run()
    assert not app.exception
    codigo = _codigo_mostrado(app)
    with banco.connect() as conexao:
        assert links.pdf_do_link(conexao, codigo) == ("TickerLab-PETR4.pdf", PDF)


def test_meus_dados_lista_e_revoga(banco, monkeypatch):
    entrar_como(monkeypatch, "lia", "lia@exemplo.com")
    abrir_app()
    usuario_id = id_do_usuario(banco, "lia")
    with banco.begin() as conexao:
        codigo = links.criar_link_da_ficha(
            conexao, usuario_id, "gratuito", _congelada(), 30
        )
        (link,) = links.listar_links(conexao, usuario_id)
    app = abrir_app("meus_dados")
    assert not app.exception
    textos = _textos(app)
    assert "Foi sorte? Cruzamento de médias em PETR4" in textos and "ativo" in textos
    app.button(key=f"revogar_link_{link.id}").click().run()
    assert not app.exception
    with banco.begin() as conexao:
        assert links.abrir_link(conexao, codigo) is None
        assert links.listar_links(conexao, usuario_id)[0].situacao == "revogado"
    assert not [b for b in app.button if b.key == f"revogar_link_{link.id}"]


def test_link_de_outra_ficha_nao_fica_embaixo_da_ficha_nova(banco, monkeypatch):
    """Achado 2a do Codex: trocar a estratégia não pode deixar o link da ficha anterior à vista."""
    entrar_como(monkeypatch, "lia", "lia@exemplo.com")
    app = abrir_app("backtest")
    app.button(key="compartilhar_ficha_criar").click().run()
    assert _codigo_mostrado(app)
    app.selectbox(key="backtest_estrategia").select("MACD").run()
    assert not app.exception
    assert not [c for c in app.code if comp.ENDERECO_DA_PAGINA in c.value]
    assert comp.AVISO_DO_LINK_CRIADO not in _textos(app)


def test_aba_aberta_da_conta_bloqueada_nao_revoga_o_link(banco, monkeypatch):
    """2ª revisão cruzada do Codex no #659: o clique em "Revogar" roda antes da releitura da conta.
    Revogar é para sempre; na conta bloqueada o link só para enquanto durar o bloqueio."""
    from src.administracao import desbloquear_conta
    from src.banco.usuarios import buscar_por_google_sub
    from tests.ajudantes_da_conta import bloquear_pelo_admin

    monkeypatch.setattr("streamlit.logout", lambda: None)
    entrar_como(monkeypatch, "lia", "lia@exemplo.com")
    abrir_app()
    usuario_id = id_do_usuario(banco, "lia")
    with banco.begin() as conexao:
        codigo = links.criar_link_da_ficha(
            conexao, usuario_id, "gratuito", _congelada(), 30
        )
        (link,) = links.listar_links(conexao, usuario_id)
    app = abrir_app("meus_dados")
    bloquear_pelo_admin(banco, usuario_id)
    app.session_state["usuario_em"] = 0  # o prazo da releitura já venceu
    app.button(key=f"revogar_link_{link.id}").click().run()
    assert not app.exception
    with banco.connect() as conexao:
        assert (
            conexao.execute(
                sa.select(compartilhamentos.c.revogado_em).where(
                    compartilhamentos.c.id == link.id
                )
            ).scalar_one()
            is None
        )
    with banco.begin() as conexao:
        chefe = buscar_por_google_sub(conexao, "g-chefe-do-bloqueio")
        desbloquear_conta(conexao, chefe.id, usuario_id)
    with banco.begin() as conexao:
        assert links.abrir_link(conexao, codigo) is not None
