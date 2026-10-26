"""O login e o bloqueio da conta em transações de verdade, ao mesmo tempo (3ª revisão cruzada do
Codex no #659).

No PostgreSQL (READ COMMITTED), a sessão que um login gravou só aparece para as outras transações
depois do commit. Se o admin bloqueia e desbloqueia nesse meio-tempo, nenhum dos dois vê a sessão
para encerrá-la. O SQLite não mostra a corrida (um escritor por vez no banco inteiro): este teste só
roda com `TICKERLAB_TEST_DATABASE_URL`, como no CI.
"""

import os
import threading
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from src import api
from src.administracao import desbloquear_conta
from src.api_v1 import VARIAVEL_DA_CHAVE, acesso, conta
from src.api_v1.sessao import NOME_DO_COOKIE
from src.autenticacao import VARIAVEL_DOS_ADMINS
from src.banco import sessoes
from src.banco.conexao import criar_engine, migrar_para
from src.banco.usuarios import buscar_por_google_sub
from tests.ajudantes_da_api import (
    AGORA,
    CLIENT_ID,
    chaves_publicas,
    com_token,
    gerar_chave,
    token,
)
from tests.ajudantes_da_conta import bloquear_pelo_admin

URL_DE_TESTE = os.environ.get("TICKERLAB_TEST_DATABASE_URL")
ESPERA_MAXIMA = 20  # segundos: só para o teste não ficar preso se algo travar de vez
ESPERA_DO_ADMIN = 1  # segundos: o bastante para o admin terminar, se nada o segurar

pytestmark = [
    pytest.mark.xdist_group("postgres"),
    pytest.mark.skipif(not URL_DE_TESTE, reason="só no PostgreSQL (CI)"),
]

DA_CARLA = {"sub": "carla-pg", "email": "carla-pg@exemplo.com", "name": "Carla"}


@pytest.fixture
def motor(monkeypatch):
    assert URL_DE_TESTE
    migrar_para("base", URL_DE_TESTE)
    migrar_para("head", URL_DE_TESTE)
    monkeypatch.setenv("TICKERLAB_DATABASE_URL", URL_DE_TESTE)
    motor = criar_engine(URL_DE_TESTE)
    yield motor
    motor.dispose()
    migrar_para("base", URL_DE_TESTE)


@pytest.fixture
def cliente(motor, monkeypatch):
    chave = gerar_chave()
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "1")
    monkeypatch.setenv(acesso.VARIAVEL_DO_CLIENT_ID, CLIENT_ID)
    monkeypatch.delenv(VARIAVEL_DOS_ADMINS, raising=False)
    monkeypatch.setattr(acesso, "agora", lambda: AGORA)
    app = api.criar_app({VARIAVEL_DA_CHAVE: "1"})
    app.dependency_overrides[acesso.chaves_do_google] = lambda: chaves_publicas(chave)
    acesso.LIMITE.zerar()
    cliente = TestClient(app)
    cliente.headers.update(com_token(token(chave, **DA_CARLA)))
    return cliente


class _LoginParadoAntesDoCommit:
    """O motor do banco, mas a transação que gravou a sessão do login para antes do commit até o
    teste soltar: é a janela em que as outras transações ainda não veem a sessão."""

    def __init__(self, motor, monkeypatch):
        self.motor = motor
        self.gravou = threading.Event()
        self.parou = threading.Event()
        self.soltar = threading.Event()
        abrir = sessoes.abrir

        def abrir_e_marcar(*args, **kwargs):
            self.gravou.set()
            return abrir(*args, **kwargs)

        monkeypatch.setattr(sessoes, "abrir", abrir_e_marcar)
        monkeypatch.setattr(conta, "obter_engine", lambda: self)

    def connect(self):
        return self.motor.connect()

    @contextmanager
    def begin(self):
        with self.motor.begin() as conexao:
            yield conexao
            if self.gravou.is_set() and not self.parou.is_set():
                self.parou.set()
                assert self.soltar.wait(ESPERA_MAXIMA)


def _em_segundo_plano(funcao, saida: dict) -> threading.Thread:
    def rodar():
        try:
            saida["valor"] = funcao()
        except Exception as erro:  # noqa: BLE001 (o erro volta para o teste, não some na thread)
            saida["erro"] = erro

    linha = threading.Thread(target=rodar, daemon=True)
    linha.start()
    return linha


def test_bloqueio_e_desbloqueio_antes_do_commit_do_login_nao_deixam_sessao_valendo(
    motor, cliente, monkeypatch
):
    """O login grava a sessão e para antes do commit; o admin bloqueia e desbloqueia, cada um na
    sua transação. Depois de tudo, nenhuma sessão desse login vale."""
    assert cliente.post("/api/v1/conta").status_code == 200
    with motor.connect() as conexao:
        carla = buscar_por_google_sub(conexao, DA_CARLA["sub"])
    assert carla is not None
    cliente.cookies.clear()
    parado = _LoginParadoAntesDoCommit(motor, monkeypatch)

    do_login: dict = {}
    login = _em_segundo_plano(lambda: cliente.post("/api/v1/conta"), do_login)
    assert parado.parou.wait(ESPERA_MAXIMA), "o login não chegou ao commit"

    def bloquear_e_desbloquear():
        bloquear_pelo_admin(motor, carla.id)
        with motor.begin() as conexao:
            chefe = buscar_por_google_sub(conexao, "g-chefe-do-bloqueio")
            assert chefe is not None
            desbloquear_conta(conexao, chefe.id, carla.id)

    do_admin: dict = {}
    admin = _em_segundo_plano(bloquear_e_desbloquear, do_admin)
    admin.join(ESPERA_DO_ADMIN)  # sem a trava da conta, o admin termina aqui
    parado.soltar.set()
    login.join(ESPERA_MAXIMA)
    admin.join(ESPERA_MAXIMA)
    assert not login.is_alive() and not admin.is_alive()
    assert "erro" not in do_admin, do_admin.get("erro")
    assert "erro" not in do_login, do_login.get("erro")

    resposta = do_login["valor"]
    valor = resposta.cookies.get(NOME_DO_COOKIE)
    if resposta.status_code == 200:
        assert valor
        with motor.connect() as conexao:
            assert sessoes.conta_da_sessao(conexao, valor) is None
    else:
        assert resposta.status_code in (403, 409)
        assert not valor
