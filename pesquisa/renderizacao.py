"""HTML renderizado pelo Crawl4AI (Apache-2.0), só para páginas que montam o conteúdo com JavaScript.

O Crawl4AI é opcional: sem ele instalado, `buscar_pagina(renderizar=true)` recusa com o motivo. O
navegador do Crawl4AI não passa pelo `ClienteHttp`; por isso o `Coletor` confere o `robots.txt` e
espera a vez do domínio antes de chamar `renderizar`.

O Firecrawl entra por HTTP, como ferramenta à parte: é AGPL, e nenhum código dele entra aqui (sem
`import`, sem pin, sem trecho copiado). Dois caminhos:

- do próprio PC: `TICKERLAB_PESQUISA_FIRECRAWL` aponta para a porta local; endereço que não seja do
  próprio PC é recusado. Tem preferência (não gasta crédito);
- hospedado: com a chave em `FIRECRAWL_API_KEY`, o serviço de `api.firecrawl.dev` (endereço fixo, para a
  chave não ir a outro lugar). Só roda depois do Crawl4AI, quando ele falta ou falha, e só depois do
  `Porteiro` (nunca vai a terceiro endereço com termo barrado) e dentro do teto de créditos.
  Pede `proxy: basic` (o `enhanced` existe para vencer anti-robô, e bloqueio não se contorna) e
  `storeInCache: false`.
"""

import asyncio
import contextlib
import os
import re
import sys
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote_plus, urlsplit

import requests

from base.arquivo.agente import AGENTE

TEMPO_LIMITE_EM_SEGUNDOS = 90
PASTA_DO_NAVEGADOR = (
    "navegadores"  # `playwright install chromium` dentro do ambiente do bot
)
VARIAVEL_DO_FIRECRAWL = "TICKERLAB_PESQUISA_FIRECRAWL"
ENDERECOS_DO_PROPRIO_PC = frozenset({"127.0.0.1", "localhost", "::1"})
ROTA_DO_FIRECRAWL = "/v1/scrape"

# O mesmo nome que o programa oficial e o conector usam.
VARIAVEL_DA_CHAVE = "FIRECRAWL_API_KEY"
VARIAVEL_DOS_TERMOS_BARRADOS = "TICKERLAB_PESQUISA_TERMOS_BARRADOS"
# Sem a variável, os termos ficam na pasta do bot (fora do repositório). Sem o arquivo, o
# hospedado não liga: a chave sozinha (posta para o programa oficial, por exemplo) não basta.
TERMOS_BARRADOS_PADRAO = Path.home() / "TickerLab-Pesquisa" / "termos-barrados.txt"
VARIAVEL_DO_TETO = "TICKERLAB_FIRECRAWL_TETO"
# Por processo: uma rodada do agente ou uma vida do servidor MCP.
TETO_PADRAO_DE_CREDITOS = 50
ROTA_DO_FIRECRAWL_HOSPEDADO = "https://api.firecrawl.dev/v2/scrape"
CREDITOS_POR_PAGINA = 1  # preço da raspagem simples, quando a resposta não diz o gasto
# Custo máximo de UMA chamada com o pedido que montamos: 1 crédito por página, sem opção paga (só
# `rawHtml`, sem JSON, resumo, ZDR, PII, lockdown nem checagem de injeção) e com `parsers: []`, que devolve
# o PDF inteiro por 1 crédito fixo em vez de 1 por página. Fonte: docs.firecrawl.dev/billing e
# /api-reference/endpoint/scrape, lidas em 26/11/2026. O contador confere o teto com este máximo antes
# de cada envio, então o gasto do processo não passa do teto.
CUSTO_MAXIMO_POR_CHAMADA = 1
# Endereços que o Firecrawl repassa a provedores com preço próprio (fora do custo acima): não vão.
DOMINIOS_COM_PRECO_PROPRIO = ("x.com", "twitter.com", "linkedin.com")
TEMPO_DO_SERVICO_EM_MS = 60_000
PRIMEIRO_STATUS_DE_ERRO = 400
# Página que respondeu assim foi bloqueada: não se tenta por outro caminho.
STATUS_DE_BLOQUEIO = frozenset({401, 403, 429})
MAXIMO_DE_DECODIFICACOES = 4  # URL dentro de URL: decodifica até parar de mudar
RAIZ_DO_REPOSITORIO = Path(__file__).resolve().parent.parent

Renderizador = Callable[[str], tuple[str, bytes]]


def _apontar_o_navegador_do_ambiente() -> None:
    """Se o ambiente isolado tem a pasta do navegador, o Playwright a usa (sem variável do usuário)."""
    pasta = Path(sys.prefix) / PASTA_DO_NAVEGADOR
    if pasta.is_dir():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(pasta))
    os.environ.setdefault("CRAWL4AI_NO_CLOUD_NOTICE", "1")


def crawl4ai_instalado() -> bool:
    try:
        import crawl4ai  # noqa: F401
    except ImportError:
        return False
    return True


async def _renderizar(url: str) -> tuple[str, bytes]:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

    navegador = BrowserConfig(headless=True, user_agent=AGENTE, verbose=False)
    async with AsyncWebCrawler(config=navegador) as rastreador:
        resultado = await rastreador.arun(
            url, config=CrawlerRunConfig(page_timeout=TEMPO_LIMITE_EM_SEGUNDOS * 1000)
        )
    if getattr(resultado, "status_code", None) in STATUS_DE_BLOQUEIO:
        raise BloqueioNaRenderizacao(f"a página respondeu HTTP {resultado.status_code}")
    if not resultado.success:
        raise RuntimeError(
            resultado.error_message or "o Crawl4AI não renderizou a página"
        )
    return resultado.redirected_url or url, (resultado.html or "").encode("utf-8")


def renderizar(url: str) -> tuple[str, bytes]:
    """Renderiza `url` e devolve (endereço final, HTML). Roda num fio próprio: o servidor MCP já
    tem um laço de eventos ativo, e `asyncio.run` não pode ser chamado dentro dele. O Crawl4AI
    escreve avisos no stdout, que no servidor MCP é o canal do protocolo: vão para o stderr."""
    _apontar_o_navegador_do_ambiente()
    with (
        contextlib.redirect_stdout(sys.stderr),
        ThreadPoolExecutor(max_workers=1) as executor,
    ):
        return executor.submit(asyncio.run, _renderizar(url)).result()


def renderizador_pelo_firecrawl(endereco: str) -> Renderizador:
    """Renderizador que pede o HTML a um Firecrawl do próprio PC (ex.: `http://127.0.0.1:3002`)."""
    if urlsplit(endereco).hostname not in ENDERECOS_DO_PROPRIO_PC:
        raise ValueError(
            f"{VARIAVEL_DO_FIRECRAWL} só aceita endereço do próprio PC (127.0.0.1 ou localhost)"
        )
    rota = endereco.rstrip("/") + ROTA_DO_FIRECRAWL

    def renderizar_pelo_firecrawl(url: str) -> tuple[str, bytes]:
        resposta = requests.post(
            rota,
            json={"url": url, "formats": ["rawHtml"]},
            timeout=TEMPO_LIMITE_EM_SEGUNDOS,
        )
        corpo = resposta.json()
        dados = corpo.get("data") or {}
        if not corpo.get("success") or not dados.get("rawHtml"):
            raise RuntimeError(corpo.get("error") or "o Firecrawl não devolveu o HTML")
        url_final = (dados.get("metadata") or {}).get("url") or url
        return url_final, dados["rawHtml"].encode("utf-8")

    return renderizar_pelo_firecrawl


# --- Firecrawl hospedado -----------------------------------------------------------------------


class EnvioBarrado(Exception):
    """O porteiro não deixa o endereço ir a terceiro. A mensagem nunca repete o que barrou."""


class TetoDeCreditos(Exception):
    """O teto de créditos do Firecrawl hospedado deste processo acabou."""


class BloqueioNaRenderizacao(RuntimeError):
    """A página respondeu bloqueio (401, 403, 429). Bloqueio não se contorna: a cascata para aqui."""


def _so_letras_e_numeros(texto: str) -> str:
    """Sem acento, sem caixa e sem separador: "Empresa Fictícia" e "empresa-ficticia" ficam iguais."""
    decomposto = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return re.sub(r"[^0-9a-z]", "", sem_acento.casefold())


class Porteiro:
    """Confere o endereço antes de ele ir a um serviço de terceiro: nada com termo barrado (nome de
    cliente, alvo de mandato, pessoa). Na dúvida, barra: a comparação ignora separadores. Número de CPF
    no endereço de página pública não é barrado (decisão do Tiago, 26/11/2026; regra "GPL e AGPL" do
    AGENTS.md)."""

    def __init__(self, termos: Iterable[str]) -> None:
        self._termos = [t for t in map(_so_letras_e_numeros, termos) if t]

    @property
    def sem_termos(self) -> bool:
        return not self._termos

    def conferir(self, url: str) -> None:
        for texto in _leituras_do_endereco(url):
            canonico = _so_letras_e_numeros(texto)
            if any(termo in canonico for termo in self._termos):
                raise EnvioBarrado("o endereço tem um termo da lista de barrados")


def _leituras_do_endereco(url: str) -> set[str]:
    """O endereço como veio e todas as decodificações dele, em UTF-8 e em Latin-1 (site antigo), até
    pararem de mudar: URL dentro de URL vem codificada duas vezes."""
    leituras = {url}
    novas = {url}
    for _ in range(MAXIMO_DE_DECODIFICACOES):
        novas = {
            unquote_plus(texto, encoding=codificacao)
            for texto in novas
            for codificacao in ("utf-8", "latin-1")
        } - leituras
        if not novas:
            break
        leituras |= novas
    return leituras


def porteiro_do_ambiente(ambiente: Mapping[str, str]) -> Porteiro:
    """Porteiro com os termos do arquivo (um por linha; `#` comenta), apontado pela variável ou, sem ela,
    o padrão da pasta do bot. O arquivo fica fora do repositório, que é público, e precisa existir (pode
    ser vazio): sem ele, para, e o Firecrawl hospedado não liga."""
    caminho = ambiente.get(VARIAVEL_DOS_TERMOS_BARRADOS) or TERMOS_BARRADOS_PADRAO
    arquivo = Path(caminho).resolve()
    if arquivo.is_relative_to(RAIZ_DO_REPOSITORIO):
        raise ValueError(
            f"{VARIAVEL_DOS_TERMOS_BARRADOS}: o arquivo fica fora do repositório"
        )
    if not arquivo.is_file():
        raise ValueError(f"{VARIAVEL_DOS_TERMOS_BARRADOS}: o arquivo não existe")
    linhas = arquivo.read_text(encoding="utf-8").splitlines()
    return Porteiro(linha for linha in linhas if not linha.strip().startswith("#"))


class ContadorDeCreditos:
    """Créditos do Firecrawl hospedado gastos neste processo, com teto."""

    def __init__(self, teto: int = TETO_PADRAO_DE_CREDITOS) -> None:
        self.teto = teto
        self.creditos = 0
        self.paginas = 0

    def conferir(self) -> None:
        """Antes do envio: a chamada só sai se, mesmo custando o máximo, o gasto fica no teto."""
        if self.creditos + CUSTO_MAXIMO_POR_CHAMADA > self.teto:
            raise TetoDeCreditos(f"teto de {self.teto} créditos do Firecrawl atingido")

    def registrar(self, creditos: int) -> None:
        self.paginas += 1
        self.creditos += creditos


def _metadados(corpo: Mapping[str, object]) -> Mapping[str, object]:
    dados = corpo.get("data")
    metadados = dados.get("metadata") if isinstance(dados, Mapping) else None
    return metadados if isinstance(metadados, Mapping) else {}


def _html_da_resposta(corpo: Mapping[str, object], url: str) -> tuple[str, bytes]:
    """(endereço final, HTML) da resposta do `/scrape`; página que respondeu com erro não serve."""
    dados = corpo.get("data")
    html = dados.get("rawHtml") if isinstance(dados, Mapping) else None
    if not corpo.get("success") or not html:
        raise RuntimeError(str(corpo.get("error") or "o Firecrawl não devolveu o HTML"))
    metadados = _metadados(corpo)
    status = metadados.get("statusCode")
    if status in STATUS_DE_BLOQUEIO:
        raise BloqueioNaRenderizacao(f"a página respondeu HTTP {status}")
    if isinstance(status, int) and status >= PRIMEIRO_STATUS_DE_ERRO:
        raise RuntimeError(f"a página respondeu HTTP {status}")
    return str(metadados.get("url") or url), str(html).encode("utf-8")


def _creditos_gastos(corpo: Mapping[str, object]) -> int:
    gasto = _metadados(corpo).get("creditsUsed")
    return gasto if isinstance(gasto, int) and gasto >= 0 else CREDITOS_POR_PAGINA


# nome com "cpf" (cpf, CPF, nr_cpf, cpfCnpj, filters[cpf][$eq]) seguido de =, : ou operador por extenso,
# depois de ?, &, ;, #, /, :, =, { , vírgula, aspas, parêntese ou espaço: ?cpf=, #!cpf=, ?a/cpf=, ?q=cpf:<n>,
# filters={"cpf":"<n>"}, $filter=cpf eq '<n>', where=cpf in ('<n>'). A palavra solta (?q=cpf) e o caminho
# (/cpf-e-cnpj/) passam.
_SEPARADORES = r"""\s=:&;?#/"'{},()"""
_PARAMETRO_CPF = re.compile(
    rf"(?:^|[{_SEPARADORES}])[^{_SEPARADORES}]*cpf[^{_SEPARADORES}]*[\"']?"
    r"(?:\s*[=:]|\s+(?:eq|ne|in|like)\b)",
    re.IGNORECASE,
)


def _conferir_parametro_de_cpf(url: str) -> None:
    """O CPF fica fora de termo de busca (regra "GPL e AGPL" do AGENTS.md): consulta com parâmetro chamado
    cpf não vai ao Firecrawl, em nenhuma decodificação. O número em outro lugar do endereço de página
    pública pode ir (decisão do Tiago, 26/11/2026). A recusa não repete o endereço."""
    if any(_PARAMETRO_CPF.search(texto) for texto in _leituras_do_endereco(url)):
        raise EnvioBarrado("o endereço tem um parâmetro de busca chamado cpf")


def _conferir_custo_fixo(url: str) -> None:
    host = (urlsplit(url).hostname or "").lower()
    if any(host == d or host.endswith("." + d) for d in DOMINIOS_COM_PRECO_PROPRIO):
        raise EnvioBarrado(
            "endereço que o Firecrawl repassa a provedor com preço próprio"
        )


def renderizador_hospedado(
    chave: str,
    porteiro: Porteiro,
    contador: ContadorDeCreditos,
    *,
    post: Callable[..., requests.Response] = requests.post,
) -> Renderizador:
    """Renderizador pelo Firecrawl hospedado. Porteiro e teto antes de qualquer envio; a chave vai só no
    cabeçalho, nunca em mensagem de erro."""

    def renderizar_pelo_firecrawl_hospedado(url: str) -> tuple[str, bytes]:
        porteiro.conferir(url)
        _conferir_parametro_de_cpf(url)
        _conferir_custo_fixo(url)
        contador.conferir()
        resposta = post(
            ROTA_DO_FIRECRAWL_HOSPEDADO,
            json={
                "url": url,
                "formats": ["rawHtml"],
                "onlyMainContent": False,
                "proxy": "basic",
                "storeInCache": False,
                "timeout": TEMPO_DO_SERVICO_EM_MS,
                "parsers": [],  # PDF por 1 crédito fixo, não 1 por página
            },
            headers={"Authorization": f"Bearer {chave}"},
            timeout=TEMPO_LIMITE_EM_SEGUNDOS,
        )
        # Conta antes de validar: página que voltou com erro também pode ter sido cobrada.
        try:
            corpo = resposta.json()
        except ValueError:
            corpo = {}
        contador.registrar(_creditos_gastos(corpo))
        if resposta.status_code >= PRIMEIRO_STATUS_DE_ERRO:
            raise RuntimeError(f"o Firecrawl respondeu HTTP {resposta.status_code}")
        return _html_da_resposta(corpo, url)

    return renderizar_pelo_firecrawl_hospedado


def em_cascata(*renderizadores: Renderizador) -> Renderizador:
    """Tenta cada renderizador na ordem; o seguinte só roda se o anterior falhou. Bloqueio da página
    para tudo: tentar por outro caminho (outro IP) seria contornar."""

    def renderizar_em_cascata(url: str) -> tuple[str, bytes]:
        erro: Exception = RuntimeError("nenhum renderizador")
        for renderizador in renderizadores:
            try:
                return renderizador(url)
            except BloqueioNaRenderizacao:
                raise
            except Exception as falha:  # noqa: BLE001 (qualquer outra falha passa ao seguinte)
                erro = falha
        raise erro

    return renderizar_em_cascata


def _teto_do_ambiente(ambiente: Mapping[str, str]) -> int:
    valor = ambiente.get(VARIAVEL_DO_TETO)
    if not valor:
        return TETO_PADRAO_DE_CREDITOS
    try:
        return int(valor)
    except ValueError:
        raise ValueError(f"{VARIAVEL_DO_TETO} precisa ser um número inteiro") from None


def escolher_renderizador(
    ambiente: Mapping[str, str] | None = None,
    *,
    contador: ContadorDeCreditos | None = None,
) -> Renderizador | None:
    """O Firecrawl local, se a variável aponta para ele. Senão, na ordem: o Crawl4AI, se instalado, e o
    Firecrawl hospedado, se há chave e arquivo de termos barrados. Nenhum dos dois: nenhum renderizador.
    O aviso de hospedado desligado vai ao stderr (no servidor MCP, o stdout é o canal do protocolo)."""
    ambiente = os.environ if ambiente is None else ambiente
    endereco = ambiente.get(VARIAVEL_DO_FIRECRAWL)
    if endereco:
        return renderizador_pelo_firecrawl(endereco)
    ordem: list[Renderizador] = [renderizar] if crawl4ai_instalado() else []
    chave = ambiente.get(VARIAVEL_DA_CHAVE)
    if chave:
        try:
            porteiro = porteiro_do_ambiente(ambiente)
        except ValueError as motivo:
            print(f"Firecrawl hospedado desligado: {motivo}", file=sys.stderr)
        else:
            if porteiro.sem_termos:
                print(
                    "Firecrawl hospedado ligado com a lista de termos barrados vazia: "
                    "nenhum endereço é conferido",
                    file=sys.stderr,
                )
            contador = contador or ContadorDeCreditos()
            contador.teto = _teto_do_ambiente(ambiente)
            ordem.append(renderizador_hospedado(chave, porteiro, contador))
    if not ordem:
        return None
    return ordem[0] if len(ordem) == 1 else em_cascata(*ordem)
