"""Ajudantes dos testes que abrem o app com um usuário logado (Google simulado)."""

from streamlit import user_info
from streamlit.testing.v1 import AppTest

from src.banco.usuarios import buscar_por_google_sub
from src.paginas import PAGINA_INICIAL, pagina
from tests.test_autenticacao import AUTH_COMPLETO


def entrar_como(monkeypatch, sub, email):
    monkeypatch.setattr(
        user_info,
        "_get_user_info",
        lambda: {"is_logged_in": True, "sub": sub, "email": email, "name": sub},
    )


def ir_para(app: AppTest, chave: str) -> AppTest:
    """Troca de página (pelo endereço registrado no menu) e roda o app nela.

    O AppTest só sabe trocar de página por arquivo; como as páginas do app são funções, o
    endereço vem do registro que o `st.navigation` fez na primeira execução.
    """
    endereco = "" if chave == PAGINA_INICIAL else pagina(chave).url
    app._page_hash = next(
        h for h, i in app._registered_pages.items() if i.get("url_pathname") == endereco
    )
    return app.run()


def aceitar_os_termos_se_pedido(app: AppTest) -> AppTest:
    """No primeiro acesso o app pede o aceite dos termos: marca, confirma e segue."""
    if any(c.key == "aceite_dos_termos" for c in app.checkbox):
        app.checkbox(key="aceite_dos_termos").check().run()
        next(b for b in app.button if b.label == "Continuar").click().run()
    return app


def abrir_app(
    chave_da_pagina: str | None = None, aceitar_termos: bool = True
) -> AppTest:
    """Abre o app já logado (se o teste simulou o login) e, se pedido, numa página."""
    app = AppTest.from_file("../app.py", default_timeout=90)
    app.secrets["auth"] = AUTH_COMPLETO
    app.session_state["usar_exemplo"] = True
    app.run()
    if aceitar_termos:
        aceitar_os_termos_se_pedido(app)
    return ir_para(app, chave_da_pagina) if chave_da_pagina else app


def id_do_usuario(banco, sub):
    with banco.connect() as conexao:
        return buscar_por_google_sub(conexao, sub).id


def botao(app, rotulo):
    return next(b for b in app.button if b.label == rotulo)
