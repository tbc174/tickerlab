"""O ritmo com que o arquivista pede a cada site (ADR 0102: o ritmo respeita o site).

- **Pausa por site:** o `Crawl-delay` do `robots.txt` (lido uma vez por site e guardado), ou, se o
  `robots.txt` não responde, a tabela `PAUSAS_DE_RESERVA` (lida em 21/10/2026). Vale para todo pedido
  ao site, inclusive o `package_show` e os catálogos. Site sem `Crawl-delay` fica no ritmo de
  `coleta.PAUSA_ENTRE_PEDIDOS_EM_SEGUNDOS`: aqui não se espera nada a mais.
- **429 (muitos pedidos):** espera o `Retry-After` do site, até `ESPERA_MAXIMA_EM_SEGUNDOS`, e pede
  de novo, no máximo `TENTATIVAS_SE_429` vezes; depois disso a resposta de erro segue o seu caminho.
"""

import logging
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

from base.arquivo import robots

log = logging.getLogger(__name__)

# sete portais CKAN pedem 10 s no robots.txt (auditoria N0, 21/10/2026)
PAUSA_DOS_PORTAIS_CKAN_EM_SEGUNDOS = 10.0
PAUSAS_DE_RESERVA = {
    host: PAUSA_DOS_PORTAIS_CKAN_EM_SEGUNDOS
    for host in (
        "dados.cvm.gov.br",
        "dadosabertos.bcb.gov.br",
        "dadosabertos.ccee.org.br",
        "dados.antt.gov.br",
        "dados.ons.org.br",
        "dadosabertos.aneel.gov.br",
        "dados.tce.rs.gov.br",
    )
}
# um Crawl-delay maior que isto é erro de digitação do site: não trava a coleta da noite
TETO_DA_PAUSA_EM_SEGUNDOS = 60.0
HTTP_MUITOS_PEDIDOS = 429
TENTATIVAS_SE_429 = 3
ESPERA_SEM_RETRY_AFTER_EM_SEGUNDOS = 30.0
ESPERA_MAXIMA_EM_SEGUNDOS = 120.0
# a máquina local não precisa de educação
HOSTS_LOCAIS = frozenset({"localhost", "127.0.0.1", "::1"})

LerRobots = Callable[[str], str | None]


def espera_do_retry_after(
    cabecalhos: Mapping[str, str], agora: datetime | None = None
) -> float:
    """Quanto esperar pelo `Retry-After` (segundos ou data HTTP), limitado ao teto; sem o cabeçalho
    (ou ilegível), `ESPERA_SEM_RETRY_AFTER_EM_SEGUNDOS`."""
    valor = {k.lower(): v for k, v in cabecalhos.items()}.get("retry-after", "").strip()
    espera = ESPERA_SEM_RETRY_AFTER_EM_SEGUNDOS
    try:
        espera = float(valor)
    except ValueError:
        try:
            data = parsedate_to_datetime(valor)
            espera = (data - (agora or datetime.now(UTC))).total_seconds()
        except (TypeError, ValueError):
            pass
    return min(max(espera, 0.0), ESPERA_MAXIMA_EM_SEGUNDOS)


class Ritmo:
    """Guarda a pausa de cada site e faz cada pedido esperar a sua vez."""

    def __init__(
        self,
        ler_robots: LerRobots,
        *,
        relogio: Callable[[], float] = time.monotonic,
        esperar: Callable[[float], None] = time.sleep,
    ) -> None:
        self._ler_robots = ler_robots
        self._relogio = relogio
        self._esperar = esperar
        self._pausas: dict[str, float] = {}
        self._ultimo_pedido: dict[str, float] = {}

    def pausa_do(self, url: str) -> float:
        """A pausa mínima entre dois pedidos ao site de `url` (0: nada além do ritmo da coleta)."""
        partes = urlsplit(url)
        host = (partes.hostname or "").lower()
        if host in HOSTS_LOCAIS:
            return 0.0
        if host not in self._pausas:
            texto = self._ler_robots(f"{partes.scheme}://{partes.netloc}/robots.txt")
            pedida = robots.pausa_pedida(texto) if texto is not None else None
            if pedida is None:
                pedida = PAUSAS_DE_RESERVA.get(host, 0.0) if texto is None else 0.0
            self._pausas[host] = min(pedida, TETO_DA_PAUSA_EM_SEGUNDOS)
        return self._pausas[host]

    def esperar_a_vez(self, url: str) -> None:
        """Espera o que falta da pausa desde o último pedido ao mesmo site e marca este pedido."""
        pausa = self.pausa_do(url)
        host = (urlsplit(url).hostname or "").lower()
        if pausa:
            anterior = self._ultimo_pedido.get(host)
            falta = pausa - (self._relogio() - anterior) if anterior is not None else 0
            if falta > 0:
                self._esperar(falta)
            self._ultimo_pedido[host] = self._relogio()

    def esperar_o_429(
        self, url: str, cabecalhos: Mapping[str, str], tentativa: int
    ) -> None:
        """Espera o `Retry-After` do site e registra (só o site, nunca o endereço inteiro)."""
        espera = espera_do_retry_after(cabecalhos)
        log.warning(
            "%s respondeu 429; espera %.0f s (nova tentativa %d de %d)",
            urlsplit(url).hostname,
            espera,
            tentativa,
            TENTATIVAS_SE_429,
        )
        self._esperar(espera)
