"""Escolha do renderizador do bot de pesquisa e a chamada ao Firecrawl local (sem rede: `requests` é dublê)."""

import pytest

from pesquisa import renderizacao

FIRECRAWL = "http://127.0.0.1:3002"


class _Resposta:
    def __init__(self, corpo: dict):
        self._corpo = corpo

    def json(self) -> dict:
        return self._corpo


def _trocar_o_post(monkeypatch: pytest.MonkeyPatch, corpo: dict) -> list[tuple]:
    pedidos: list[tuple] = []

    def post(rota: str, json: dict, timeout: int) -> _Resposta:
        pedidos.append((rota, json))
        return _Resposta(corpo)

    monkeypatch.setattr(renderizacao.requests, "post", post)
    return pedidos


def test_firecrawl_local_devolve_o_html_e_o_endereco_final(
    monkeypatch: pytest.MonkeyPatch,
):
    corpo = {
        "success": True,
        "data": {"rawHtml": "<p>olá</p>", "metadata": {"url": "https://x.gov.br/a/"}},
    }
    pedidos = _trocar_o_post(monkeypatch, corpo)
    renderizar = renderizacao.renderizador_pelo_firecrawl(FIRECRAWL + "/")
    assert renderizar("https://x.gov.br/a") == (
        "https://x.gov.br/a/",
        "<p>olá</p>".encode(),
    )
    assert pedidos == [
        (
            f"{FIRECRAWL}/v1/scrape",
            {"url": "https://x.gov.br/a", "formats": ["rawHtml"]},
        )
    ]


@pytest.mark.parametrize(
    "corpo",
    [{"success": False, "error": "tempo esgotado"}, {"success": True, "data": {}}],
)
def test_firecrawl_sem_html_levanta_erro(monkeypatch: pytest.MonkeyPatch, corpo: dict):
    _trocar_o_post(monkeypatch, corpo)
    with pytest.raises(RuntimeError):
        renderizacao.renderizador_pelo_firecrawl(FIRECRAWL)("https://x.gov.br/a")


@pytest.mark.parametrize(
    "endereco", ["https://api.firecrawl.dev", "http://10.0.0.5:3002", "sem-esquema"]
)
def test_firecrawl_fora_do_proprio_pc_e_recusado(endereco: str):
    with pytest.raises(ValueError, match="próprio PC"):
        renderizacao.renderizador_pelo_firecrawl(endereco)


def test_escolha_do_renderizador(monkeypatch: pytest.MonkeyPatch):
    variavel = renderizacao.VARIAVEL_DO_FIRECRAWL
    escolhido = renderizacao.escolher_renderizador({variavel: FIRECRAWL})
    assert escolhido is not None and escolhido.__name__ == "renderizar_pelo_firecrawl"
    monkeypatch.setattr(renderizacao, "crawl4ai_instalado", lambda: True)
    assert renderizacao.escolher_renderizador({}) is renderizacao.renderizar
    monkeypatch.setattr(renderizacao, "crawl4ai_instalado", lambda: False)
    assert renderizacao.escolher_renderizador({}) is None
