"""Falhas de leitura da conta na página Minhas simulações (`telas/dados_da_conta.py`).

O ciclo salvar, reabrir e apagar está em `test_conta_no_app.py`; os avisos de falha ao salvar e ao
apagar, em `test_simulacoes_falhas.py`. Aqui o banco falha ao ler: a página deve avisar sem quebrar
e sem mostrar a lista (nem a mensagem de "nenhuma simulação", que seria mentira).
"""

from src.banco import dados_do_usuario as repo
from telas import dados_da_conta
from tests.ajudantes_da_conta import abrir_app, entrar_como, id_do_usuario

AVISO_AO_LISTAR = "Não consegui carregar as suas simulações agora."
SEM_SIMULACOES = "Você ainda não salvou nenhuma simulação"


def _textos(elementos) -> str:
    return " ".join(str(e.value) for e in elementos)


def test_falha_ao_listar_as_simulacoes_avisa_sem_dizer_que_esta_vazio(
    banco, monkeypatch
):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    abrir_app()
    ana = id_do_usuario(banco, "ana")
    with banco.begin() as conexao:
        repo.salvar_simulacao(conexao, ana, "backtest", "Guardada", {}, {})

    def quebrar(*_args, **_kwargs):
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(dados_da_conta, "listar_simulacoes", quebrar)
    app = abrir_app("simulacoes")

    assert not app.exception
    assert AVISO_AO_LISTAR in _textos(app.warning)
    assert SEM_SIMULACOES not in _textos(app.info)
    assert not app.expander  # nenhuma simulação aparece
    with banco.connect() as conexao:  # e a simulação guardada continua lá
        assert [s.nome for s in repo.listar_simulacoes(conexao, ana)] == ["Guardada"]


def test_falha_ao_carregar_a_conta_avisa_que_nada_fica_guardado(banco, monkeypatch):
    entrar_como(monkeypatch, "ana", "ana@exemplo.com")
    abrir_app()

    def quebrar(*_args, **_kwargs):
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(dados_da_conta, "listar_favoritos", quebrar)
    app = abrir_app()

    assert not app.exception
    assert "Não consegui carregar os favoritos e as preferências" in _textos(
        app.warning
    )
    assert "conta_carregada" not in app.session_state  # tenta de novo depois
