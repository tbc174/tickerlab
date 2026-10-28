"""O site público (pasta `site/`): em dia, sem links quebrados, sem recursos de terceiros e sem
promessas que o produto não cumpre.

As páginas, o CSS e o JS vêm do React (`web/`, ADR 0048; o teste de que estão em dia é do Vitest);
fontes, marca, relatório de exemplo e catálogo vêm de `scripts/gerar_site.py` (testados aqui)."""

import html
import json
import re
from pathlib import Path

import pytest

from scripts import gerar_site as gs
from scripts.markdown_simples import markdown_para_html
from src import marca, planos
from src.paginas import PAGINAS

SITE = Path(__file__).resolve().parent.parent / "site"
PAGINAS_HTML = sorted(SITE.glob("*.html"))
URL_DO_APP = "https://app.tickerlab.com.br"
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


def esc(texto: str) -> str:
    return html.escape(texto, quote=True)


def test_parte_do_python_esta_em_dia(regerado):
    """Mudou a marca, o relatório de exemplo ou o catálogo? Rode `python -m scripts.gerar_site`."""
    novos = gs.arquivos_do_python(regerado)
    atuais = gs.arquivos_do_python(SITE)
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
        "novidades.html",
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
        for pagina in re.findall(re.escape(URL_DO_APP) + r"/([a-z0-9\-]*)", texto):
            assert pagina in urls, (arquivo.name, pagina)


def test_nada_vem_de_terceiros():
    """Sem Google Fonts, sem rastreadores: fontes, imagens e scripts são do próprio site."""
    for arquivo in [
        *PAGINAS_HTML,
        *(SITE / n for n in ("estilo.css", "site.js", "movimento.js")),
    ]:
        texto = arquivo.read_text(encoding="utf-8")
        assert "googleapis" not in texto and "gstatic" not in texto
        externos = re.findall(r'(?:src|href)="(https?://[^"]+)"', texto)
        recursos = [u for u in externos if re.search(r"\.(?:js|css|woff2?|ttf)$", u)]
        assert not recursos, (arquivo.name, recursos)
        assert '<script src="http' not in texto


def test_fontes_do_site_sao_woff2_leves_e_existem():
    """Os TTF inteiros eram ~350 KB da primeira visita; o WOFF2 recortado (scripts/gerar_fontes_web)."""
    css = (SITE / "estilo.css").read_text(encoding="utf-8")
    fontes = re.findall(r'url\("/fontes/([^"]+)"\) format\("([^"]+)"\)', css)
    assert {formato for _, formato in fontes} == {"woff2"}
    precarregada = re.findall(
        r'<link rel="preload" href="/fontes/([^"]+)" as="font" type="font/woff2"',
        (SITE / "index.html").read_text(encoding="utf-8"),
    )
    assert precarregada and precarregada[0] in {nome for nome, _ in fontes}
    total = sum((SITE / "fontes" / nome).stat().st_size for nome, _ in fontes)
    assert total < 120 * 1024
    assert not list((SITE / "fontes").glob("*.ttf"))


def test_planos_do_site_sao_os_do_app():
    texto = (SITE / "precos.html").read_text(encoding="utf-8")
    tabela = texto[texto.index('<table class="planos') : texto.index("</table>")]
    # Sim e Não aparecem como ✓ e — (a palavra fica no aria-label, para o leitor de tela)
    icones = {"✓": "Sim", "—": "Não"}
    no_site = {
        recurso: [
            icones.get(c, c)
            for c in (
                re.sub(r"<[^>]+>", "", c)
                for c in re.findall(r"<td>(.*?)</td>", celulas)
            )
        ]
        for recurso, celulas in re.findall(
            r'<tr><th scope="row">(.*?)</th>(.*?)</tr>', tabela
        )
    }
    for linha in planos.tabela_de_planos():
        esperado = [esc(linha[nome]) for nome in ("Gratuito", "Plus", "Pro")]
        assert no_site[esc(linha["Recurso"])] == esperado, linha["Recurso"]
    assert "R$" not in texto  # sem preço enquanto não houver cobrança real
    assert "modo de teste" in texto


def test_precos_pessoa_e_casa_sem_preco():
    """Plano do site para quem analisa (D1): Pessoa e Casa, uma faixa grátis, nenhum preço."""
    texto = (SITE / "precos.html").read_text(encoding="utf-8")
    sem_tags = html.unescape(re.sub(r"<[^>]+>", " ", texto))
    for frase in (
        "Para conhecer, de graça",
        "Pessoa",
        "Casa",
        "por assento",
        "em construção",
        "definido antes do lançamento",  # ADR 0029, Emenda 1
        "toda conta usa",
    ):
        assert frase in sem_tags, frase
    assert "R$" not in texto
    # nenhum valor em dinheiro: número seguido de "reais", "/mês", "por mês" ou "/ano"
    assert not re.search(
        r"\d\s*(reais|/\s*m[eê]s|por m[eê]s|/\s*ano|por ano)", sem_tags
    )


def test_precos_anunciam_mensal_de_verdade():
    """ADR 0054: mensal cobrado um mês por vez, sem fidelidade, e o cancelamento no próprio app."""
    texto = (SITE / "precos.html").read_text(encoding="utf-8")
    for frase in (
        "Mensal de verdade",
        "Sem fidelidade",
        "cobra um mês por vez",
        "Planos e assinatura",
    ):
        assert frase in texto, frase


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
    html = markdown_para_html(
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
    assert "Dados auditáveis para quem analisa empresas no Brasil." in inicio
    assert 'content="https://tickerlab.com.br/marca/compartilhamento.png"' in inicio
    assert (SITE / "marca" / "compartilhamento.png").exists()


def test_assinatura_antiga_sumiu():
    """ADR 0099: a assinatura é a nova em toda página; a antiga (para o investidor) não sobra."""
    paginas = sorted(SITE.glob("*.html"))
    assert paginas
    for pagina in paginas:
        texto = pagina.read_text(encoding="utf-8")
        assert "Menos ruído" not in texto, pagina.name
        assert "Mais inteligência para investir" not in texto, pagina.name


def test_css_e_js_tem_a_versao_do_conteudo_no_endereco():
    """A Cloudflare guarda o CSS e o JS por horas: sem a versão no endereço, quem visita depois de
    um deploy recebe o HTML novo com o estilo antigo."""
    import hashlib

    for nome in ("estilo.css", "site.js", "movimento.js"):
        conteudo = (SITE / nome).read_text(
            encoding="utf-8"
        )  # quebras de linha iguais em todo SO
        versao = hashlib.sha256(conteudo.encode("utf-8")).hexdigest()[:12]
        for arquivo in PAGINAS_HTML:
            assert f'"/{nome}?v={versao}"' in arquivo.read_text(encoding="utf-8"), (
                arquivo.name,
                nome,
            )


MENU_DO_TOPO = [
    ("/dados.html", "Dados"),
    ("/relatorios.html", "Relatórios"),
    ("/como-funciona.html", "Como funciona"),
    ("/precos.html", "Planos"),
    ("/sobre.html", "Sobre"),
]


def _menu_principal(texto: str) -> list[tuple[str, str]]:
    nav = texto.split('<nav id="menu-principal"')[1].split("</nav>")[0]
    return re.findall(r'<a href="([^"]+)"[^>]*>([^<]+)</a>', nav)


def test_menu_do_topo_tem_os_cinco_itens_do_plano_em_todas_as_paginas():
    """Plano do site para quem analisa (18/10/2026, ADR 0099); "pode" do Tiago em 23/10/2026."""
    for arquivo in PAGINAS_HTML:
        assert _menu_principal(arquivo.read_text(encoding="utf-8")) == MENU_DO_TOPO, (
            arquivo.name
        )


def test_o_que_saiu_do_topo_continua_no_rodape():
    for arquivo in PAGINAS_HTML:
        rodape = arquivo.read_text(encoding="utf-8").split('<footer class="rodape')[1]
        for href, nome in (
            ("/produto.html", "Produto"),
            ("/dados.html", "Dados"),
            ("/relatorios.html", "Relatórios"),
            ("/ferramentas.html", "Ferramentas grátis"),
            ("/aprender.html", "Aprender"),
        ):
            assert f'<a href="{href}">{nome}</a>' in rodape, (arquivo.name, nome)


def test_toda_pagina_do_mapa_do_site_tem_link_de_outra_pagina():
    """O dados.html e o relatório das elétricas ficaram sem link nenhum: só o Google chegava."""
    linkadas = set()
    for arquivo in PAGINAS_HTML:
        for alvo in re.findall(
            r'href="/([^"#?]*)', arquivo.read_text(encoding="utf-8")
        ):
            if (alvo or "index.html") != arquivo.name:
                linkadas.add(alvo or "index.html")
    mapa = (SITE / "sitemap.xml").read_text(encoding="utf-8")
    for alvo in re.findall(r"<loc>https://tickerlab\.com\.br/([^<]*)</loc>", mapa):
        assert (alvo or "index.html") in linkadas, alvo


def test_olho_das_calculadoras_leva_a_vitrine():
    """Ferramentas saiu do topo: quem chega numa calculadora pelo Google volta à vitrine por aqui."""
    calculadoras = [
        a for a in PAGINAS_HTML if "data-ferramenta=" in a.read_text(encoding="utf-8")
    ]
    assert len(calculadoras) >= 10
    for arquivo in calculadoras:
        texto = arquivo.read_text(encoding="utf-8")
        assert (
            '<a class="olho" href="/ferramentas.html">Ferramentas grátis</a>' in texto
        ), arquivo.name


def test_celular_tem_botao_que_abre_o_menu_em_todas_as_paginas():
    """Sem ele, abaixo de 860 px o topo ficava só com a marca, o tema e "Abrir o app"."""
    for arquivo in PAGINAS_HTML:
        topo = arquivo.read_text(encoding="utf-8").split("</header>")[0]
        assert 'data-menu-botao=""' in topo, arquivo.name
        assert 'aria-controls="menu-principal"' in topo, arquivo.name
        assert '<nav id="menu-principal" aria-label="Principal">' in topo, arquivo.name


def test_pagina_produto_mostra_o_que_existe_e_o_que_vem():
    from src import modulos

    texto = (SITE / "produto.html").read_text(encoding="utf-8")
    for modulo in modulos.MODULOS[:6]:
        assert f'id="{modulo.chave}"' in texto
        for f in modulo.funcionalidades:
            assert esc(f.nome) in texto
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
        assert esc(frase) in texto, frase
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
        # o rodapé do site (um cartão pode ter o próprio <footer>, como o painel da inicial)
        topo, rodape = (
            texto.split("</header>")[0],
            texto.split('<footer class="rodape')[1],
        )
        assert '<a href="/sobre.html"' in topo, arquivo.name
        assert '<a href="/sobre.html">' in rodape, arquivo.name


def test_metodologia_explica_o_selo_e_lista_todas_as_regras():
    """Selo de qualidade (série 1 da base de ML, PR 4): as regras são públicas e as mesmas do app."""
    from src.qualidade_texto import ANCORA_NO_SITE, EXPLICACAO_DO_SELO, REGRAS

    texto = (SITE / "metodologia.html").read_text(encoding="utf-8")
    assert f'id="{ANCORA_NO_SITE}"' in texto
    assert esc(EXPLICACAO_DO_SELO) in texto
    for regra in REGRAS.values():
        assert esc(regra.titulo) in texto
        assert esc(regra.o_que_confere) in texto


def test_metodologia_explica_padroes_notas_e_formulas():
    """Relatório da empresa (série 2 da base de ML, PR 8): as regras das notas e dos padrões e as
    fórmulas são públicas, com os mesmos textos (e os mesmos limites) do app."""
    from src import metodologia_das_notas as m

    texto = (SITE / "metodologia.html").read_text(encoding="utf-8")
    assert f'id="{m.ANCORA_NO_SITE}"' in texto
    for paragrafo in (*m.PADROES, *m.NOTAS):
        assert esc(paragrafo) in texto
    for item in (*m.GRUPOS, *m.INDICADORES_DAS_NOTAS):
        assert esc(item.nome) in texto
    for formula in m.FORMULAS:
        assert esc(formula.formula) in texto
        assert esc(formula.leitura) in texto


def test_novidades_no_rodape_de_todas_as_paginas_e_no_mapa_do_site():
    for arquivo in PAGINAS_HTML:
        rodape = arquivo.read_text(encoding="utf-8").split("<footer", 1)[1]
        assert '<a href="/novidades.html">Novidades</a>' in rodape, arquivo.name
    assert "https://tickerlab.com.br/novidades.html" in (
        SITE / "sitemap.xml"
    ).read_text(encoding="utf-8")


def test_security_txt_existe_e_nao_esta_perto_de_vencer():
    """RFC 9116: o `Expires` do security.txt vale um ano; quem lê ignora arquivo vencido.
    Falha 30 dias antes: gere de novo com a data nova (SECURITY_TXT_EXPIRA em web/src/entry-server.tsx)."""
    from datetime import UTC, datetime, timedelta

    texto = (SITE / ".well-known" / "security.txt").read_text(encoding="utf-8")
    assert "Contact: mailto:contato@tickerlab.com.br" in texto
    expira = re.search(r"^Expires: (\S+)$", texto, re.MULTILINE)
    assert expira, "falta o campo Expires"
    vence = datetime.fromisoformat(expira.group(1).replace("Z", "+00:00"))
    assert vence - datetime.now(UTC) > timedelta(days=30), (
        "renove o Expires do security.txt"
    )
