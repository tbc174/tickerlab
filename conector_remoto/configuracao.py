"""A configuração do conector, lida do ambiente do contêiner (nada de segredo aqui no PR 1)."""

from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

VARIAVEL_DA_API = "TICKERLAB_MCP_API_URL"
VARIAVEL_DA_URL_PUBLICA = "TICKERLAB_MCP_URL_PUBLICA"
VARIAVEL_DOS_HOSTS = "TICKERLAB_MCP_HOSTS"
# dentro da rede do compose: o contêiner da API externa, sem passar pela internet
API_PADRAO = "http://tickerlab-api:8000"
URL_PUBLICA_PADRAO = "https://mcp.tickerlab.com.br"
# quem chama o conector são os servidores da Anthropic e da OpenAI; um navegador só manda Origin destes
ORIGENS_PADRAO = ("https://claude.ai", "https://chatgpt.com")
# a API externa costuma responder em menos de 1 s; o Claude espera até 240 s por ferramenta
TEMPO_LIMITE_DA_API_S = 30.0


@dataclass(frozen=True)
class Configuracao:
    """Onde está a API, como o conector se chama na internet e de quem ele aceita pedidos."""

    url_da_api: str
    url_publica: str
    hosts_permitidos: tuple[str, ...]
    origens_permitidas: tuple[str, ...]
    tempo_limite_s: float = TEMPO_LIMITE_DA_API_S

    @property
    def url_do_mcp(self) -> str:
        """O endereço que o analista cola na IA (o recurso protegido do OAuth)."""
        return f"{self.url_publica}/mcp"


def _host_da_url(url: str) -> str:
    partes = urlsplit(url)
    if partes.scheme not in {"http", "https"} or not partes.hostname:
        raise ValueError(f"URL sem esquema http(s) ou sem host: {url!r}")
    return partes.netloc.lower()


def _lista(texto: str) -> tuple[str, ...]:
    return tuple(item.strip().lower() for item in texto.split(",") if item.strip())


def ler_configuracao(ambiente: Mapping[str, str]) -> Configuracao:
    """A configuração a partir das variáveis de ambiente; o host público é sempre aceito."""
    url_da_api = ambiente.get(VARIAVEL_DA_API, API_PADRAO).rstrip("/")
    url_publica = ambiente.get(VARIAVEL_DA_URL_PUBLICA, URL_PUBLICA_PADRAO).rstrip("/")
    _host_da_url(url_da_api)
    host_publico = _host_da_url(url_publica)
    extras = _lista(ambiente.get(VARIAVEL_DOS_HOSTS, ""))
    hosts = tuple(dict.fromkeys((host_publico, *extras)))
    origem_publica = f"{urlsplit(url_publica).scheme}://{host_publico}"
    origens = tuple(dict.fromkeys((*ORIGENS_PADRAO, origem_publica)))
    return Configuracao(url_da_api, url_publica, hosts, origens)
