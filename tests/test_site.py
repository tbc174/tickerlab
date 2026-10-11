"""O site público (pasta `site/`, gerada por `scripts/gerar_site.py`): em dia, sem links
quebrados, sem recursos de terceiros e sem promessas que o produto não cumpre."""

import json
import re
from pathlib import Path

import pytest

from scripts import gerar_site as gs
from src import planos
from src.paginas import PAGINAS

SITE = Path(__file__).resolve().parent.parent / "site"
PAGINAS_HTML = sorted(SITE.glob("*.html"))
PROIBIDAS = (
    "lucro certo",
    "ganhe do mercado",
    "a melhor ação",
    "infalível",
    "lucro garantido",
    "retorno garantido",
    "regularizado pela cvm",
    "marca registrada",
    "parceiro oficial",
)


@pytest.fixture(scope="module")
def regerado(tmp_path_factory):
    destino = tmp_path_factory.mktemp("site")
    gs.gerar(destino)
    return destino


def test_site_esta_em_dia_com_o_gerador(regerado):
    """Mudou a marca, os planos, os termos ou o catálogo? Rode `python -m scripts.gerar_site`."""
    novos = {p.relative_to(regerado) for p in regerado.rglob("*") if p.is_file()}
    atuais = {p.relative_to(SITE) for p in SITE.rglob("*") if p.is_file()}
    assert novos == atuais
    diferentes = [
        str(c) for c in novos if (regerado / c).read_bytes() != (SITE / c).read_bytes()
    ]
    assert not diferentes, f"Rode python -m scripts.gerar_site: {diferentes}"


def test_paginas_tem_titulo_descricao_idioma_e_aviso():
    assert {p.name for p in PAGINAS_HTML} >= {
        "index.html",
        "precos.html",
        "metodologia.html",
        "termos.html",
        "privacidade.html",
        "404.html",
    }
    for arquivo in PAGINAS_HTML:
        texto = arquivo.read_text(encoding="utf-8")
        assert '<html lang="pt-BR">' in texto
        assert re.search(r"<title>[^<]+</title>", texto)
        assert '<meta name="description" content="' in texto
        assert "nada aqui é recomendação de investimento" in texto
        assert (
            'href="#conteudo"' in texto and 'id="conteudo"' in texto
        )  # pular para o conteúdo


def test_nenhuma_promessa_proibida():
    for arquivo in PAGINAS_HTML:
        texto = arquivo.read_text(encoding="utf-8").lower()
        for frase in PROIBIDAS:
            assert frase not in texto, (arquivo.name, frase)


def test_links_internos_e_imagens_existem():
    for arquivo in PAGINAS_HTML:
        texto = arquivo.read_text(encoding="utf-8")
        for alvo in re.findall(r'(?:href|src)="(/[^"#?]*)', texto):
            caminho = SITE / (alvo.lstrip("/") or "index.html")
            assert caminho.exists(), (arquivo.name, alvo)


def test_links_para_o_app_vao_para_paginas_que_existem():
    urls = {p.url for p in PAGINAS} | {""}
    for arquivo in PAGINAS_HTML:
        texto = arquivo.read_text(encoding="utf-8")
        for pagina in re.findall(re.escape(gs.URL_DO_APP) + r"/([a-z\-]*)", texto):
            assert pagina in urls, (arquivo.name, pagina)


def test_nada_vem_de_terceiros():
    """Sem Google Fonts, sem rastreadores: fontes, imagens e scripts são do próprio site."""
    for arquivo in [*PAGINAS_HTML, SITE / "estilo.css", SITE / "site.js"]:
        texto = arquivo.read_text(encoding="utf-8")
        assert "googleapis" not in texto and "gstatic" not in texto
        externos = re.findall(r'(?:src|href)="(https?://[^"]+)"', texto)
        recursos = [u for u in externos if re.search(r"\.(?:js|css|woff2?|ttf)$", u)]
        assert not recursos, (arquivo.name, recursos)
        assert '<script src="http' not in texto


def test_planos_do_site_sao_os_do_app():
    texto = (SITE / "precos.html").read_text(encoding="utf-8")
    for linha in planos.tabela_de_planos():
        for nome in ("Gratuito", "Plus", "Pro"):
            assert f"<td>{gs.esc(linha[nome])}</td>" in texto
    assert "R$" not in texto  # sem preço enquanto não houver cobrança real
    assert "modo de teste" in texto


def test_catalogo_da_busca_e_o_do_app():
    ativos = json.loads((SITE / "catalogo.json").read_text(encoding="utf-8"))
    simbolos = {a[0] for a in ativos}
    assert {"PETR4.SA", "AAPL", "^BVSP", "BTC-USD"} <= simbolos
    assert all(len(a) == 5 for a in ativos)


def test_relatorio_de_exemplo_e_um_pdf_de_verdade_marcado_como_exemplo():
    from io import BytesIO

    from pypdf import PdfReader

    pdf = (SITE / "relatorio" / f"exemplo-{gs.TICKER_DO_EXEMPLO}.pdf").read_bytes()
    capa = PdfReader(BytesIO(pdf)).pages[0].extract_text()
    assert "de exemplo" in capa
    for estilo in ("research", "terminal", "institucional"):
        for pagina in (1, 2):
            assert (
                SITE / "relatorio" / f"{estilo}-{pagina}.webp"
            ).stat().st_size > 5_000


def test_markdown_simples_vira_html():
    html = gs.markdown_para_html(
        "## Título\n\nTexto com **negrito** e *ênfase*.\n\n- um\n- dois\n\n"
        "| A | B |\n|---|---|\n| 1 | <x> |\n"
    )
    assert "<h3>Título</h3>" in html
    assert "<strong>negrito</strong>" in html and "<em>ênfase</em>" in html
    assert "<ul><li>um</li><li>dois</li></ul>" in html
    assert "<td>&lt;x&gt;</td>" in html  # o texto é escapado
