"""Quem pode chamar a API de leitura (src/api_v1/acesso.py e a rota /api/v1/eu).

Os tokens são assinados aqui com chaves geradas no teste, no formato do Google: nada de internet.
"""

import time

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from joserfc.jwk import RSAKey

from src import api, paginas
from src.api_v1 import VARIAVEL_DA_CHAVE, acesso, api_v1_ligada, rotas
from src.banco.usuarios import entrar, mudar_plano
from src.conformidade import registrar_aceite
from src.planos import PARES
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


def test_limite_esquece_quem_parou_de_pedir():
    """Com rota pública (chave por IP), quem só passou não pode ficar na memória para sempre."""
    limite = acesso.LimiteDePedidos(por_minuto=3, maximo_de_chaves=5)
    for i in range(5):
        assert limite.permitir(f"ip:{i}", 0)
    assert limite.chaves() == 5
    assert limite.permitir(
        "ip:novo", 61
    )  # passou do máximo: as que não pedem há 1 min saem
    assert limite.chaves() == 1
    for _ in range(2):
        assert limite.permitir("ip:novo", 62)
    assert not limite.permitir(
        "ip:novo", 62
    )  # a limpeza não zera quem ainda está pedindo


def test_limite_de_pedidos_por_conta():
    limite = acesso.LimiteDePedidos(por_minuto=3)
    assert all(limite.permitir("ana", AGORA + i) for i in range(3))
    assert not limite.permitir("ana", AGORA + 3)
    assert limite.permitir("bia", AGORA + 3)  # cada conta tem o seu limite
    assert limite.permitir("ana", AGORA + 61)  # passou um minuto


def test_api_ligada_so_com_a_chave_igual_a_1():
    assert not api_v1_ligada({})
    assert not api_v1_ligada({VARIAVEL_DA_CHAVE: "0"})
    assert api_v1_ligada({VARIAVEL_DA_CHAVE: "1"})


# --- a rota /api/v1/eu, com o FastAPI de verdade ---


@pytest.fixture
def cliente(banco, monkeypatch, chave, chaves_publicas):
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "1")
    monkeypatch.setenv(acesso.VARIAVEL_DO_CLIENT_ID, CLIENT_ID)
    monkeypatch.setattr(acesso, "agora", lambda: AGORA)
    app = api.criar_app({VARIAVEL_DA_CHAVE: "1"})
    app.dependency_overrides[acesso.chaves_do_google] = lambda: chaves_publicas
    acesso.LIMITE.zerar()
    yield TestClient(app)


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
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "0")
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

    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "1")
    monkeypatch.setenv(acesso.VARIAVEL_DO_CLIENT_ID, CLIENT_ID)
    monkeypatch.setattr(acesso, "_chaves_em_cache", None)
    monkeypatch.setattr(acesso.httpx, "get", falhar)
    app = api.criar_app({VARIAVEL_DA_CHAVE: "1"})
    resposta = TestClient(app).get("/api/v1/eu", headers=com_token(token(chave)))
    assert resposta.status_code == 503


def test_desligada_a_api_nem_monta_a_v1_e_fica_leve():
    """Sem a chave, as rotas da v1 não existem e nada dela é carregado (o contêiner é pequeno)."""
    cliente = TestClient(api.criar_app({}))
    assert cliente.get("/api/v1/eu").status_code == 404
    assert cliente.get("/v1/eu").status_code == 404


# --- /api/v1/configuracao: o que a tela nova precisa antes do login (série 3) ---


def test_configuracao_responde_sem_login_e_so_com_o_client_id(cliente):
    """O client ID do Google não é segredo (vai no endereço do login): a tela precisa dele antes."""
    resposta = cliente.get("/api/v1/configuracao")
    assert resposta.status_code == 200
    assert resposta.json() == {"google_client_id": CLIENT_ID}


def test_configuracao_sem_client_id_devolve_null(cliente, monkeypatch):
    monkeypatch.delenv(acesso.VARIAVEL_DO_CLIENT_ID)
    assert cliente.get("/api/v1/configuracao").json() == {"google_client_id": None}


def test_configuracao_com_a_api_desligada_404(cliente, monkeypatch):
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "0")
    assert cliente.get("/api/v1/configuracao").status_code == 404


# --- o motivo do 401/403 num cabeçalho: a tela nova mostra o caminho certo para cada um ---


@pytest.mark.parametrize(
    ("cabecalho", "motivo"),
    [({}, "sem-token"), ({"Authorization": "Bearer lixo"}, "token-invalido")],
)
def test_401_diz_o_motivo(cliente, ana, cabecalho, motivo):
    resposta = cliente.get("/api/v1/eu", headers=cabecalho)
    assert resposta.status_code == 401
    assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == motivo


def test_conta_nova_e_termos_dizem_o_motivo(cliente, banco, chave):
    resposta = cliente.get("/api/v1/eu", headers=com_token(token(chave, sub="bia")))
    assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "conta-nova"
    with banco.begin() as conexao:
        entrar(conexao, "ana", "ana@exemplo.com")
    resposta = cliente.get("/api/v1/eu", headers=com_token(token(chave)))
    assert resposta.status_code == 403
    assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "termos"


# --- O plano da conta abre a página da rota? (ADR 0062) -------------------------------------
# Nenhuma página com contrato é paga hoje: uma página paga de mentira, com rota só no teste.

ROTA_PAGA = "/v1/pago-de-teste"
PAGINA_PAGA = paginas.Pagina(
    "pago_de_teste",
    "Pago de teste",
    paginas.GRUPO_AVANCADO,
    ":material/lock:",
    "Só existe no teste.",
    recurso=PARES,
    contrato=paginas.Contrato("GET", ROTA_PAGA, (), "PagoDeTesteV1"),
)


@pytest.fixture
def chamadas(cliente, monkeypatch):
    """Monta a rota paga e uma rota sem contrato; a lista guarda cada vez que uma delas calculou."""
    feitas = []
    teste = APIRouter(prefix="/v1")

    @teste.get("/pago-de-teste")
    def pago(_conta: rotas.Conta) -> dict:
        feitas.append("pago")
        return {"ok": True}

    @teste.get("/sem-contrato")
    def sem_contrato(_conta: rotas.Conta) -> dict:
        feitas.append("sem-contrato")
        return {"ok": True}

    cliente.app.include_router(teste)
    cliente.app.include_router(teste, prefix="/api")
    monkeypatch.setitem(paginas.POR_ROTA, ROTA_PAGA, PAGINA_PAGA)
    monkeypatch.setitem(paginas.POR_CHAVE, PAGINA_PAGA.chave, PAGINA_PAGA)
    return feitas


def _virar(banco, usuario, plano):
    with banco.begin() as conexao:
        mudar_plano(conexao, usuario.id, plano)


@pytest.mark.parametrize("caminho", ["/api/v1/pago-de-teste", "/v1/pago-de-teste"])
def test_rota_paga_recusa_quem_nao_tem_o_plano_com_o_motivo(
    cliente, ana, chave, chamadas, caminho
):
    resposta = cliente.get(caminho, headers=com_token(token(chave)))
    assert resposta.status_code == 403
    assert resposta.json()["detail"] == paginas.motivo_da_pagina(
        "gratuito", "pago_de_teste"
    )
    assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "plano"


@pytest.mark.parametrize("plano", ["gratuito", "plus"])
def test_rota_paga_nao_calcula_quando_recusa(
    cliente, banco, ana, chave, chamadas, plano
):
    _virar(banco, ana, plano)
    assert (
        cliente.get(
            "/api/v1/pago-de-teste", headers=com_token(token(chave))
        ).status_code
        == 403
    )
    assert chamadas == []


def test_rota_paga_responde_a_quem_tem_o_plano(cliente, banco, ana, chave, chamadas):
    _virar(banco, ana, "pro")
    resposta = cliente.get("/api/v1/pago-de-teste", headers=com_token(token(chave)))
    assert resposta.status_code == 200
    assert chamadas == ["pago"]


def test_rota_paga_confere_o_login_antes_do_plano(cliente, ana, chamadas):
    resposta = cliente.get("/api/v1/pago-de-teste")
    assert resposta.status_code == 401
    assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "sem-token"


def test_rota_sem_contrato_fecha(cliente, banco, ana, chave, chamadas):
    """Rota nova sem contrato de página nunca fica livre por esquecimento, nem para o Pro."""
    _virar(banco, ana, "pro")
    resposta = cliente.get("/api/v1/sem-contrato", headers=com_token(token(chave)))
    assert resposta.status_code == 500
    assert chamadas == []
