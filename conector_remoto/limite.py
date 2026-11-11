"""De quem é o pedido (o IP de verdade atrás do túnel) e o limite de tentativas por IP.

O conector só é alcançado pelo túnel da Cloudflare: a porta fica em `127.0.0.1` do VPS e o `cloudflared`
entrega o pedido com o IP de quem chamou em `CF-Connecting-IP`. Esse cabeçalho só vale quando o pedido
chega de um endereço da lista de confiança (o próprio VPS e a rede do Compose); vindo de qualquer outro
lugar ele é ignorado, e conta o endereço da conexão (senão bastaria forjar o cabeçalho para fugir do
limite ou culpar outro IP).
"""

import ipaddress
import time
from collections import deque
from collections.abc import Callable, Iterable

from starlette.requests import Request

CABECALHO_DO_TUNEL = "cf-connecting-ip"
# o VPS (cloudflared no host) e as redes privadas que o Docker usa para o Compose
REDES_CONFIAVEIS_PADRAO = ("127.0.0.0/8", "::1/128", "172.16.0.0/12")
SEM_ENDERECO = "desconhecido"
Rede = ipaddress.IPv4Network | ipaddress.IPv6Network


def redes(textos: Iterable[str]) -> tuple[Rede, ...]:
    """As redes da lista de confiança (`10.0.0.0/8`, `::1/128`...)."""
    return tuple(
        ipaddress.ip_network(t.strip(), strict=False) for t in textos if t.strip()
    )


def _ip(texto: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(texto.strip())
    except ValueError:
        return None


def ip_do_pedido(pedido: Request, confiaveis: tuple[Rede, ...]) -> str:
    """O IP de quem fez o pedido: o do túnel, se o pedido veio do túnel; senão, o da conexão."""
    conexao = pedido.client.host if pedido.client else ""
    endereco = _ip(conexao)
    if endereco is None:
        return conexao or SEM_ENDERECO
    if any(endereco in rede for rede in confiaveis):
        do_tunel = _ip(pedido.headers.get(CABECALHO_DO_TUNEL, ""))
        if do_tunel is not None:
            return str(do_tunel)
    return str(endereco)


class LimitePorIp:
    """No máximo `maximo` falhas por IP numa janela de `janela_s` segundos (memória do processo)."""

    def __init__(
        self,
        maximo: int,
        janela_s: float,
        *,
        relogio: Callable[[], float] = time.monotonic,
        maximo_de_ips: int = 10_000,
    ) -> None:
        self._maximo = maximo
        self._janela_s = janela_s
        self._relogio = relogio
        self._maximo_de_ips = maximo_de_ips
        self._falhas: dict[str, deque[float]] = {}

    def _recentes(self, ip: str) -> deque[float]:
        limite = self._relogio() - self._janela_s
        falhas = self._falhas.get(ip, deque())
        while falhas and falhas[0] <= limite:
            falhas.popleft()
        return falhas

    def bloqueado(self, ip: str) -> bool:
        """Se o IP já gastou as tentativas da janela."""
        return len(self._recentes(ip)) >= self._maximo

    def falhou(self, ip: str) -> None:
        """Conta uma falha do IP (só as falhas contam: um escritório inteiro entra pelo mesmo IP)."""
        if ip not in self._falhas and len(self._falhas) >= self._maximo_de_ips:
            self._falhas = {i: f for i, f in self._falhas.items() if self._recentes(i)}
            while len(self._falhas) >= self._maximo_de_ips:
                del self._falhas[next(iter(self._falhas))]
        falhas = self._recentes(ip)
        falhas.append(self._relogio())
        self._falhas[ip] = falhas
