"""Posts das assessorias de M&A no arquivista (base/arquivo/assessorias.py, ADR 0082)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from base.arquivo import assessorias, coleta, fontes
from base.arquivo.coleta import Alvo, ErroDeDescoberta, Fonte, Resposta
from src.banco import coletas

AGORA = datetime(2026, 10, 18, 5, tzinfo=UTC)  # domingo, 2h em Brasília
IGC = assessorias.Assessoria(
    "teste", "https://www.assessoria.com.br", r"/transactions/[^/]+"
)
SITEMAP = IGC.site + "/sitemap.xml"
ROBOTS = IGC.site + "/robots.txt"
PAGINA_1 = IGC.site + "/transactions/a-x-e-adquirida-pela-y"
PAGINA_2 = IGC.site + "/transactions/a-z-vendeu-participacao-a-w"
HTML = b"<!doctype html><html><body><h1>X e Y</h1></body></html>"


def _sitemap(*urls: str) -> bytes:
    locs = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locs}</urlset>'
    ).encode()


SITEMAP_DO_SITE = _sitemap(
    IGC.site + "/en",
    PAGINA_2,
    IGC.site + "/en/transactions/a-x-e-adquirida-pela-y",
    IGC.site + "/es/transactions/a-x-e-adquirida-pela-y",
    PAGINA_1,
    PAGINA_1,  # repetida
    IGC.site + "/transactions",  # a lista, não um negócio
    "https://outro.com.br/transactions/a-x",  # outro site
)


class Site:
    """Um site em memória: url -> conteúdo. Guarda o que foi pedido e baixado."""

    def __init__(self, paginas: dict[str, bytes]):
        self.paginas = paginas
        self.lidos: list[str] = []
        self.baixados: list[str] = []

    def ler(self, url, *, metodo="GET", cabecalhos=None):
        self.lidos.append(url)
        return Resposta(url, self.paginas[url], {})

    def cabecalhos(self, url):
        return {}

    def baixar(self, url, destino: Path):
        self.baixados.append(url)
        destino.write_bytes(self.paginas[url])
        return {}


def _site(robots: bytes = b"Sitemap: https://www.assessoria.com.br/sitemap.xml\n"):
    return Site(
        {ROBOTS: robots, SITEMAP: SITEMAP_DO_SITE, PAGINA_1: HTML, PAGINA_2: HTML}
    )


def test_sitemap_da_so_as_paginas_de_negocio_em_portugues():
    assert assessorias.paginas_de_transacao(SITEMAP_DO_SITE, IGC) == [
        PAGINA_1,
        PAGINA_2,
    ]


def test_descobrir_le_o_robots_antes_do_sitemap_e_devolve_as_paginas():
    site = _site()
    alvos = assessorias.descobrir(IGC)(site, AGORA)
    assert site.lidos == [ROBOTS, SITEMAP]
    assert alvos == [Alvo(PAGINA_1, ".html"), Alvo(PAGINA_2, ".html")]


@pytest.mark.parametrize(
    "robots",
    [
        b"User-agent: *\nDisallow: /transactions/\n",
        b"User-agent: TickerLab\nDisallow: /\n",
        b"User-agent: *\nDisallow: /transactions/a-z\n",  # uma página só já para tudo
    ],
)
def test_robots_que_proibe_para_a_coleta_inteira(robots):
    site = _site(robots)
    with pytest.raises(ErroDeDescoberta, match="robots.txt"):
        assessorias.descobrir(IGC)(site, AGORA)
    assert site.baixados == []


def test_robots_que_proibe_outro_robo_nao_atrapalha():
    robots = b"User-agent: GPTBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
    assert len(assessorias.descobrir(IGC)(_site(robots), AGORA)) == 2


def test_robots_que_pede_mais_espera_que_a_nossa_para_a_coleta():
    robots = b"User-agent: *\nCrawl-delay: 30\n"
    with pytest.raises(ErroDeDescoberta, match="Crawl-delay"):
        assessorias.descobrir(IGC)(_site(robots), AGORA)


def test_sitemap_sem_pagina_de_negocio_e_falha():
    site = _site()
    site.paginas[SITEMAP] = _sitemap(IGC.site + "/en", IGC.site + "/transactions")
    with pytest.raises(ErroDeDescoberta, match="nenhuma página"):
        assessorias.descobrir(IGC)(site, AGORA)


def test_pagina_ja_guardada_nao_e_baixada_de_novo(banco, tmp_path):
    fonte = assessorias.fonte(IGC)
    site = _site()
    primeira = coleta.arquivar(fonte, site, AGORA, tmp_path / "t", pausa=0)
    segunda = coleta.arquivar(fonte, site, AGORA, tmp_path / "t", pausa=0)
    assert (primeira.novos, segunda.novos, segunda.pulados) == (2, 0, 2)
    assert site.baixados == [PAGINA_1, PAGINA_2]


def test_pausa_minima_da_fonte_vale_mesmo_com_pausa_menor(banco, tmp_path, monkeypatch):
    esperas: list[float] = []
    monkeypatch.setattr(coleta.time, "sleep", esperas.append)
    coleta.arquivar(assessorias.fonte(IGC), _site(), AGORA, tmp_path / "t", pausa=1.0)
    assert esperas == [assessorias.PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS]
    assert assessorias.PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS >= 3


def test_pausa_zero_dos_testes_continua_sem_esperar(banco, tmp_path, monkeypatch):
    esperas: list[float] = []
    monkeypatch.setattr(coleta.time, "sleep", esperas.append)
    coleta.arquivar(assessorias.fonte(IGC), _site(), AGORA, tmp_path / "t", pausa=0)
    assert esperas == []


def test_fonte_sem_pausa_minima_usa_a_pausa_de_sempre(banco, tmp_path, monkeypatch):
    esperas: list[float] = []
    monkeypatch.setattr(coleta.time, "sleep", esperas.append)
    fonte = Fonte(
        "teste-fonte", "diaria", lambda c, a: [Alvo(PAGINA_1), Alvo(PAGINA_2)], "html"
    )
    coleta.arquivar(fonte, _site(), AGORA, tmp_path / "t", pausa=1.0)
    assert esperas == [1.0]


def test_igc_no_catalogo_semanal_com_a_vigia_do_robots():
    por_id = {f.id: f for f in fontes.FONTES}
    igc = por_id["assessoria-igc"]
    assert (igc.grupo, igc.tipo, igc.vigia) == ("semanal", "html", False)
    assert igc.pausa_minima == assessorias.PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS
    vigia = por_id["termos-igc-robots"]
    assert vigia.vigia and vigia.descobrir(None, AGORA) == [
        Alvo("https://www.igcp.com.br/robots.txt")
    ]
    assert "termos-igc-privacidade" in por_id


def test_assessorias_nao_sao_vendidas_antes_do_parecer():
    assert "0082" in coletas.licenca_da_fonte("assessoria-igc")
    assert coletas.revenda_da_fonte("assessoria-igc") == coletas.A_CONFIRMAR
