"""Registro de acesso da API: IP real, hora, pedido, código e navegador, num arquivo que sobrevive ao deploy.

O Marco Civil da Internet (art. 15) manda guardar os registros de acesso à aplicação por 6 meses,
sob sigilo. O uvicorn só enxerga o endereço do gateway do Docker; o IP do visitante chega nos
cabeçalhos da Cloudflare. Esses cabeçalhos qualquer um forja, então só valem quando o pedido
vem de um proxy confiável (`TICKERLAB_PROXIES_CONFIAVEIS`, lista de IPs ou redes separados por
vírgula; vazia = nenhum cabeçalho vale).

Regras da política de privacidade (linha "sessões de login ... sem endereço IP em nenhum momento"):
o IP vai **só** para este arquivo, nunca para o banco, e a linha não leva e-mail, nome, `usuario_id`
nem a query string (o link de descadastro leva um código que vale como senha).
"""

import ipaddress
import json
import logging
import os
from collections.abc import Awaitable, Callable, Iterable, Mapping, MutableMapping
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)

VARIAVEL_DO_ARQUIVO = "TICKERLAB_REGISTRO_DE_ACESSO"
VARIAVEL_DOS_PROXIES = "TICKERLAB_PROXIES_CONFIAVEIS"
CABECALHO_DA_CLOUDFLARE = "cf-connecting-ip"
CABECALHO_ENCADEADO = "x-forwarded-for"
TAMANHO_MAXIMO_DO_NAVEGADOR = (
    200  # caracteres: o suficiente para identificar, sem encher o disco
)

Rede = ipaddress.IPv4Network | ipaddress.IPv6Network

# tipos do ASGI escritos aqui: o starlette não está no requirements-prod.txt (vem junto do fastapi)
Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def ler_proxies_confiaveis(texto: str | None) -> tuple[Rede, ...]:
    """Lê a lista de IPs/redes de proxies; entrada inválida é ignorada (e avisada), nunca confiada."""
    redes: list[Rede] = []
    for parte in (texto or "").split(","):
        parte = parte.strip()
        if not parte:
            continue
        try:
            redes.append(ipaddress.ip_network(parte, strict=False))
        except ValueError:
            log.warning(
                "%s: entrada ignorada por não ser IP nem rede", VARIAVEL_DOS_PROXIES
            )
    return tuple(redes)


def _como_ip(texto: str) -> str | None:
    try:
        return str(ipaddress.ip_address(texto.strip()))
    except ValueError:
        return None


def ip_do_cliente(
    origem: str | None, cabecalhos: Mapping[str, str], confiaveis: Iterable[Rede]
) -> str:
    """O IP do visitante: dos cabeçalhos só se `origem` (quem abriu a conexão) é proxy confiável.

    Usa o `CF-Connecting-IP`; sem ele, o último da cadeia `X-Forwarded-For` (o proxy confiável
    acrescenta o endereço que viu ao fim, então o que veio antes pode ter sido forjado).
    """
    ip_de_origem = _como_ip(origem or "")
    if ip_de_origem is None:
        return "desconhecido"
    endereco = ipaddress.ip_address(ip_de_origem)
    if not any(endereco in rede for rede in confiaveis):
        return ip_de_origem
    direto = _como_ip(cabecalhos.get(CABECALHO_DA_CLOUDFLARE, ""))
    if direto:
        return direto
    cadeia = cabecalhos.get(CABECALHO_ENCADEADO, "").split(",")
    return _como_ip(cadeia[-1]) or ip_de_origem


def escrever_no_arquivo(caminho: str) -> Callable[[str], None]:
    """Acrescenta uma linha por vez (abrir a cada linha deixa o logrotate trocar o arquivo à vontade).

    Falha ao gravar vai para o log comum e nunca derruba o pedido do visitante.
    """

    def escrever(linha: str) -> None:
        try:
            with open(caminho, "a", encoding="utf-8") as arquivo:
                arquivo.write(linha + "\n")
        except OSError:
            log.exception("Não consegui gravar o registro de acesso")

    return escrever


def montar_linha(
    ip: str, metodo: str, caminho: str, status: int, navegador: str
) -> str:
    return json.dumps(
        {
            "hora": datetime.now(UTC).isoformat(timespec="seconds"),
            "ip": ip,
            "metodo": metodo,
            "caminho": caminho,
            "status": status,
            "navegador": navegador[:TAMANHO_MAXIMO_DO_NAVEGADOR],
        },
        ensure_ascii=False,
    )


class RegistroDeAcesso:
    """Middleware ASGI: uma linha de registro por pedido HTTP, depois de a resposta começar."""

    def __init__(
        self,
        app: ASGIApp,
        escrever: Callable[[str], None],
        confiaveis: Iterable[Rede] = (),
    ) -> None:
        self.app = app
        self.escrever = escrever
        self.confiaveis = tuple(confiaveis)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        status = 500  # se a rota quebrar antes de responder, o cliente recebe 500

        async def enviar(mensagem: Message) -> None:
            nonlocal status
            if mensagem["type"] == "http.response.start":
                status = mensagem["status"]
            await send(mensagem)

        try:
            await self.app(scope, receive, enviar)
        finally:
            self._registrar(scope, status)

    def _registrar(self, scope: Scope, status: int) -> None:
        cabecalhos = {
            chave.decode("latin-1").lower(): valor.decode("latin-1")
            for chave, valor in scope.get("headers", [])
        }
        cliente = scope.get("client")
        ip = ip_do_cliente(cliente[0] if cliente else None, cabecalhos, self.confiaveis)
        self.escrever(
            montar_linha(
                ip,
                scope["method"],
                scope["path"],  # sem a query string, de propósito
                status,
                cabecalhos.get("user-agent", ""),
            )
        )


def proxies_pelo_ambiente(
    ambiente: Mapping[str, str] | None = None,
) -> tuple[Rede, ...]:
    """Os proxies confiáveis da configuração (vazio = nenhum cabeçalho de IP vale)."""
    ambiente = os.environ if ambiente is None else ambiente
    return ler_proxies_confiaveis(ambiente.get(VARIAVEL_DOS_PROXIES))


def registro_pelo_ambiente(
    ambiente: Mapping[str, str] | None = None,
) -> tuple[Callable[[str], None], tuple[Rede, ...]] | None:
    """O que o `criar_app` precisa para ligar o registro, ou None se o arquivo não foi configurado."""
    ambiente = os.environ if ambiente is None else ambiente
    caminho = ambiente.get(VARIAVEL_DO_ARQUIVO, "").strip()
    if not caminho:
        return None
    return escrever_no_arquivo(caminho), proxies_pelo_ambiente(ambiente)
