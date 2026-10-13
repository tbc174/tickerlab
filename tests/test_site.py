"""O site público (pasta `site/`, gerada por `scripts/gerar_site.py`): em dia, sem links
quebrados, sem recursos de terceiros e sem promessas que o produto não cumpre."""

import json
import re
from pathlib import Path

import pytest

from scripts import gerar_site as gs
from src import marca, planos
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
        "produto.html",
        "como-funciona.html",
        "aprender.html",
    }
    for arquivo in PAGINAS_HTML:
        texto = arquivo.read_text(encoding="utf-8")
        assert '<html lang="pt-BR">' in texto
        assert re.search(r"<title>[^<]+</title>", texto)
        assert '<meta name="description" content="' in texto
        assert "nada aqui é recomendação de investimento" in texto.lower()
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


def test_o_site_abre_claro_e_tem_o_botao_do_tema_escuro():
    """Manual de identidade v1: site claro com faixas em marinho; o escuro é uma opção."""
    css = (SITE / "estilo.css").read_text(encoding="utf-8")
    raiz = css[css.index(":root {") : css.index("}", css.index(":root {"))]
    assert "color-scheme: light" in raiz and marca.CLARO in raiz
    assert ':root[data-tema="escuro"]' in css and ".escura" in css
    for arquivo in PAGINAS_HTML:
        texto = arquivo.read_text(encoding="utf-8")
        assert "data-tema-botao" in texto, arquivo.name
        # a escolha guardada vale antes de pintar a página (sem piscar o tema claro)
        assert texto.index('localStorage.getItem("tema")') < texto.index("<body>")
    assert "data-tema-botao" in (SITE / "site.js").read_text(encoding="utf-8")


def test_o_site_usa_o_simbolo_e_a_assinatura_do_manual():
    inicio = (SITE / "index.html").read_text(encoding="utf-8")
    assert marca.TRACO_DO_TOPO in inicio and marca.TRACO_DA_HASTE in inicio
    assert "Menos ruído. Mais inteligência para investir." in inicio
    assert 'content="https://tickerlab.com.br/marca/compartilhamento.png"' in inicio
    assert (SITE / "marca" / "compartilhamento.png").exists()


def test_css_e_js_tem_a_versao_do_conteudo_no_endereco():
    """A Cloudflare guarda o CSS e o JS por horas: sem a versão no endereço, quem visita depois de
    um deploy recebe o HTML novo com o estilo antigo."""
    import hashlib

    for nome in ("estilo.css", "site.js"):
        conteudo = (SITE / nome).read_text(
            encoding="utf-8"
        )  # quebras de linha iguais em todo SO
        versao = hashlib.sha256(conteudo.encode("utf-8")).hexdigest()[:12]
        for arquivo in PAGINAS_HTML:
            assert f'"/{nome}?v={versao}"' in arquivo.read_text(encoding="utf-8"), (
                arquivo.name,
                nome,
            )


def test_menu_da_versao_a_em_todas_as_paginas():
    """Organização escolhida pelo Tiago em 13/10/2026 (protótipo A, por assunto)."""
    for arquivo in PAGINAS_HTML:
        topo = arquivo.read_text(encoding="utf-8").split("</header>")[0]
        for rotulo in ("Produto", "Como funciona", "Relatórios", "Planos", "Aprender"):
            assert f">{rotulo}</a>" in topo, (arquivo.name, rotulo)


def test_pagina_produto_mostra_o_que_existe_e_o_que_vem():
    from src import modulos

    texto = (SITE / "produto.html").read_text(encoding="utf-8")
    for modulo in modulos.MODULOS[:6]:
        assert f'id="{modulo.chave}"' in texto
        for f in modulo.funcionalidades:
            assert gs.esc(f.nome) in texto
    total_breve = sum(m.em_breve for m in modulos.MODULOS[:6])
    assert texto.count('class="selo breve"') == total_breve
    # o que ainda não existe não leva a lugar nenhum
    for cartao in re.findall(r'<article class="cartao breve">.*?</article>', texto):
        assert "href=" not in cartao


def test_animacoes_do_site_respeitam_quem_pede_menos_movimento():
    """Catálogo de animações do blueprint (seção 09), só com CSS e JS próprios."""
    css = (SITE / "estilo.css").read_text(encoding="utf-8")
    assert "@view-transition { navigation: auto; }" in css  # troca suave entre páginas
    reduzir = css[css.index("@media (prefers-reduced-motion: reduce)") :]
    assert "animation: none !important" in reduzir
    assert "@view-transition { navigation: none; }" in reduzir
    js = (SITE / "site.js").read_text(encoding="utf-8")
    assert "startViewTransition" in js and "prefers-reduced-motion" in js


def test_a_linha_do_heroi_e_decorativa():
    """O desenho do topo é ilustração (manual, seção 5): escondido dos leitores de tela."""
    inicio = (SITE / "index.html").read_text(encoding="utf-8")
    linha = re.search(r'<svg class="linha-heroi"[^>]*>', inicio)
    assert linha and 'aria-hidden="true"' in linha.group(0)


def test_menu_do_tema_tem_claro_escuro_e_automatico():
    """Pedido do Tiago (13/10/2026): escolher claro, escuro ou automático (pelo pôr do sol)."""
    for arquivo in PAGINAS_HTML:
        topo = arquivo.read_text(encoding="utf-8").split("</header>")[0]
        opcoes = re.findall(r'role="menuitemradio"[^>]*data-tema-escolha="(\w+)"', topo)
        assert opcoes == ["claro", "escuro", "auto"], arquivo.name
        assert 'aria-haspopup="menu"' in topo


def test_o_tema_e_decidido_no_head_antes_do_css_e_o_padrao_e_automatico():
    import hashlib

    sol = (SITE / "tema" / "sol.js").read_text(encoding="utf-8")
    versao = hashlib.sha256(sol.encode("utf-8")).hexdigest()[:12]
    for arquivo in PAGINAS_HTML:
        texto = arquivo.read_text(encoding="utf-8")
        cabeca = texto[: texto.index("</head>")]
        # o cálculo do sol carrega antes do CSS e sem defer: não pisca o tema errado
        assert f'<script src="/tema/sol.js?v={versao}"></script>' in cabeca, (
            arquivo.name
        )
        assert cabeca.index("/tema/sol.js") < cabeca.index("/estilo.css")
        assert '|| "auto"' in cabeca  # quem nunca escolheu fica no automático
        assert "temaDoMomento" in cabeca
    assert sol == (gs.RAIZ / "static" / "tema" / "sol.js").read_text(encoding="utf-8")


# frases das peças institucionais aprovadas (carrosséis "Quem somos", "Nossa história" e "No que
# acreditamos", 13/10/2026): a página Sobre usa o texto aprovado, sem reescrever
FRASES_APROVADAS = (
    "Uma análise não conta toda a história.",
    "O mercado financeiro oferece inúmeros dados, gráficos e indicadores.",
    "Mas informações isoladas nem sempre ajudam a compreender o conjunto.",
    "Nossa visão é conectar diferentes perspectivas de análise.",
    "Queremos tornar a pesquisa de investimentos mais clara, profunda e organizada.",
    "Uma plataforma brasileira de inteligência financeira.",
    "Tudo começou com Python e Pandas.",
    "O primeiro projeto universitário.",
    "A evolução.",
    "O ponto de virada.",
    "Nossa história continua.",
    "Diferentes perspectivas. Uma visão mais completa.",
    "Resultados, endividamento e geração de valor ajudam a compreender uma empresa.",
    "Nossa visão é conectar métodos, mostrar concordâncias, divergências, riscos e limitações.",
    "Não queremos substituir suas decisões.",
    "Queremos contribuir para uma pesquisa de investimentos mais clara, fundamentada e autônoma.",
)


def test_pagina_sobre_usa_o_texto_aprovado():
    texto = (SITE / "sobre.html").read_text(encoding="utf-8")
    for frase in FRASES_APROVADAS:
        assert gs.esc(frase) in texto, frase
    for pilar in ("Dados confiáveis", "Método e contexto", "Múltiplas perspectivas"):
        assert pilar in texto
    for secao in ("quem-somos", "nossa-historia", "no-que-acreditamos"):
        assert f'id="{secao}"' in texto
    assert "https://tickerlab.com.br/sobre.html" in (SITE / "sitemap.xml").read_text(
        encoding="utf-8"
    )


def test_sobre_no_menu_e_no_rodape_de_todas_as_paginas():
    for arquivo in PAGINAS_HTML:
        texto = arquivo.read_text(encoding="utf-8")
        topo, rodape = texto.split("</header>")[0], texto.split("<footer")[1]
        assert '<a href="/sobre.html"' in topo, arquivo.name
        assert '<a href="/sobre.html">' in rodape, arquivo.name
