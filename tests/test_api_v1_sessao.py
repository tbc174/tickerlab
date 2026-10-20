"""A sessão por cookie na API v1 (plano do login com Microsoft e e-mail, PR 1, tarefa 4).

`POST /v1/conta` (com o token do Google) abre a sessão e põe o cookie `__Host-tl_sessao`; daí em
diante o app novo não manda token nenhum: o navegador manda o cookie. Como o navegador manda o cookie
sozinho, um site de fora poderia tentar um POST em nome da pessoa (CSRF): todo POST com o cookie exige
o cabeçalho `X-TickerLab-Pedido: 1` (que um site de fora não consegue pôr sem a permissão de CORS, que
a API não dá) e a origem do próprio site.
"""

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from src import api
from src.api_v1 import VARIAVEL_DA_CHAVE, acesso, sessao
from src.banco import sessoes
from src.banco.modelo import sessoes_de_login
from src.banco.usuarios import apagar_conta, buscar_por_google_sub, entrar
from src.conformidade import VERSAO_DOS_TERMOS, registrar_aceite
from tests.ajudantes_da_api import (
    AGORA,
    CLIENT_ID,
    chaves_publicas,
    com_token,
    gerar_chave,
    token,
)

DO_SITE = {"X-TickerLab-Pedido": "1", "Origin": "http://testserver"}
TRINTA_DIAS = 30 * 24 * 3600


@pytest.fixture(scope="module")
def chave():
    return gerar_chave()


@pytest.fixture
def cliente(banco, monkeypatch, chave):
    monkeypatch.setenv(VARIAVEL_DA_CHAVE, "1")
    monkeypatch.setenv(acesso.VARIAVEL_DO_CLIENT_ID, CLIENT_ID)
    monkeypatch.setattr(acesso, "agora", lambda: AGORA)
    app = api.criar_app({VARIAVEL_DA_CHAVE: "1"})
    app.dependency_overrides[acesso.chaves_do_google] = lambda: chaves_publicas(chave)
    acesso.LIMITE.zerar()
    return TestClient(app)


@pytest.fixture
def ana(banco):
    with banco.begin() as conexao:
        usuario = entrar(
            conexao, "ana", "ana@exemplo.com", "Ana", email_confirmado=True
        )[0]
        registrar_aceite(conexao, usuario.id)
    return usuario


def _sessao_da(banco, conta) -> str:
    with banco.begin() as conexao:
        return sessoes.abrir(conexao, conta.id, "google")


def _com_cookie(token_da_sessao: str, **extra: str) -> dict[str, str]:
    # o TestClient fala HTTP; um cookie Secure guardado por ele não voltaria: vai no cabeçalho
    return {"Cookie": f"{sessao.NOME_DO_COOKIE}={token_da_sessao}", **extra}


def _cookie_posto(resposta) -> str:
    (posto,) = [
        c
        for c in resposta.headers.get_list("set-cookie")
        if c.startswith(sessao.NOME_DO_COOKIE)
    ]
    return posto


# --- abrir a sessão ------------------------------------------------------------------------


def test_cookie_tem_as_flags(cliente, ana, chave):
    resposta = cliente.post("/api/v1/conta", headers=com_token(token(chave)))
    assert resposta.status_code == 200
    posto = _cookie_posto(resposta)
    atributos = {a.strip().split("=")[0].lower() for a in posto.split(";")[1:]}
    assert {"httponly", "secure", "path", "max-age", "samesite"} <= atributos
    assert "samesite=lax" in posto.lower() and "path=/" in posto.lower()
    assert f"max-age={TRINTA_DIAS}" in posto.lower()
    # __Host-: sem Domain (o cookie fica só no endereço que o pôs)
    assert "domain" not in atributos
    assert sessao.NOME_DO_COOKIE == "__Host-tl_sessao"


def test_o_token_do_cookie_abre_a_conta_e_o_banco_so_tem_o_hash(
    cliente, ana, chave, banco
):
    resposta = cliente.post("/api/v1/conta", headers=com_token(token(chave)))
    valor = _cookie_posto(resposta).split(";")[0].split("=", 1)[1]
    with banco.connect() as conexao:
        linha = conexao.execute(sa.select(sessoes_de_login)).one()
    assert valor not in str(tuple(linha)) and linha.usuario_id == ana.id
    eu = cliente.get("/api/v1/eu", headers=_com_cookie(valor))
    assert eu.status_code == 200 and eu.json()["nome"] == "Ana"


def test_entrar_de_novo_troca_a_sessao_e_exige_o_pedido_do_site(
    cliente, ana, chave, banco
):
    antiga = _sessao_da(banco, ana)
    de_fora = cliente.post(
        "/api/v1/conta", headers=_com_cookie(antiga, **com_token(token(chave)))
    )
    assert de_fora.status_code == 403
    resposta = cliente.post(
        "/api/v1/conta",
        headers=_com_cookie(antiga, **com_token(token(chave)), **DO_SITE),
    )
    assert resposta.status_code == 200
    # a sessão que o navegador tinha acaba; fica só a nova
    assert cliente.get("/api/v1/eu", headers=_com_cookie(antiga)).status_code == 401
    with banco.connect() as conexao:
        abertas = conexao.execute(
            sa.select(sessoes_de_login).where(sessoes_de_login.c.encerrada_em.is_(None))
        ).all()
    assert len(abertas) == 1


def test_conta_nova_pelo_google_ja_sai_com_a_sessao(cliente, chave, banco):
    resposta = cliente.post(
        "/api/v1/conta",
        headers=com_token(token(chave, sub="carla", email="carla@exemplo.com")),
    )
    assert resposta.status_code == 200 and resposta.json()["primeira_vez"]
    with banco.connect() as conexao:
        carla = buscar_por_google_sub(conexao, "carla")
        dela = conexao.execute(
            sa.select(sessoes_de_login.c.usuario_id, sessoes_de_login.c.provedor)
        ).one()
    assert tuple(dela) == (carla.id, "google")


# --- usar a sessão -------------------------------------------------------------------------


def test_eu_so_com_o_cookie(cliente, ana, banco):
    resposta = cliente.get("/api/v1/eu", headers=_com_cookie(_sessao_da(banco, ana)))
    assert resposta.status_code == 200 and resposta.json()["nome"] == "Ana"


def test_sem_cookie_nem_token_continua_401(cliente, ana):
    resposta = cliente.get("/api/v1/eu")
    assert resposta.status_code == 401
    assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "sem-token"


def test_cookie_desconhecido_recebe_401_de_sessao(cliente, ana):
    resposta = cliente.get("/api/v1/eu", headers=_com_cookie("inventado"))
    assert resposta.status_code == 401
    assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "sessao"


def test_sessao_vencida(cliente, ana, banco):
    valor = _sessao_da(banco, ana)
    with banco.begin() as conexao:
        conexao.execute(
            sa.update(sessoes_de_login).values(
                expira_em=datetime.now(UTC) - timedelta(minutes=1)
            )
        )
    resposta = cliente.get("/api/v1/eu", headers=_com_cookie(valor))
    assert resposta.status_code == 401
    assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "sessao"


def test_sessao_de_uma_conta_nao_abre_outra(cliente, ana, banco):
    with banco.begin() as conexao:
        bia = entrar(conexao, "bia", "bia@exemplo.com", "Bia")[0]
        registrar_aceite(conexao, bia.id)
    da_ana, da_bia = _sessao_da(banco, ana), _sessao_da(banco, bia)
    assert (
        cliente.get("/api/v1/eu", headers=_com_cookie(da_ana)).json()["nome"] == "Ana"
    )
    assert (
        cliente.get("/api/v1/eu", headers=_com_cookie(da_bia)).json()["nome"] == "Bia"
    )


def test_o_bearer_do_google_nao_vale_mais_fora_do_login(cliente, ana, chave):
    """R5: o token do Google só abre a sessão (`POST /v1/conta`); nas outras rotas não vale."""
    resposta = cliente.get("/api/v1/eu", headers=com_token(token(chave)))
    assert resposta.status_code == 401
    assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "sem-token"


def test_apagar_conta_encerra_as_sessoes(cliente, ana, banco):
    valor = _sessao_da(banco, ana)
    with banco.begin() as conexao:
        apagar_conta(conexao, ana.id)
    assert cliente.get("/api/v1/eu", headers=_com_cookie(valor)).status_code == 401


# --- CSRF: POST com o cookie ---------------------------------------------------------------


def _aceitar(cliente, cabecalhos):
    return cliente.post(
        "/api/v1/aceite-dos-termos",
        headers=cabecalhos,
        json={"versao": VERSAO_DOS_TERMOS},
    )


def test_post_do_proprio_site_passa(cliente, ana, banco):
    resposta = _aceitar(cliente, _com_cookie(_sessao_da(banco, ana), **DO_SITE))
    assert resposta.status_code == 200


def test_post_sem_cabecalho_recusado(cliente, ana, banco):
    resposta = _aceitar(
        cliente, _com_cookie(_sessao_da(banco, ana), Origin="http://testserver")
    )
    assert resposta.status_code == 403
    assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "pedido-de-fora"


@pytest.mark.parametrize(
    "origem",
    [
        "https://site-malicioso.com",
        "http://testserver.site-malicioso.com",
        "null",
        None,
    ],
)
def test_post_de_outra_origem_recusado(cliente, ana, banco, origem):
    cabecalhos = _com_cookie(_sessao_da(banco, ana), **{"X-TickerLab-Pedido": "1"})
    if origem is not None:
        cabecalhos["Origin"] = origem
    resposta = _aceitar(cliente, cabecalhos)
    assert resposta.status_code == 403
    assert resposta.headers[acesso.CABECALHO_DO_MOTIVO] == "pedido-de-fora"


def test_vale_o_host_do_pedido_e_nao_o_x_forwarded_host(cliente, ana, banco):
    """R4 (revisão de 19/10): a origem se compara com o Host; o X-Forwarded-Host é ignorado."""
    valor = _sessao_da(banco, ana)
    do_host = _com_cookie(
        valor,
        **{
            "X-TickerLab-Pedido": "1",
            "Origin": "https://app.tickerlab.com.br",
            "Host": "app.tickerlab.com.br",
        },
    )
    assert _aceitar(cliente, do_host).status_code == 200
    forjado = _com_cookie(
        valor,
        **{
            "X-TickerLab-Pedido": "1",
            "Origin": "https://atacante.exemplo",
            "X-Forwarded-Host": "atacante.exemplo",
        },
    )
    assert _aceitar(cliente, forjado).status_code == 403


def test_get_com_o_cookie_nao_precisa_do_cabecalho(cliente, ana, banco):
    """Ler não muda nada (e um site de fora não lê a resposta sem CORS)."""
    resposta = cliente.get("/api/v1/eu", headers=_com_cookie(_sessao_da(banco, ana)))
    assert resposta.status_code == 200


# --- sair ----------------------------------------------------------------------------------


def test_sair_encerra_a_sessao(cliente, ana, banco):
    valor = _sessao_da(banco, ana)
    resposta = cliente.post("/api/v1/sair", headers=_com_cookie(valor, **DO_SITE))
    assert resposta.status_code == 204
    # o cookie é apagado no navegador e a sessão, no banco
    apagado = _cookie_posto(resposta).lower()
    assert "max-age=0" in apagado or "expires=thu, 01 jan 1970" in apagado
    assert cliente.get("/api/v1/eu", headers=_com_cookie(valor)).status_code == 401


def test_sair_de_fora_do_site_nao_encerra(cliente, ana, banco):
    valor = _sessao_da(banco, ana)
    resposta = cliente.post("/api/v1/sair", headers=_com_cookie(valor))
    assert resposta.status_code == 403
    assert cliente.get("/api/v1/eu", headers=_com_cookie(valor)).status_code == 200


def test_sair_sem_sessao_nao_e_erro(cliente):
    assert cliente.post("/api/v1/sair", headers=DO_SITE).status_code == 204
