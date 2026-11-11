"""Ajudantes dos testes do OAuth do conector (linha 570, PR 2): o caminho que o Claude e o ChatGPT fazem.

Registro (DCR) → `/authorize` → página `/autorizar` (GET e POST com a chave) → volta com o código →
`/token`. Cada passo é uma função pequena, para os testes poderem estragar um passo de cada vez.
"""

import base64
import hashlib
import re
import secrets
from urllib.parse import parse_qs, urlsplit

import httpx
from starlette.testclient import TestClient

from tests.ajudantes_do_conector import CABECALHOS, URL_PUBLICA

VOLTA_DO_CLAUDE = "https://claude.ai/api/mcp/auth_callback"
VOLTA_DO_CHATGPT = "https://chatgpt.com/connector_platform_oauth_redirect"
VOLTA_DO_CHATGPT_POR_ID = "https://chatgpt.com/connector/oauth/AbC_123-x"
RECURSO = f"{URL_PUBLICA}/mcp"
# duas chaves de formato certo, de ninguém: cada uma é de uma organização do dublê da API
CHAVE_A = "tld_aaaaaaaa_" + "A" * 43
CHAVE_B = "tld_bbbbbbbb_" + "B" * 43
CONJUNTOS_A = ("companies", "financials")
CONJUNTOS_B = ("sectors",)


class ApiComChaves:
    """Dublê da API com chaves que podem ser revogadas no meio do teste, ou com a API fora do ar."""

    def __init__(self) -> None:
        self.chaves: dict[str, tuple[str, ...]] = {
            CHAVE_A: CONJUNTOS_A,
            CHAVE_B: CONJUNTOS_B,
        }
        self.fora_do_ar = False
        self.pedidos: list[httpx.Request] = []

    def revogar(self, chave: str) -> None:
        del self.chaves[chave]

    def _responder(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append(pedido)
        if self.fora_do_ar:
            raise httpx.ConnectError("API fora do ar", request=pedido)
        chave = pedido.headers.get("authorization", "").removeprefix("Bearer ")
        if chave not in self.chaves:
            return httpx.Response(401, json={"detail": "invalid_api_key"})
        if pedido.url.path == "/data/v1/catalog":
            conjuntos = [{"dataset": c} for c in self.chaves[chave]]
            return httpx.Response(200, json={"datasets": conjuntos, "sources": []})
        return httpx.Response(404, json={"detail": "not_available"})

    @property
    def transporte(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._responder)


def pkce() -> tuple[str, str]:
    """(verificador, desafio S256)."""
    verificador = secrets.token_urlsafe(48)
    desafio = (
        base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest())
        .decode()
        .rstrip("=")
    )
    return verificador, desafio


def registrar(
    cliente: TestClient, *enderecos: str, metodo: str = "none"
) -> httpx.Response:
    corpo = {
        "redirect_uris": list(enderecos or (VOLTA_DO_CLAUDE,)),
        "token_endpoint_auth_method": metodo,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "client_name": "Claude",
    }
    return cliente.post("/register", json=corpo, headers={"Host": CABECALHOS["Host"]})


def registrar_ok(cliente: TestClient, *enderecos: str, metodo: str = "none") -> dict:
    resposta = registrar(cliente, *enderecos, metodo=metodo)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def autorizar(
    cliente: TestClient,
    client_id: str,
    desafio: str | None,
    *,
    volta: str = VOLTA_DO_CLAUDE,
    state: str = "estado-1",
    recurso: str | None = RECURSO,
) -> httpx.Response:
    parametros = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": volta,
        "state": state,
        "code_challenge_method": "S256",
    }
    if desafio is not None:
        parametros["code_challenge"] = desafio
    if recurso is not None:
        parametros["resource"] = recurso
    return cliente.get("/authorize", params=parametros, follow_redirects=False)


def endereco_da_pagina(
    cliente: TestClient, client_id: str, desafio: str, **opcoes
) -> str:
    resposta = autorizar(cliente, client_id, desafio, **opcoes)
    assert resposta.status_code == 302, resposta.text
    local = resposta.headers["location"]
    assert local.startswith(f"{URL_PUBLICA}/autorizar?pedido="), local
    return local


def campos_da_pagina(html: str) -> tuple[str, str]:
    """(pedido selado, csrf) dos campos escondidos do formulário."""
    pedido = re.search(r'name="pedido" value="([^"]+)"', html)
    csrf = re.search(r'name="csrf" value="([^"]+)"', html)
    assert pedido and csrf, html
    return pedido.group(1), csrf.group(1)


def abrir_pagina(cliente: TestClient, endereco: str) -> tuple[httpx.Response, str, str]:
    resposta = cliente.get(endereco.removeprefix(URL_PUBLICA))
    assert resposta.status_code == 200, resposta.text
    pedido, csrf = campos_da_pagina(resposta.text)
    return resposta, pedido, csrf


def enviar_chave(
    cliente: TestClient,
    pedido: str,
    csrf: str,
    chave: str,
    *,
    acao: str = "ligar",
    cabecalhos: dict[str, str] | None = None,
) -> httpx.Response:
    return cliente.post(
        "/autorizar",
        data={"pedido": pedido, "csrf": csrf, "chave": chave, "acao": acao},
        headers=cabecalhos,
        follow_redirects=False,
    )


def parametros_da_volta(endereco: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(endereco).query).items()}


def codigo_para(
    cliente: TestClient,
    chave: str,
    *,
    volta: str = VOLTA_DO_CLAUDE,
    metodo: str = "none",
) -> tuple[dict, str, str]:
    """Registra, autoriza e cola a chave; devolve (cliente registrado, código, verificador PKCE)."""
    registrado = registrar_ok(cliente, volta, metodo=metodo)
    verificador, desafio = pkce()
    endereco = endereco_da_pagina(
        cliente, registrado["client_id"], desafio, volta=volta
    )
    _, pedido, csrf = abrir_pagina(cliente, endereco)
    resposta = enviar_chave(cliente, pedido, csrf, chave)
    assert resposta.status_code == 303, resposta.text
    volta_com_codigo = resposta.headers["location"]
    assert volta_com_codigo.startswith(volta)
    return registrado, parametros_da_volta(volta_com_codigo)["code"], verificador


def trocar_codigo(
    cliente: TestClient,
    registrado: dict,
    codigo: str,
    verificador: str,
    *,
    volta: str = VOLTA_DO_CLAUDE,
) -> httpx.Response:
    corpo = {
        "grant_type": "authorization_code",
        "code": codigo,
        "redirect_uri": volta,
        "client_id": registrado["client_id"],
        "code_verifier": verificador,
        "resource": RECURSO,
    }
    if registrado.get("client_secret"):
        corpo["client_secret"] = registrado["client_secret"]
    return cliente.post("/token", data=corpo)


def renovar(cliente: TestClient, registrado: dict, renovacao: str) -> httpx.Response:
    corpo = {
        "grant_type": "refresh_token",
        "refresh_token": renovacao,
        "client_id": registrado["client_id"],
        "resource": RECURSO,
    }
    if registrado.get("client_secret"):
        corpo["client_secret"] = registrado["client_secret"]
    return cliente.post("/token", data=corpo)


def tokens_para(cliente: TestClient, chave: str, **opcoes) -> tuple[dict, dict]:
    """O caminho inteiro; devolve (cliente registrado, resposta do /token)."""
    registrado, codigo, verificador = codigo_para(cliente, chave, **opcoes)
    resposta = trocar_codigo(
        cliente,
        registrado,
        codigo,
        verificador,
        volta=opcoes.get("volta", VOLTA_DO_CLAUDE),
    )
    assert resposta.status_code == 200, resposta.text
    return registrado, resposta.json()
