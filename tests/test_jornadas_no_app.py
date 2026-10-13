"""Jornadas de ponta a ponta com login (Master v3, Fase D).

O `test_paginas_no_app.py` abre todas as páginas no modo local (sem conta, tudo liberado). Aqui o
caminho é o de quem usa de verdade: com login, em cada plano, e com o banco fora do ar.
"""

import pytest

from src.banco import usuarios as contas
from src.banco.modelo import PLANOS
from src.conformidade import registrar_aceite
from src.paginas import PAGINAS
from tests.ajudantes_da_conta import abrir_app, entrar_como, ir_para

# um PostgreSQL que não responde (conexão recusada), com 1 s de limite por tentativa
BANCO_FORA_DO_AR = "postgresql://ninguem:x@127.0.0.1:1/fora_do_ar?connect_timeout=1"
FRASES_FALSAS_COM_O_BANCO_FORA = (
    "ainda não foram coletad",  # "ainda não foram coletados/coletadas"
    "ainda não tem alertas",
)
PAGINAS_QUE_LEEM_O_BANCO = (
    "research",
    "fundamentos",
    "por_dentro",
    "donos",
    "newsletter",
    "alertas",
)


def _conta(banco, plano="gratuito", admin=False):
    with banco.begin() as c:
        usuario, _ = contas.entrar(
            c,
            "ana",
            "ana@exemplo.com",
            emails_de_admin=("ana@exemplo.com",) if admin else (),
        )
        contas.mudar_plano(c, usuario.id, plano)
        registrar_aceite(c, usuario.id)


def _textos(app) -> str:
    return " ".join(str(x.value) for x in [*app.info, *app.warning, *app.error])


@pytest.mark.parametrize("plano", PLANOS)
def test_todas_as_paginas_abrem_com_login_em_cada_plano(banco, monkeypatch, plano):
    _conta(banco, plano)
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app()
    for p in PAGINAS:
        if p.somente_admin:  # testada em test_admin_no_app.py
            continue
        ir_para(app, p.chave)
        assert not app.exception, (
            f"{plano}/{p.chave}: {[e.value for e in app.exception]}"
        )
        assert not app.error, f"{plano}/{p.chave}: {[e.value for e in app.error]}"
    assert app.session_state["usuario"].plano == plano  # o login valeu o tempo todo


def test_banco_fora_do_ar_nenhuma_pagina_quebra_nem_inventa_vazio(banco, monkeypatch):
    # regressão do achado D-2 (Master v3): banco fora virava "ainda não coletado"
    _conta(banco, "pro")
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = abrir_app()  # entra com o banco no ar
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", BANCO_FORA_DO_AR)
    app.session_state["usuario_em"] = 0  # força reler o usuário, como a cada minuto
    for p in PAGINAS:
        if p.somente_admin:
            continue
        ir_para(app, p.chave)
        assert not app.exception, f"{p.chave}: {[e.value for e in app.exception]}"
        texto = _textos(app)
        for frase in FRASES_FALSAS_COM_O_BANCO_FORA:
            assert frase not in texto, f"{p.chave} diz '{frase}' com o banco fora"
        if p.chave in PAGINAS_QUE_LEEM_O_BANCO:
            assert "Não consegui ler" in texto, f"{p.chave} não avisou a falha"


def test_coleta_vazia_explica_sem_comando_interno_para_quem_usa(banco, monkeypatch):
    # achado D-3: o comando `python -m scripts...` aparecia para qualquer pessoa
    _conta(banco, "pro")
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = ir_para(abrir_app(), "research")
    texto = _textos(app)
    assert "ainda não foram coletados" in texto
    assert "A coleta roda uma vez por dia" in texto
    assert "python -m" not in texto


def test_coleta_vazia_mostra_os_comandos_para_o_administrador(banco, monkeypatch):
    monkeypatch.setenv("TICKERLAB_ADMINS", "ana@exemplo.com")
    _conta(banco, "pro", admin=True)
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    app = ir_para(abrir_app(), "research")
    assert "`python -m scripts.atualizar_eventos`" in _textos(app)
