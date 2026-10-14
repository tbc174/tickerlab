"""A origem do cadastro no app: o primeiro login lê o cookie `tl_origem` e guarda (campanha, PR 1).

O AppTest não tem navegador, então o cookie entra por um dublê do contexto do cliente do
Streamlit (de onde `st.context.cookies` lê), como o `entrar_como` faz com o login do Google.
"""

from types import SimpleNamespace

from streamlit.runtime import context

from src.banco.origens import buscar_origem
from src.origem import NOME_DO_COOKIE, Origem
from tests.ajudantes_da_conta import abrir_app, entrar_como, id_do_usuario


def _com_cookie(monkeypatch, valor):
    cliente = SimpleNamespace(
        headers=[], cookies={NOME_DO_COOKIE: valor}, remote_ip=None
    )
    monkeypatch.setattr(context, "_get_client_context", lambda: cliente)


def _origem_de(banco, sub):
    with banco.connect() as conexao:
        return buscar_origem(conexao, id_do_usuario(banco, sub))


def test_primeiro_login_grava_a_origem_do_cookie(banco, monkeypatch):
    _com_cookie(monkeypatch, "s=instagram|m=publi|c=lancamento|r=clube-do-robo")
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")

    app = abrir_app()

    assert not app.exception
    assert _origem_de(banco, "ana") == Origem(
        source="instagram", medium="publi", campaign="lancamento", ref="clube-do-robo"
    )


def test_segundo_login_nao_troca_a_origem(banco, monkeypatch):
    _com_cookie(monkeypatch, "s=google|m=cpc")
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    abrir_app()

    _com_cookie(monkeypatch, "s=youtube|m=video")
    abrir_app()  # outra sessão: o login passa pelo banco de novo

    assert _origem_de(banco, "ana") == Origem(source="google", medium="cpc")


def test_login_sem_cookie_nao_grava_origem(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")

    app = abrir_app()

    assert not app.exception
    assert _origem_de(banco, "ana") is None
