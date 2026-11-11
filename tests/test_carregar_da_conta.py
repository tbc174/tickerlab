"""`carregar_da_conta`: as preferências guardadas (tema, tutorial, tolerância) viram o ponto de partida."""

from src.banco import dados_do_usuario as repo
from src.ficha import PREFERENCIA_DA_TOLERANCIA, TOLERANCIA_PADRAO_DE_QUEDA
from tests.ajudantes_da_conta import abrir_app, entrar_como, id_do_usuario


def _guardar_preferencias(banco, sub, dados):
    with banco.begin() as conexao:
        repo.salvar_preferencias(conexao, id_do_usuario(banco, sub), dados)


def test_tema_tutorial_e_tolerancia_guardados_voltam_na_proxima_sessao(
    banco, monkeypatch
):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    abrir_app()  # cria a conta
    _guardar_preferencias(
        banco,
        "ana",
        {"tema": "escuro", "tutorial_visto": True, PREFERENCIA_DA_TOLERANCIA: 0.2},
    )

    app = abrir_app()

    assert not app.exception
    assert app.session_state["tema_do_app"] == "escuro"
    assert app.session_state["tema_escolhido"] is True
    assert app.session_state["tutorial_visto"] is True
    assert app.session_state["ficha_tolerancia"] == 20


def test_preferencia_invalida_cai_no_padrao_sem_quebrar(banco, monkeypatch):
    entrar_como(monkeypatch, "bia", "bia@exemplo.com")
    abrir_app()
    _guardar_preferencias(
        banco,
        "bia",
        {"tema": "roxo", "tutorial_visto": "sim", PREFERENCIA_DA_TOLERANCIA: 99},
    )

    app = abrir_app()

    assert not app.exception
    assert app.session_state["tema_do_app"] == "auto"  # tema fora das três escolhas
    assert "tutorial_visto" not in app.session_state  # só o True de verdade vale
    assert app.session_state["ficha_tolerancia"] == round(
        TOLERANCIA_PADRAO_DE_QUEDA * 100
    )  # fora da faixa: padrão
