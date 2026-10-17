"""As simulações pelo app novo (Workspace, PR 1 do plano de 17/10; ADR 0062, tela 3).

O que o Streamlit faz em "Minhas simulações" passa a existir na API v1: listar, salvar (com a ficha
"Foi sorte?", para o Pulse recalcular depois) e apagar. O limite de simulações do plano vira um 403
com o motivo "plano", que o app novo já sabe mostrar.
"""

import pytest
from fastapi.testclient import TestClient

from src import api, planos
from src.api_v1 import VARIAVEL_DA_CHAVE, acesso
from src.banco.usuarios import entrar
from src.conformidade import registrar_aceite
from tests.ajudantes_da_api import (
    AGORA,
    CLIENT_ID,
    chaves_publicas,
    com_token,
    gerar_chave,
    token,
)


@pytest.fixture(scope="module")
def chave():
    return gerar_chave()


@pytest.fixture
def app(banco, monkeypatch, chave):
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "1")
    monkeypatch.setenv(acesso.VARIAVEL_DO_CLIENT_ID, CLIENT_ID)
    monkeypatch.setattr(acesso, "agora", lambda: AGORA)
    nova = api.criar_app({VARIAVEL_DA_CHAVE: "1"})
    nova.dependency_overrides[acesso.chaves_do_google] = lambda: chaves_publicas(chave)
    acesso.LIMITE.zerar()
    with banco.begin() as conexao:
        ana = entrar(conexao, "ana", "ana@exemplo.com")[0]
        registrar_aceite(conexao, ana.id)
    return nova


@pytest.fixture
def cliente(app, chave):
    return TestClient(app, headers=com_token(token(chave)))


# --- Tarefa 1.1: o limite do plano vira 403 com o motivo "plano" ----------------------------


def test_limite_do_plano_responde_403_com_motivo_plano(app, cliente):
    """Qualquer rota que deixe escapar `LimiteDoPlanoError` responde como a recusa de plano da
    API (403 + `X-TickerLab-Motivo: plano`), com a frase do erro, que já sugere o Pro."""

    def estourar():
        planos.conferir_simulacoes("gratuito", 5)  # a 6ª simulação do Gratuito

    with pytest.raises(planos.LimiteDoPlanoError) as erro:
        estourar()
    app.add_api_route("/v1/estourar-limite", estourar)
    resposta = cliente.get("/v1/estourar-limite")
    assert resposta.status_code == 403, resposta.text
    assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "plano"
    assert resposta.json() == {"detail": str(erro.value)}
