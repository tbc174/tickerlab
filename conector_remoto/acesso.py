"""Quem é o analista: a chave da API dele, conferida na própria API (`/catalog`).

Entrada provisória do PR 1: a IA manda `Authorization: Bearer <chave tld_...>`. O PR 2 troca a entrada
pelo OAuth (o token passa a levar a chave cifrada), e o resto do conector não muda: as ferramentas só
leem o `AcessoDoAnalista` do pedido.

O catálogo de cada chave fica 60 s na memória do processo, para a lista de ferramentas não gastar um
pedido do minuto da organização a cada mensagem. Uma chave revogada continua na lista por esse tempo,
mas nada sai: cada ferramenta chama a API com a chave, e a API recusa na hora.
"""

import hashlib
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from pydantic import Field

from conector_remoto.cliente_api import ClienteDaApi

# o mesmo formato de `src/chaves_da_api.FORMATO` (um teste confere): o grupo é o id público da chave
FORMATO_DA_CHAVE = re.compile(r"tld_([a-z2-7]{8})_[A-Za-z0-9_-]{43}")
CLIENTE_DA_ENTRADA_DIRETA = "chave-direta"
VALIDADE_DO_CATALOGO_S = 60.0
MAXIMO_NA_MEMORIA = 1_000


class AcessoDoAnalista(AccessToken):
    """O token do pedido, com a chave da API do analista e os conjuntos que ela pode ver."""

    # na entrada direta do PR 1 o token é a própria chave: nenhum dos dois aparece no repr (nem no log)
    token: str = Field(repr=False)
    chave_da_api: str = Field(repr=False)
    conjuntos: frozenset[str] = frozenset()


@dataclass(frozen=True)
class _Guardado:
    acesso: AcessoDoAnalista
    vence_em: float


def id_da_chave(chave: str) -> str | None:
    """O id público da chave (`tld_xxxxxxxx`), que pode ir para o log; None se não é uma chave."""
    achado = FORMATO_DA_CHAVE.fullmatch(chave)
    return f"tld_{achado.group(1)}" if achado else None


def conjuntos_do_catalogo(corpo: object) -> frozenset[str]:
    """Os conjuntos que o catálogo da chave lista (`datasets[].dataset`)."""
    if not isinstance(corpo, dict) or not isinstance(corpo.get("datasets"), list):
        return frozenset()
    return frozenset(
        item["dataset"]
        for item in corpo["datasets"]
        if isinstance(item, dict) and isinstance(item.get("dataset"), str)
    )


class VerificadorDeChave:
    """O `TokenVerifier` do MCP: aceita a chave que a API aceita no `/catalog`."""

    def __init__(
        self,
        cliente: ClienteDaApi,
        recurso: str,
        *,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cliente = cliente
        self._recurso = recurso
        self._relogio = relogio
        self._memoria: dict[str, _Guardado] = {}

    def _lembrar(self, impressao: str, acesso: AcessoDoAnalista) -> None:
        agora = self._relogio()
        if len(self._memoria) >= MAXIMO_NA_MEMORIA:
            self._memoria = {
                k: g for k, g in self._memoria.items() if g.vence_em > agora
            }
        while len(self._memoria) >= MAXIMO_NA_MEMORIA:
            del self._memoria[next(iter(self._memoria))]
        self._memoria[impressao] = _Guardado(acesso, agora + VALIDADE_DO_CATALOGO_S)

    async def verify_token(self, token: str) -> AccessToken | None:
        """O acesso do analista, ou None (a IA recebe 401 com o ponteiro do OAuth)."""
        identificador = id_da_chave(token)
        if identificador is None:
            return None
        # a memória é indexada pelo hash: a chave não vira chave de dicionário
        impressao = hashlib.sha256(token.encode()).hexdigest()
        guardado = self._memoria.get(impressao)
        if guardado is not None and guardado.vence_em > self._relogio():
            return guardado.acesso
        resposta = await self._cliente.get(token, "/catalog")
        if not resposta.ok:
            self._memoria.pop(impressao, None)
            return None
        acesso = AcessoDoAnalista(
            token=token,
            client_id=CLIENTE_DA_ENTRADA_DIRETA,
            scopes=[],
            resource=self._recurso,
            subject=identificador,
            chave_da_api=token,
            conjuntos=conjuntos_do_catalogo(resposta.corpo),
        )
        self._lembrar(impressao, acesso)
        return acesso


def acesso_do_pedido() -> AcessoDoAnalista | None:
    """O acesso do analista que fez este pedido (None fora de um pedido autenticado)."""
    token = get_access_token()
    return token if isinstance(token, AcessoDoAnalista) else None
