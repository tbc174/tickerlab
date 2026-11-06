"""HTML renderizado pelo Crawl4AI (Apache-2.0), só para páginas que montam o conteúdo com JavaScript.

O Crawl4AI é opcional: sem ele instalado, `buscar_pagina(renderizar=true)` recusa com o motivo. O
navegador do Crawl4AI não passa pelo `ClienteHttp`; por isso o `Coletor` confere o `robots.txt` e
espera a vez do domínio antes de chamar `renderizar`.
"""

import asyncio
import contextlib
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from base.arquivo.agente import AGENTE

TEMPO_LIMITE_EM_SEGUNDOS = 90
PASTA_DO_NAVEGADOR = (
    "navegadores"  # `playwright install chromium` dentro do ambiente do bot
)


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
