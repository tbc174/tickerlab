"""Ajudantes dos testes do conector remoto (linha 570): o app de pé e os pedidos JSON-RPC do MCP.

O conector roda de verdade (`conector_remoto.servidor.criar_app`), com o lifespan, num `TestClient`; a API
do outro lado é ou um dublê (`httpx.MockTransport`) ou o app de verdade da API externa
(`httpx.ASGITransport`), sem rede.
"""

import json
from collections.abc import Generator
from contextlib import contextmanager

import httpx
from starlette.testclient import TestClient

from conector_remoto.configuracao import ler_configuracao
from conector_remoto.servidor import criar_app

HOST = "mcp.tickerlab.com.br"
URL_PUBLICA = f"https://{HOST}"
# uma chave com o formato certo, de ninguém (só vale contra o dublê da API)
CHAVE_DE_MENTIRA = "tld_abcdefgh_" + "A" * 43
VERSAO_DO_PROTOCOLO = "2025-06-18"
CABECALHOS = {
    "Host": HOST,
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
    "MCP-Protocol-Version": VERSAO_DO_PROTOCOLO,
}


@contextmanager
def conector(
    transporte: httpx.AsyncBaseTransport,
    ambiente: dict[str, str] | None = None,
    ip: str = "203.0.113.10",
) -> Generator[TestClient]:
    """O conector com a configuração de produção, falando com a API pelo `transporte`; os pedidos
    chegam do endereço `ip` (por padrão, um IP de fora, da faixa de documentação)."""
    app = criar_app(ler_configuracao(ambiente or {}), transporte)
    with TestClient(app, base_url=URL_PUBLICA, client=(ip, 50000)) as cliente:
        yield cliente


def com_chave(chave: str) -> dict[str, str]:
    return CABECALHOS | {"Authorization": f"Bearer {chave}"}


def rpc(
    cliente: TestClient, chave: str | None, metodo: str, parametros: dict | None = None
):
    """Um pedido JSON-RPC ao `/mcp`; devolve a resposta HTTP."""
    corpo: dict[str, object] = {"jsonrpc": "2.0", "id": 1, "method": metodo}
    if parametros is not None:
        corpo["params"] = parametros
    cabecalhos = com_chave(chave) if chave else CABECALHOS
    return cliente.post("/mcp", json=corpo, headers=cabecalhos)


def nomes_das_ferramentas(cliente: TestClient, chave: str) -> list[str]:
    resposta = rpc(cliente, chave, "tools/list")
    assert resposta.status_code == 200, resposta.text
    return sorted(f["name"] for f in resposta.json()["result"]["tools"])


def chamar(
    cliente: TestClient, chave: str, ferramenta: str, /, **argumentos
) -> tuple[bool, str]:
    """Chama a ferramenta; devolve (deu erro?, texto da resposta)."""
    resposta = rpc(
        cliente, chave, "tools/call", {"name": ferramenta, "arguments": argumentos}
    )
    assert resposta.status_code == 200, resposta.text
    resultado = resposta.json()["result"]
    (conteudo,) = resultado["content"]
    return resultado["isError"], conteudo["text"]


def chamar_ok(
    cliente: TestClient, chave: str, ferramenta: str, /, **argumentos
) -> object:
    """Chama a ferramenta e devolve o JSON que ela entregou (falha o teste se deu erro)."""
    erro, texto = chamar(cliente, chave, ferramenta, **argumentos)
    assert not erro, texto
    return json.loads(texto)


def api_de_mentira(
    rotas: dict[str, httpx.Response],
    conjuntos: tuple[str, ...] = (
        "prospecting",
        "profiles",
        "companies",
        "comparables",
        "financials",
        "sectors",
        "funds",
    ),
    pedidos: list[httpx.Request] | None = None,
) -> httpx.MockTransport:
    """Um dublê da API: aceita só a `CHAVE_DE_MENTIRA`, lista `conjuntos` no catálogo e responde
    `rotas[caminho]` (404 `not_available` para o resto). Guarda os pedidos em `pedidos`."""

    def responder(pedido: httpx.Request) -> httpx.Response:
        if pedidos is not None:
            pedidos.append(pedido)
        if pedido.headers.get("authorization") != f"Bearer {CHAVE_DE_MENTIRA}":
            return httpx.Response(401, json={"detail": "invalid_api_key"})
        if pedido.url.path == "/data/v1/catalog":
            return httpx.Response(
                200,
                json={"datasets": [{"dataset": c} for c in conjuntos], "sources": []},
            )
        caminho = pedido.url.path.removeprefix("/data/v1")
        if caminho in rotas:
            return rotas[caminho]
        return httpx.Response(404, json={"detail": "not_available"})

    return httpx.MockTransport(responder)
