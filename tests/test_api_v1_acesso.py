"""Quem pode chamar a API de leitura (src/api_v1/acesso.py e a rota /api/v1/eu).

Os tokens são assinados aqui com chaves geradas no teste, no formato do Google: nada de internet.
"""

import time

import pytest
from fastapi.testclient import TestClient
from joserfc.jwk import RSAKey

from src import api
from src.api_v1 import acesso
from src.banco.usuarios import entrar
from src.conformidade import registrar_aceite
from tests.ajudantes_da_api import (
    AGORA,
    CLIENT_ID,
    com_token,
    gerar_chave,
    token,
)
from tests.ajudantes_da_api import chaves_publicas as _chaves_publicas


@pytest.fixture(scope="module")
def chave():
    return gerar_chave()


@pytest.fixture(scope="module")
def chaves_publicas(chave):
    return _chaves_publicas(chave)


def test_token_valido_devolve_a_identidade(chave, chaves_publicas):
    identidade = acesso.verificar_token(token(chave), chaves_publicas, CLIENT_ID, AGORA)
    assert identidade.sub == "ana"
    assert identidade.email == "ana@exemplo.com"


@pytest.mark.parametrize(
    "mudancas",
    [
        {"aud": "outro-app.apps.googleusercontent.com"},  # token feito para outro site
        {"iss": "https://falso.exemplo.com"},
        {"exp": AGORA - 3600},  # vencido
        {"email_verified": False},
        {"email_verified": None},  # o Google sempre manda; sem ele, recusa
        {"sub": None},
    ],
)
def test_token_recusado(chave, chaves_publicas, mudancas):
    with pytest.raises(acesso.TokenInvalidoError):
        acesso.verificar_token(
            token(chave, **mudancas), chaves_publicas, CLIENT_ID, AGORA
        )


def test_token_assinado_por_outra_chave_recusado(chaves_publicas):
    intrusa = RSAKey.generate_key(2048, parameters={"kid": "chave-1"})
    with pytest.raises(acesso.TokenInvalidoError):
        acesso.verificar_token(token(intrusa), chaves_publicas, CLIENT_ID, AGORA)


def test_token_sem_assinatura_recusado(chaves_publicas):
    """O ataque clássico: `alg: none`, sem assinatura nenhuma."""
    partes = token(RSAKey.generate_key(2048)).split(".")
    sem_assinatura = (
        "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0." + partes[1] + "."  # {"alg":"none"}
    )
    with pytest.raises(acesso.TokenInvalidoError):
        acesso.verificar_token(sem_assinatura, chaves_publicas, CLIENT_ID, AGORA)


def test_lixo_no_lugar_do_token_recusado(chaves_publicas):
    with pytest.raises(acesso.TokenInvalidoError):
        acesso.verificar_token("nao-e-um-token", chaves_publicas, CLIENT_ID, AGORA)


def test_limite_de_pedidos_por_conta():
    limite = acesso.LimiteDePedidos(por_minuto=3)
    assert all(limite.permitir("ana", AGORA + i) for i in range(3))
    assert not limite.permitir("ana", AGORA + 3)
    assert limite.permitir("bia", AGORA + 3)  # cada conta tem o seu limite
    assert limite.permitir("ana", AGORA + 61)  # passou um minuto


def test_api_ligada_so_com_a_chave_igual_a_1():
    assert not acesso.api_v1_ligada({})
    assert not acesso.api_v1_ligada({acesso.VARIAVEL_DA_CHAVE: "0"})
    assert acesso.api_v1_ligada({acesso.VARIAVEL_DA_CHAVE: "1"})


# --- a rota /api/v1/eu, com o FastAPI de verdade ---


@pytest.fixture
def cliente(banco, monkeypatch, chave, chaves_publicas):
    monkeypatch.setenv(acesso.VARIAVEL_DA_CHAVE, "1")
    monkeypatch.setenv(acesso.VARIAVEL_DO_CLIENT_ID, CLIENT_ID)
    monkeypatch.setattr(acesso, "agora", lambda: AGORA)
    api.app.dependency_overrides[acesso.chaves_do_google] = lambda: chaves_publicas
    acesso.LIMITE.zerar()
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()


@pytest.fixture
def ana(banco):
    with banco.begin() as conexao:
        usuario = entrar(conexao, "ana", "ana@exemplo.com")[0]
        registrar_aceite(conexao, usuario.id)
    return usuario


def test_eu_mostra_o_plano_da_conta(cliente, ana, chave):
    resposta = cliente.get("/api/v1/eu", headers=com_token(token(chave)))
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["plano"] == "gratuito"
    assert dados["limites"]["favoritos"] == 3
    assert "email" not in dados  # o e-mail não precisa sair (LGPD)


def test_eu_tambem_sem_o_prefixo_api(cliente, ana, chave):
    """Como as outras rotas, funciona se o proxy tirar ou repassar o /api."""
    assert cliente.get("/v1/eu", headers=com_token(token(chave))).status_code == 200


def test_sem_token_401(cliente, ana):
    assert cliente.get("/api/v1/eu").status_code == 401
    assert (
        cliente.get("/api/v1/eu", headers={"Authorization": "Basic x"}).status_code
        == 401
    )


def test_conta_que_nunca_entrou_no_app_401(cliente, banco, chave):
    resposta = cliente.get("/api/v1/eu", headers=com_token(token(chave, sub="bia")))
    assert resposta.status_code == 401


def test_conta_sem_os_termos_atuais_403(cliente, banco, chave):
    with banco.begin() as conexao:
        entrar(conexao, "ana", "ana@exemplo.com")
    resposta = cliente.get("/api/v1/eu", headers=com_token(token(chave)))
    assert resposta.status_code == 403


def test_desligada_responde_404_e_o_resto_continua(cliente, ana, chave, monkeypatch):
    monkeypatch.setenv(acesso.VARIAVEL_DA_CHAVE, "0")
    assert cliente.get("/api/v1/eu", headers=com_token(token(chave))).status_code == 404
    assert cliente.get("/api/saude").status_code in (200, 503)


def test_sem_client_id_configurado_503(cliente, ana, chave, monkeypatch):
    monkeypatch.delenv(acesso.VARIAVEL_DO_CLIENT_ID)
    assert cliente.get("/api/v1/eu", headers=com_token(token(chave))).status_code == 503


def test_passou_do_limite_429(cliente, ana, chave, monkeypatch):
    monkeypatch.setattr(acesso, "LIMITE", acesso.LimiteDePedidos(por_minuto=2))
    cabecalho = com_token(token(chave))
    assert [
        cliente.get("/api/v1/eu", headers=cabecalho).status_code for _ in range(3)
    ] == [
        200,
        200,
        429,
    ]


def test_o_tempo_real_e_usado_fora_dos_testes():
    assert abs(acesso.agora() - time.time()) < 5


def test_google_fora_do_ar_responde_503(banco, ana, chave, monkeypatch):
    import httpx

    def falhar(*_args, **_kwargs):
        raise httpx.ConnectError("sem rede")

    monkeypatch.setenv(acesso.VARIAVEL_DA_CHAVE, "1")
    monkeypatch.setenv(acesso.VARIAVEL_DO_CLIENT_ID, CLIENT_ID)
    monkeypatch.setattr(acesso, "_chaves_em_cache", None)
    monkeypatch.setattr(acesso.httpx, "get", falhar)
    resposta = TestClient(api.app).get("/api/v1/eu", headers=com_token(token(chave)))
    assert resposta.status_code == 503
