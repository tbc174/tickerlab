"""O cliente da API externa (`/data/v1`): um GET com a chave do analista, sem ecoar a chave.

Uma conexão por pedido (o conector não guarda estado entre pedidos). O transporte é injetável para os
testes chamarem o app de verdade da API sem rede (`httpx.ASGITransport`).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import httpx

PREFIXO = "/data/v1"
STATUS_OK = 200
ParametroDaApi = str | int | bool | Sequence[str] | None


@dataclass(frozen=True)
class RespostaDaApi:
    """O que a API respondeu: o status, o JSON (ou None) e o Retry-After, quando veio."""

    status: int
    corpo: object
    espera_s: int | None = None

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK

    @property
    def codigo(self) -> str | None:
        """O código do erro da API (`{"detail": "not_available"}` → `not_available`), se houver."""
        if isinstance(self.corpo, dict) and isinstance(self.corpo.get("detail"), str):
            return self.corpo["detail"]
        return None


def _espera(resposta: httpx.Response) -> int | None:
    valor = resposta.headers.get("Retry-After", "")
    return int(valor) if valor.isascii() and valor.isdigit() else None


def _corpo(resposta: httpx.Response) -> object:
    try:
        return resposta.json()
    except ValueError:
        return None


def _parametros(parametros: Mapping[str, ParametroDaApi]) -> dict[str, object]:
    # o que não foi pedido (None, lista vazia) não vai na URL: a API usa o padrão dela
    return {
        nome: (str(valor).lower() if isinstance(valor, bool) else valor)
        for nome, valor in parametros.items()
        if valor is not None and valor != [] and valor != ()
    }


class ClienteDaApi:
    """Chama a API externa em `url_base` (ex.: `http://tickerlab-api:8000`)."""

    def __init__(
        self,
        url_base: str,
        *,
        tempo_limite_s: float,
        transporte: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url_base = url_base.rstrip("/")
        self._tempo_limite_s = tempo_limite_s
        self._transporte = transporte

    async def get(
        self,
        chave: str,
        caminho: str,
        parametros: Mapping[str, ParametroDaApi] | None = None,
    ) -> RespostaDaApi:
        """GET `/data/v1{caminho}` com a chave no cabeçalho (nunca na URL)."""
        async with httpx.AsyncClient(
            base_url=self._url_base,
            transport=self._transporte,
            timeout=self._tempo_limite_s,
            follow_redirects=False,
        ) as cliente:
            resposta = await cliente.get(
                f"{PREFIXO}{caminho}",
                params=_parametros(parametros or {}),
                headers={"Authorization": f"Bearer {chave}"},
            )
        return RespostaDaApi(resposta.status_code, _corpo(resposta), _espera(resposta))
