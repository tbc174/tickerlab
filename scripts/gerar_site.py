"""Gera o site público do TickerLab (tickerlab.com.br) na pasta `site/`.

    python -m scripts.gerar_site

O site é estático (HTML, CSS e um pouco de JavaScript), separado do app (app.tickerlab.com.br):
ele explica o produto e leva ao app; o app é onde se trabalha (blueprint, seção 3). Tudo o que ele
mostra vem do próprio projeto, para não haver duas versões da verdade:

- cores e fontes: `src/marca.py` e `static/` (fontes servidas pelo próprio site, sem Google Fonts);
- planos: `src/planos.py` (os mesmos limites que o app aplica; sem preço, porque não há cobrança real);
- busca do topo: o catálogo `conteudo/catalogo_de_ativos.csv`;
- termos e privacidade: `conteudo/termos.md` e `conteudo/privacidade.md`;
- o relatório de exemplo e as imagens dele: gerados agora pelo mesmo código do app, com os dados de
  exemplo guardados no projeto (rotulados como exemplo).

Rodar de novo sempre que esses conteúdos mudarem; um teste confere que `site/` está em dia.
"""

import hashlib
import html
import json
import re
import shutil
import sys
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
from PIL import Image

from src import catalogo, marca, planos, previa_pdf, relatorios
from src.estilos_pdf import ESTILOS

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "site"
URL_DO_SITE = "https://tickerlab.com.br"
URL_DO_APP = "https://app.tickerlab.com.br"
URL_DO_CODIGO = "https://github.com/tbc174/tickerlab"
EMAIL_DE_CONTATO = "contato@tickerlab.com.br"
# True enquanto o login do Google estiver em "modo Teste" (só e-mails convidados entram);
# o acesso foi aberto em 11/10/2026 (app do Google publicado em "Em produção")
BETA_FECHADO = False
TICKER_DO_EXEMPLO = "PETR4.SA"
AVISO = (
    "Nada aqui é recomendação de investimento. Os dados vêm do Yahoo "
    "Finance e podem ter atraso ou erros. Rentabilidade passada não garante resultado futuro."
)


def esc(texto: str) -> str:
    return html.escape(texto, quote=True)


def link_do_app(pagina: str = "", **parametros: str) -> str:
    consulta = "&".join(f"{k}={v}" for k, v in parametros.items())
    return f"{URL_DO_APP}/{pagina}" + (f"?{consulta}" if consulta else "")


# --- Markdown dos termos e da política (só o que esses textos usam) -----------------------
def _inline(texto: str) -> str:
    texto = esc(texto)
    texto = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", texto)
    texto = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", texto)
    texto = re.sub(r"`(.+?)`", r"<code>\1</code>", texto)
    return re.sub(
        r"\[(.+?)\]\((https?://[^)\s]+)\)",
        r'<a href="\2" rel="noopener">\1</a>',
        texto,
    )


def markdown_para_html(texto: str) -> str:
    """Títulos, parágrafos, listas, tabelas, negrito, itálico, código e links."""
    saida: list[str] = []
    linhas = texto.splitlines()
    i = 0
    while i < len(linhas):
        linha = linhas[i].rstrip()
        if not linha.strip():
            i += 1
        elif m := re.match(r"^(#{1,4})\s+(.*)", linha):
            nivel = min(len(m.group(1)) + 1, 4)  # o h1 é o título da página
            saida.append(f"<h{nivel}>{_inline(m.group(2))}</h{nivel}>")
            i += 1
        elif linha.lstrip().startswith(("- ", "* ")):
            itens = []
            while i < len(linhas) and linhas[i].lstrip().startswith(("- ", "* ")):
                itens.append(f"<li>{_inline(linhas[i].lstrip()[2:])}</li>")
                i += 1
            saida.append("<ul>" + "".join(itens) + "</ul>")
        elif re.match(r"^\d+\.\s", linha.lstrip()):
            itens = []
            while i < len(linhas) and re.match(r"^\d+\.\s", linhas[i].lstrip()):
                itens.append(
                    f"<li>{_inline(linhas[i].lstrip().split('. ', 1)[1])}</li>"
                )
                i += 1
            saida.append("<ol>" + "".join(itens) + "</ol>")
        elif linha.startswith("|"):
            tabela = []
            while i < len(linhas) and linhas[i].startswith("|"):
                tabela.append(
                    [c.strip() for c in linhas[i].strip().strip("|").split("|")]
                )
                i += 1
            cabecalho, corpo = (
                tabela[0],
                [
                    t
                    for t in tabela[1:]
                    if not all(re.fullmatch(r":?-+:?", c) for c in t)
                ],
            )
            saida.append(
                '<div class="tabela"><table><thead><tr>'
                + "".join(f"<th>{_inline(c)}</th>" for c in cabecalho)
                + "</tr></thead><tbody>"
                + "".join(
                    "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in t) + "</tr>"
                    for t in corpo
                )
                + "</tbody></table></div>"
            )
        else:
            paragrafo = []
            while (
                i < len(linhas)
                and linhas[i].strip()
                and not re.match(r"^(#|\||- |\* |\d+\.\s)", linhas[i].lstrip())
            ):
                paragrafo.append(linhas[i].strip())
                i += 1
            saida.append(f"<p>{_inline(' '.join(paragrafo))}</p>")
    return "\n".join(saida)


# --- peças comuns ---------------------------------------------------------------------------
# o topo do símbolo segue o tema (marinho no claro, claro no escuro); a haste é sempre elétrica
SIMBOLO = marca.simbolo_svg(topo="currentColor")
LOGO = (
    f'<a class="marca" href="/" aria-label="TickerLab, página inicial">{SIMBOLO}'
    "<span>Ticker<b>Lab</b></span></a>"
)


# ícones do Material ("dark_mode" e "light_mode"); o rótulo muda pelo site.js
BOTAO_DO_TEMA = (
    '<button class="tema" type="button" data-tema-botao aria-label="Usar o tema escuro">'
    '<svg class="lua" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
    '<path d="M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.39 5.39 0 0 1-4.4 2.26 5.4 5.4 0 0 1'
    '-3.14-9.8c-.44-.06-.9-.1-1.36-.1z"/></svg>'
    '<svg class="sol" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
    '<path d="M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM2 13h2a1 1 0 0 0 0-2H2a1 1 0 0 0 0 2zm18 0h2a1'
    " 1 0 0 0 0-2h-2a1 1 0 0 0 0 2zM11 2v2a1 1 0 0 0 2 0V2a1 1 0 0 0-2 0zm0 18v2a1 1 0 0 0 2 0v-2a1"
    " 1 0 0 0-2 0zM5.99 4.58a1 1 0 0 0-1.41 1.41l1.06 1.06a1 1 0 0 0 1.41-1.41L5.99 4.58zm12.37"
    " 12.37a1 1 0 0 0-1.41 1.41l1.06 1.06a1 1 0 0 0 1.41-1.41l-1.06-1.06zm1.06-10.96a1 1 0 0 0-1.41"
    "-1.41l-1.06 1.06a1 1 0 0 0 1.41 1.41l1.06-1.06zM7.05 18.36a1 1 0 0 0-1.41-1.41l-1.06 1.06a1 1"
    ' 0 0 0 1.41 1.41l1.06-1.06z"/></svg>'
    "</button>"
)
# Roda no <head>, antes de pintar a página: aplica o tema escolhido da última vez (sem piscar o
# claro) e avisa o CSS que há JavaScript. O site abre claro; o escuro é escolha de quem visita.
TEMA_SALVO = (
    '<script>document.documentElement.classList.add("com-js");'
    'try { if (localStorage.getItem("tema") === "escuro") '
    'document.documentElement.dataset.tema = "escuro"; } catch (e) {}</script>'
)


def topo(atual: str) -> str:
    itens = [
        ("/#produto", "Produto"),
        ("/#relatorios", "Relatórios"),
        ("/metodologia.html", "Metodologia"),
        ("/precos.html", "Planos"),
    ]
    links = "".join(
        f'<a href="{href}"{" aria-current=page" if href == atual else ""}>{nome}</a>'
        for href, nome in itens
    )
    return (
        '<header class="topo"><div class="faixa">'
        f'{LOGO}<nav aria-label="Principal">{links}</nav>'
        f"{BOTAO_DO_TEMA}"
        f'<a class="botao primario pequeno" href="{link_do_app()}">Abrir o app</a>'
        "</div></header>"
    )


# a assinatura institucional do manual de identidade
ASSINATURA = "Menos ruído. Mais inteligência para investir."
RODAPE = f"""<footer class="rodape escura"><div class="faixa">
<div>{LOGO}<p class="apagado">{ASSINATURA}</p></div>
<nav aria-label="Rodapé">
<a href="/metodologia.html">Fontes e metodologia</a>
<a href="/precos.html">Planos</a>
<a href="/termos.html">Termos de uso</a>
<a href="/privacidade.html">Privacidade</a>
<a href="{URL_DO_CODIGO}" rel="noopener">Código no GitHub</a>
<a href="mailto:{EMAIL_DE_CONTATO}">{EMAIL_DE_CONTATO}</a>
</nav>
<p class="aviso">{esc(AVISO)}</p>
</div></footer>"""


def _versao(conteudo: str) -> str:
    """Um pedaço do hash do arquivo, para pôr no endereço: a Cloudflare e o navegador guardam o CSS
    e o JS por horas, e um endereço novo a cada mudança faz todos buscarem a versão nova na hora."""
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()[:12]


def pagina(
    caminho: str, titulo: str, descricao: str, corpo: str, atual: str = ""
) -> str:
    titulo_completo = "TickerLab" if caminho == "/" else f"{titulo} · TickerLab"
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(titulo_completo)}</title>
<meta name="description" content="{esc(descricao)}">
<link rel="canonical" href="{URL_DO_SITE}{caminho}">
<meta property="og:title" content="{esc(titulo_completo)}">
<meta property="og:description" content="{esc(descricao)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{URL_DO_SITE}{caminho}">
<meta property="og:image" content="{URL_DO_SITE}/marca/compartilhamento.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="TickerLab: {esc(ASSINATURA)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="{marca.CLARO}">
{TEMA_SALVO}
<link rel="icon" href="/marca/simbolo.svg" type="image/svg+xml">
<link rel="icon" href="/marca/icone.png" type="image/png">
<link rel="preload" href="/fontes/Manrope-VariableFont_wght.ttf" as="font" type="font/ttf" crossorigin>
<link rel="stylesheet" href="/estilo.css?v={_versao(css())}">
<script src="/site.js?v={_versao(JS)}" defer></script>
</head>
<body>
<a class="pular" href="#conteudo">Pular para o conteúdo</a>
{topo(atual)}
<main id="conteudo">
{corpo}
</main>
{RODAPE}
</body>
</html>
"""


# --- páginas ---------------------------------------------------------------------------------
def _tabela_de_planos() -> str:
    linhas = planos.tabela_de_planos()
    nomes = [planos.limites_do(p).nome for p in planos.PLANOS]
    cabecalho = "<th scope=col>Recurso</th>" + "".join(
        f"<th scope=col>{esc(n)}</th>" for n in nomes
    )
    corpo = "".join(
        f"<tr><th scope=row>{esc(l['Recurso'])}</th>"
        + "".join(f"<td>{esc(l[n])}</td>" for n in nomes)
        + "</tr>"
        for l in linhas
    )
    return (
        '<div class="tabela"><table class="planos"><thead><tr>'
        + cabecalho
        + "</tr></thead><tbody>"
        + corpo
        + "</tbody></table></div>"
    )


def _cobranca() -> str:
    pagos = [planos.limites_do(p).nome for p in planos.COM_COBRANCA]
    em_breve = [
        planos.limites_do(p).nome
        for p in planos.PLANOS
        if p != "gratuito" and p not in planos.COM_COBRANCA
    ]
    return (
        f"O plano Gratuito não pede cartão. A assinatura do {' e do '.join(pagos)} funciona "
        "em <strong>modo de teste</strong> do Stripe: nenhum dinheiro real é cobrado enquanto "
        "o projeto estiver em demonstração. "
        + (
            f"O {' e o '.join(em_breve)} já tem os limites definidos; a assinatura dele chega "
            "em breve."
            if em_breve
            else ""
        )
    )


def _aviso_de_acesso() -> str:
    if not BETA_FECHADO:
        return ""
    return (
        '<p class="selo-beta"><span>Beta fechado</span> O app está em fase de testes: por '
        "enquanto, só contas convidadas entram com o Google.</p>"
    )


def _vitrine(estilos_disponiveis: list[str]) -> str:
    """O Report Studio na landing: imagens do PDF de verdade, trocando estilo e página."""
    botoes_de_estilo = "".join(
        f'<button type="button" data-estilo="{e}" aria-pressed="{"true" if i == 0 else "false"}">'
        f"{esc(ESTILOS[e].nome)}</button>"
        for i, e in enumerate(estilos_disponiveis)
    )
    primeiro = estilos_disponiveis[0]
    return f"""
<div class="vitrine" data-vitrine>
  <div class="controles" role="group" aria-label="Estilo do relatório">{botoes_de_estilo}</div>
  <div class="folhas">
    <img src="/relatorio/{primeiro}-1.webp" width="560" height="792" loading="lazy"
         alt="Capa do relatório de exemplo de {TICKER_DO_EXEMPLO}" data-pagina="1">
    <img src="/relatorio/{primeiro}-2.webp" width="560" height="792" loading="lazy"
         alt="Segunda página do relatório de exemplo, com o resumo executivo e os números-chave"
         data-pagina="2">
  </div>
  <p class="legenda">Imagens do PDF real gerado pelo app, com dados de exemplo guardados no
  projeto. Só as cores mudam entre os estilos: os números são os mesmos.</p>
</div>"""


def landing(estilos: list[str]) -> str:
    exemplos = "".join(
        f'<a class="ticker" href="{link_do_app("visao-geral", ticker=s)}">'
        f"{esc(catalogo.rotulo(s).split(' · ')[0])}</a>"
        for s in catalogo.EXEMPLOS
    )
    cartoes_resultado = [
        (
            "Entender um ativo",
            (
                "Retorno, risco, maiores quedas e meses bons e ruins de uma ação, ETF, índice ou "
                "cripto, cada número explicado em português."
            ),
            link_do_app("visao-geral", ticker=TICKER_DO_EXEMPLO),
            "Analisar PETR4",
        ),
        (
            "Organizar a carteira",
            (
                "Envie a planilha de posição da Área do Investidor da B3 e veja concentração e "
                "risco. O arquivo é lido só na memória e não fica guardado."
            ),
            link_do_app("relatorio"),
            "Ver a minha carteira",
        ),
        (
            "Criar um relatório",
            (
                "Escolha modelo, seções e estilo, veja a prévia do PDF de verdade e gere um "
                "relatório para ler, imprimir ou enviar."
            ),
            link_do_app("relatorio"),
            "Abrir o estúdio",
        ),
    ]
    resultados = "".join(
        f'<article class="cartao"><h3>{esc(t)}</h3><p>{esc(d)}</p>'
        f'<a class="seta" href="{href}">{esc(rotulo)}</a></article>'
        for t, d, href, rotulo in cartoes_resultado
    )
    passos = [
        (
            "Escolha o que investigar",
            "Busque por código ou empresa: B3, EUA, índices e cripto.",
        ),
        (
            "Explore os dados",
            "Gráficos, risco e testes de estratégia no passado, com custos.",
        ),
        ("Guarde e compartilhe", "Monte um PDF com as seções que importam e baixe."),
    ]
    como = "".join(
        f'<li><span class="numero">{i}</span><h3>{esc(t)}</h3><p>{esc(d)}</p></li>'
        for i, (t, d) in enumerate(passos, 1)
    )
    publicos = [
        (
            "Quem está começando",
            (
                "Quer entender uma ação antes de investir, sem jargão. O tutorial guia a primeira "
                "análise em 2 minutos."
            ),
        ),
        (
            "Quem estuda estratégias",
            (
                "Testa regras de compra e venda com custos, validação fora da amostra e teste "
                "contra o acaso, e vê quando a estratégia não funciona."
            ),
        ),
        (
            "Quem quer organizar a carteira",
            (
                "Vê concentração, número efetivo de ativos e o comportamento da carteira de hoje no "
                "passado, comparada ao Ibovespa."
            ),
        ),
    ]
    para_quem = "".join(
        f'<article class="cartao"><h3>{esc(t)}</h3><p>{esc(d)}</p></article>'
        for t, d in publicos
    )
    confianca = [
        (
            "Dados",
            (
                "Preços diários do Yahoo Finance, ajustados por dividendos e desdobramentos. Não é "
                "tempo real: os dados podem ter atraso, falhas e ajustes posteriores."
            ),
        ),
        (
            "Carteira B3",
            (
                "A API da Área do Investidor só atende empresas credenciadas. Por isso o caminho é "
                "a planilha que você mesmo baixa; ela é lida só na memória."
            ),
        ),
        (
            "Privacidade",
            (
                "Login com o Google; você exporta ou apaga a sua conta quando quiser. O site não usa "
                "Google Fonts nem ferramentas de rastreamento."
            ),
        ),
        (
            "Método",
            (
                "A decisão de um dia só vale no dia seguinte (sem olhar o futuro), custos entram em "
                "todo teste e o app mostra quando algo não funciona."
            ),
        ),
    ]
    pilares = "".join(
        f'<article class="pilar"><h3>{esc(t)}</h3><p>{esc(d)}</p></article>'
        for t, d in confianca
    )
    perguntas = [
        (
            "O TickerLab recomenda o que comprar?",
            (
                "Não. O TickerLab mostra o que aconteceu no passado e explica cada "
                "número. Nada aqui é recomendação de investimento."
            ),
        ),
        (
            "Os preços são em tempo real?",
            (
                "Não. O app usa o histórico diário do Yahoo Finance, que pode ter atraso. Cada "
                "relatório diz a data e a hora dos dados usados."
            ),
        ),
        (
            "Vocês se conectam à minha conta na B3?",
            (
                "Não. A API da B3 é só para empresas credenciadas. Você envia a planilha de posição "
                "que baixa na Área do Investidor; ela não fica guardada."
            ),
        ),
        (
            "O que fica guardado sobre mim?",
            (
                "Seu perfil do Google (nome, e-mail), preferências, favoritos, simulações salvas e o "
                "registro dos relatórios gerados (não o PDF). Detalhes na Política de privacidade."
            ),
        ),
        (
            "Preciso pagar?",
            (
                "Não para começar: o plano Gratuito não pede cartão. Hoje a cobrança dos planos "
                "pagos está em modo de teste, sem dinheiro real."
            ),
        ),
        (
            "Como apago a minha conta?",
            (
                "Em Minha conta → Meus dados e privacidade: dá para exportar tudo em JSON e apagar a "
                "conta, o que também encerra a assinatura."
            ),
        ),
    ]
    faq = "".join(
        f"<details><summary>{esc(p)}</summary><p>{esc(r)}</p></details>"
        for p, r in perguntas
    )
    corpo = f"""
<div class="escura">
<section class="heroi faixa" aria-labelledby="titulo-heroi">
  <div class="heroi-texto">
    <p class="olho">Pesquisa quantitativa · B3 e EUA</p>
    <h1 id="titulo-heroi">Vá além do preço. Entenda o ativo por trás do ticker.</h1>
    <p class="subtitulo">Pesquise ativos, explore análises quantitativas e transforme o seu
    estudo em relatórios claros, com cada número explicado em português.</p>
    <form class="busca" action="{URL_DO_APP}/visao-geral" method="get" role="search"
          data-busca data-app="{URL_DO_APP}">
      <label for="busca-ticker">Busque um ativo</label>
      <div class="campo">
        <input id="busca-ticker" name="ticker" type="text" autocomplete="off"
               placeholder="PETR4, Petrobras, AAPL, Ibovespa…" role="combobox"
               aria-autocomplete="list" aria-expanded="false" aria-controls="sugestoes">
        <button class="botao primario" type="submit">Analisar</button>
      </div>
      <ul id="sugestoes" role="listbox" hidden></ul>
    </form>
    <p class="exemplos"><span>Experimente:</span> {exemplos}</p>
    <div class="acoes">
      <a class="botao secundario" href="/relatorio/exemplo-{TICKER_DO_EXEMPLO}.pdf">Ver um relatório de exemplo (PDF)</a>
    </div>
    {_aviso_de_acesso()}
  </div>
  <div class="heroi-visual" aria-hidden="true">
    <img src="/relatorio/{estilos[0]}-2.webp" width="560" height="792" alt="">
  </div>
</section>
</div>

<section id="produto" class="faixa secao" aria-labelledby="titulo-resultados">
  <p class="olho">O que você leva</p>
  <h2 id="titulo-resultados">Três resultados, uma jornada</h2>
  <div class="grade tres">{resultados}</div>
</section>

<section id="relatorios" class="faixa secao" aria-labelledby="titulo-estudio">
  <p class="olho">Report Studio</p>
  <h2 id="titulo-estudio">Sua pesquisa merece mais que uma tela</h2>
  <p class="subtitulo">Modelo Executivo ou Pesquisa completa, seções na ordem que você quiser,
  três estilos e a prévia do PDF de verdade antes de baixar. Toda versão tem resumo,
  metodologia e os limites da análise.</p>
  {_vitrine(estilos)}
</section>

<section class="faixa secao" aria-labelledby="titulo-como">
  <p class="olho">Como funciona</p>
  <h2 id="titulo-como">Em três passos</h2>
  <ol class="passos">{como}</ol>
</section>

<section class="faixa secao" aria-labelledby="titulo-quem">
  <p class="olho">Para quem é</p>
  <h2 id="titulo-quem">Feito para quem quer entender, não para quem quer palpite</h2>
  <div class="grade tres">{para_quem}</div>
</section>

<div class="escura">
<section class="faixa secao" aria-labelledby="titulo-confianca">
  <p class="olho">Confiança</p>
  <h2 id="titulo-confianca">De onde vêm os números e o que eles não dizem</h2>
  <div class="grade quatro">{pilares}</div>
  <p><a class="seta" href="/metodologia.html">Fontes e metodologia em detalhe</a></p>
</section>
</div>

<section class="faixa secao" aria-labelledby="titulo-planos">
  <p class="olho">Planos</p>
  <h2 id="titulo-planos">Escolha o nível de pesquisa que faz sentido para você</h2>
  {_tabela_de_planos()}
  <p class="apagado">{_cobranca()}</p>
</section>

<section class="faixa secao" aria-labelledby="titulo-faq">
  <p class="olho">Perguntas</p>
  <h2 id="titulo-faq">Perguntas frequentes</h2>
  <div class="faq">{faq}</div>
</section>

<section class="faixa secao final" aria-labelledby="titulo-final">
  <h2 id="titulo-final">Comece pela sua primeira análise</h2>
  <p class="subtitulo">O tutorial do app guia você em 2 minutos, com dados de verdade.</p>
  <a class="botao primario" href="{link_do_app("visao-geral", ticker=TICKER_DO_EXEMPLO)}">Experimentar com PETR4</a>
</section>
"""
    return pagina(
        "/",
        "TickerLab",
        "Pesquise ativos da B3 e dos EUA, entenda retorno e risco com cada número explicado "
        "e gere relatórios em PDF. Nada é recomendação de investimento.",
        corpo,
    )


def precos() -> str:
    corpo = f"""
<section class="faixa secao estreita">
  <p class="olho">Planos</p>
  <h1>Escolha o nível de pesquisa que faz sentido para você</h1>
  <p class="subtitulo">Os limites abaixo são os mesmos que o app aplica. Ao chegar a um
  limite, nada do que você já fez é perdido.</p>
  {_tabela_de_planos()}
  <h2>Cobrança</h2>
  <p>{_cobranca()}</p>
  <p>Quando houver cobrança real, os valores, a renovação e a forma de cancelar aparecem aqui e
  nos Termos de uso antes de qualquer mudança. Você pode cancelar a assinatura no próprio app
  (Minha conta → Planos e assinatura).</p>
  <h2>Os números que contam</h2>
  <ul>
    <li><strong>Relatórios:</strong> contam os gerados nas últimas 24 horas. A prévia do PDF não
    conta; excluir um relatório da biblioteca não devolve o limite.</li>
    <li><strong>Simulações e favoritos:</strong> o que fica guardado na sua conta.</li>
    <li><strong>Ativos na carteira:</strong> quantos ativos uma simulação de carteira aceita.</li>
  </ul>
  {_aviso_de_acesso()}
  <p><a class="botao primario" href="{link_do_app("planos")}">Ver no app</a></p>
</section>"""
    return pagina(
        "/precos.html",
        "Planos",
        "Gratuito, Plus e Pro: o que cada plano do TickerLab inclui, com os mesmos limites do "
        "app. Cobrança em modo de teste.",
        corpo,
        "/precos.html",
    )


def metodologia() -> str:
    corpo = f"""
<section class="faixa secao estreita texto-longo">
  <p class="olho">Confiança</p>
  <h1>Fontes e metodologia</h1>
  <p class="subtitulo">De onde vêm os números, como são calculados e o que eles não dizem.</p>

  <h2>Dados de mercado</h2>
  <ul>
    <li><strong>Fonte:</strong> Yahoo Finance, histórico diário de preços de fechamento,
    ajustados por dividendos e desdobramentos. O CDI e a Selic vêm do Banco Central.</li>
    <li><strong>Não é tempo real.</strong> Os dados podem ter atraso, lacunas e ajustes
    posteriores. O app guarda um histórico para não depender do Yahoo a cada visita e avisa
    quando usa dados guardados ou de exemplo.</li>
    <li><strong>Cobertura da busca:</strong> ações, units, FIIs, ETFs e BDRs negociados na B3
    (cadastro público da B3), as empresas do S&amp;P 500, os principais índices, cinco
    criptomoedas e câmbio. Outros códigos do Yahoo também podem ser digitados.</li>
  </ul>

  <h2>Como os números são calculados</h2>
  <ul>
    <li>Retornos diários a partir do fechamento; ano de 252 pregões.</li>
    <li>Volatilidade: desvio padrão dos retornos diários, anualizado.</li>
    <li>Índice de Sharpe: retorno anualizado menos a taxa livre de risco, dividido pela
    volatilidade anual.</li>
    <li>Maior queda (drawdown): a pior queda a partir de um topo anterior.</li>
  </ul>

  <h2>Testes de estratégia (backtest)</h2>
  <ul>
    <li><strong>Sem olhar o futuro:</strong> a decisão tomada com o fechamento de um dia só vale
    a partir do dia seguinte.</li>
    <li><strong>Com custos:</strong> cada compra e venda paga um custo; há também imposto e o
    rendimento do CDI no caixa nas páginas que permitem.</li>
    <li><strong>Validação:</strong> treino e teste, walk-forward, teste contra o acaso e Sharpe
    deflacionado, para separar sorte de padrão.</li>
    <li><strong>Limites:</strong> não há derrapagem nem falta de liquidez na simulação, e os
    ativos escolhidos hoje carregam viés de sobrevivência.</li>
  </ul>

  <h2>Research: eventos e fundamentos</h2>
  <ul>
    <li><strong>Eventos:</strong> os documentos que as empresas entregam aos reguladores, lidos
    uma vez por dia. Da <strong>CVM</strong> (empresas da B3): fatos relevantes, comunicados,
    avisos, proventos e resultados. Da <strong>SEC</strong> (empresas do S&amp;P 500): 8-K
    (resultados, mudanças na diretoria, aquisições...), 10-K (anual) e 10-Q (trimestral). Cada
    evento tem o link para o documento original.</li>
    <li><strong>Sinais de alerta:</strong> balanço (DFP ou ITR) entregue à CVM depois do prazo
    legal (a data de entrega é oficial; o prazo é calculado pelo TickerLab, sem feriados), aviso
    de atraso nos EUA (NT 10-K e NT 10-Q), troca de auditor, mudança de controle e vencimento
    antecipado de dívida.</li>
    <li><strong>Participações:</strong> investidores que declaram ter 5% ou mais de uma empresa
    dos EUA (13D, com intenção ativa, e 13G, passivo).</li>
    <li><strong>Pessoas de dentro:</strong> compras e vendas de ações por controladores,
    diretores e conselheiros. Na B3, o formulário mensal da CVM (somado por cargo, publicado até
    o dia 10 do mês seguinte); nos EUA, o Form 4 da SEC (em até 2 dias úteis, com a marcação de
    venda programada pelo plano 10b5-1). Mostramos o <strong>cargo</strong>, nunca o nome. Pela
    pesquisa, as compras costumam dizer mais que as vendas; ainda assim, é um fato, não uma
    recomendação.</li>
    <li><strong>Donos e fundos:</strong> quais fundos brasileiros têm cada ação da B3 (carteira
    mensal entregue à CVM, com as posições vendidas, a aposta na queda) e quais grandes gestores
    têm cada ação dos EUA (Form 13F trimestral da SEC). Como muitos fundos mantêm posições em
    sigilo por até 90 dias, mostramos a fatia dos fundos que informaram e só comparamos meses
    com cobertura parecida.</li>
    <li><strong>Newsletter:</strong> a edição da sua lista junta tudo isso num só lugar, na tela
    ou em PDF. É montada só com fatos dos documentos oficiais, em frases de modelo fixo (sem
    inteligência artificial), com o link de cada item, os parâmetros usados e os limites.</li>
    <li><strong>Relevância:</strong> a ordem da lista vem de pesos que você ajusta (tipo do
    evento, quão recente é, a fonte). É uma regra editorial para organizar a leitura, não uma
    previsão de preço.</li>
    <li><strong>Fundamentos:</strong> receita, margens, ROE, ROIC, dívida e múltiplos nos
    últimos 12 meses. Na B3, das demonstrações da CVM (DFP e ITR); nos EUA, dos números que as
    empresas marcam em XBRL nos relatórios 10-K e 10-Q entregues à SEC, respeitando o ano
    fiscal de cada uma (o da Apple termina em setembro). Bancos e seguradoras aparecem como "não
    se aplica" onde o indicador não faz sentido.</li>
  </ul>

  <h2>Carteira B3</h2>
  <p>A API da Área do Investidor da B3 só atende empresas credenciadas (com CNPJ, certificado
  digital e contrato). O TickerLab não tem essa conexão. Você baixa a planilha de posição na Área
  do Investidor e a envia no app: ela é lida <strong>só na memória</strong>, não fica guardada e
  não vai para os registros. A análise usa os pesos de hoje no passado: mostra risco e
  concentração, não o seu resultado real.</p>

  <h2>Relatórios em PDF</h2>
  <p>Os relatórios usam os mesmos cálculos do app. Cada um traz a data e a hora da coleta dos
  dados, os parâmetros, a seção "Metodologia e reprodutibilidade" e a seção obrigatória "Limites
  e cuidados". O resumo executivo só repete, em frases neutras, números do próprio relatório.</p>

  <h2>Privacidade e segurança</h2>
  <ul>
    <li>Login com o Google; o app não vê nem guarda a sua senha.</li>
    <li>Você exporta os seus dados (JSON) e apaga a conta quando quiser.</li>
    <li>O site e o app não usam Google Fonts nem ferramentas de análise de terceiros.</li>
    <li>Pagamentos (em modo de teste) pelo Stripe; o TickerLab não recebe dados de cartão.</li>
  </ul>
  <p>Detalhes na <a href="/privacidade.html">Política de privacidade</a>.</p>

  <h2>O que o TickerLab não é</h2>
  <p>Não é corretora, não executa ordens, não é consultoria e não é recomendação de
  investimento. É uma plataforma de informação e análise por assinatura; o enquadramento
  regulatório da oferta comercial está em avaliação.</p>
  <p>Dúvidas, correções e pedidos: <a href="mailto:{EMAIL_DE_CONTATO}">{EMAIL_DE_CONTATO}</a>.</p>
  <p class="apagado">Código aberto para conferência: <a href="{URL_DO_CODIGO}" rel="noopener">{URL_DO_CODIGO.removeprefix("https://")}</a>.</p>
</section>"""
    return pagina(
        "/metodologia.html",
        "Fontes e metodologia",
        "De onde vêm os dados do TickerLab, como os números são calculados, os limites dos "
        "testes de estratégia e como a carteira B3 e a privacidade são tratadas.",
        corpo,
        "/metodologia.html",
    )


def legal(caminho: str, arquivo: str, titulo: str, descricao: str) -> str:
    texto = (RAIZ / "conteudo" / arquivo).read_text(encoding="utf-8")
    texto = re.sub(r"^#\s+.*\n", "", texto, count=1)  # o título vira o h1 da página
    corpo = (
        f'<section class="faixa secao estreita texto-longo"><h1>{esc(titulo)}</h1>'
        f"{markdown_para_html(texto)}</section>"
    )
    return pagina(caminho, titulo, descricao, corpo, caminho)


def nao_encontrada() -> str:
    corpo = """
<section class="faixa secao estreita">
  <p class="olho">Erro 404</p>
  <h1>Esta página não existe</h1>
  <p class="subtitulo">O endereço pode ter mudado. Volte para o início ou abra o app.</p>
  <p><a class="botao primario" href="/">Ir para o início</a></p>
</section>"""
    return pagina("/404.html", "Página não encontrada", "Página não encontrada.", corpo)


# --- arquivos que não são páginas -----------------------------------------------------------
TEMA_CLARO = {
    "fundo": marca.CLARO,
    "superficie": marca.AZUL_CLARO,
    "destaque": "#ffffff",
    "linha": "rgba(10, 31, 68, 0.12)",
    "linha-forte": "rgba(10, 31, 68, 0.22)",
    "texto": marca.MARINHO,
    "apagado": marca.PAPEL_APAGADO,
    "sutil": marca.PAPEL_SUTIL,
    "azul": marca.AZUL,
    "azul-texto": marca.PAPEL_AZUL_TEXTO,
    "lab": marca.AZUL,
    "simbolo-topo": marca.MARINHO,
    "atencao": marca.PAPEL_ATENCAO,
    "sombra": "rgba(10, 31, 68, 0.18)",
}
TEMA_ESCURO = {
    "fundo": marca.FUNDO,
    "superficie": marca.SUPERFICIE,
    "destaque": marca.DESTAQUE,
    "linha": marca.LINHA,
    "linha-forte": marca.LINHA_FORTE,
    "texto": marca.TEXTO,
    "apagado": marca.TEXTO_APAGADO,
    "sutil": marca.TEXTO_SUTIL,
    "azul": marca.AZUL,
    "azul-texto": marca.AZUL_TEXTO,
    "lab": marca.AZUL_TEXTO,  # o elétrico some no marinho em texto deste tamanho
    "simbolo-topo": marca.CLARO,
    "atencao": marca.ATENCAO,
    "sombra": "rgba(0, 0, 0, 0.5)",
}
# As faixas marinhas (início, confiança, chamada final e rodapé) são escuras nos dois temas, como
# as peças do manual que alternam fundo escuro e claro; dentro delas, tudo sobe um degrau.
FAIXA_MARINHA = {
    **TEMA_ESCURO,
    "fundo": marca.MARINHO,
    "superficie": marca.DESTAQUE,
    "destaque": "#163160",
}


def _variaveis(tema: dict[str, str]) -> str:
    return " ".join(f"--{nome}: {valor};" for nome, valor in tema.items())


def css() -> str:
    return f"""/* gerado por scripts/gerar_site.py a partir de src/marca.py — não editar à mão */
@font-face {{ font-family: "Manrope"; src: url("/fontes/Manrope-VariableFont_wght.ttf") format("truetype"); font-weight: 200 800; font-display: swap; }}
@font-face {{ font-family: "JetBrains Mono"; src: url("/fontes/JetBrainsMono-VariableFont_wght.ttf") format("truetype"); font-weight: 100 800; font-display: swap; }}
:root {{
  {_variaveis(TEMA_CLARO)}
  --largura: 72rem; --raio: 14px;
  color-scheme: light;
}}
:root[data-tema="escuro"] {{ {_variaveis(TEMA_ESCURO)} color-scheme: dark; }}
.escura {{ {_variaveis(FAIXA_MARINHA)} color-scheme: dark; background: var(--fundo); color: var(--texto); }}
*, *::before, *::after {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{ margin: 0; background: var(--fundo); color: var(--texto);
  font: 400 1rem/1.6 "Manrope", system-ui, -apple-system, "Segoe UI", sans-serif;
  -webkit-font-smoothing: antialiased; }}
img {{ max-width: 100%; height: auto; display: block; }}
a {{ color: var(--azul-texto); text-underline-offset: 3px; }}
h1, h2, h3 {{ line-height: 1.12; letter-spacing: -0.03em; text-wrap: balance; margin: 0 0 .6em; }}
h1 {{ font-size: clamp(2.1rem, 5vw, 3.4rem); font-weight: 800; }}
h2 {{ font-size: clamp(1.6rem, 3.2vw, 2.3rem); font-weight: 800; }}
h3 {{ font-size: 1.12rem; font-weight: 700; letter-spacing: -0.01em; }}
p, li {{ max-width: 68ch; }}
code, .ticker {{ font-family: "JetBrains Mono", ui-monospace, monospace; font-size: .92em; }}
:focus-visible {{ outline: 2px solid var(--azul-texto); outline-offset: 3px; border-radius: 6px; }}
.pular {{ position: absolute; left: -999px; top: .5rem; background: var(--azul); color: #fff; padding: .5rem 1rem; border-radius: 8px; z-index: 10; }}
.pular:focus {{ left: 1rem; }}
.faixa {{ width: 100%; max-width: var(--largura); margin-inline: auto; padding-inline: clamp(1rem, 4vw, 2rem); }}
.olho {{ margin: 0 0 .5rem; font-size: .74rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: var(--azul-texto); }}
.subtitulo {{ font-size: 1.12rem; color: var(--apagado); }}
.apagado {{ color: var(--apagado); }}
/* topo */
.topo {{ position: sticky; top: 0; z-index: 5; background: color-mix(in srgb, var(--fundo) 88%, transparent);
  backdrop-filter: blur(10px); border-bottom: 1px solid var(--linha); }}
.topo .faixa {{ display: flex; align-items: center; gap: 1rem 1.5rem; min-height: 4rem; }}
.topo nav {{ display: flex; gap: 1.25rem; margin-left: auto; flex-wrap: wrap; }}
.topo nav a {{ color: var(--apagado); text-decoration: none; font-weight: 600; font-size: .95rem; }}
.topo nav a:hover, .topo nav a[aria-current] {{ color: var(--texto); }}
.marca {{ display: inline-flex; align-items: center; gap: .55rem; color: var(--texto); text-decoration: none;
  font-weight: 800; font-size: 1.15rem; letter-spacing: -0.02em; }}
.marca svg {{ width: 28px; height: 28px; color: var(--simbolo-topo); }}
.marca b {{ color: var(--lab); font-weight: 800; }}
/* botão do tema: só aparece com JavaScript (sem ele, o botão não faria nada) */
.tema {{ display: none; align-items: center; justify-content: center; width: 2.4rem; height: 2.4rem; padding: 0;
  border-radius: 10px; border: 1px solid var(--linha-forte); background: transparent; color: var(--texto); cursor: pointer; }}
.com-js .tema {{ display: inline-flex; }}
.tema:hover {{ border-color: var(--azul); }}
.tema svg {{ width: 1.15rem; height: 1.15rem; }}
.tema .sol, [data-tema="escuro"] .tema .lua {{ display: none; }}
[data-tema="escuro"] .tema .sol {{ display: block; }}
/* botões */
.botao {{ display: inline-flex; align-items: center; justify-content: center; gap: .4rem; border-radius: 10px;
  padding: .75rem 1.2rem; font: 700 1rem "Manrope", sans-serif; text-decoration: none; cursor: pointer;
  border: 1px solid transparent; transition: transform 120ms ease, background 150ms ease, border-color 150ms ease; }}
.botao:active {{ transform: scale(.98); }}
.botao.primario {{ background: var(--azul); color: #fff; }}
.botao.primario:hover {{ background: #3d71ff; }}
.botao.secundario {{ background: var(--superficie); color: var(--texto); border-color: var(--linha-forte); }}
.botao.secundario:hover {{ border-color: var(--azul); }}
.botao.pequeno {{ padding: .5rem .9rem; font-size: .92rem; }}
.seta {{ font-weight: 700; text-decoration: none; }}
.seta::after {{ content: " →"; }}
/* herói */
.heroi {{ display: grid; grid-template-columns: 1.15fr .85fr; gap: clamp(2rem, 5vw, 4rem); align-items: center;
  padding-block: clamp(3rem, 8vw, 6rem); }}
.heroi-texto {{ min-width: 0; }}
.heroi-visual img {{ border-radius: 10px; border: 1px solid var(--linha-forte);
  box-shadow: 0 30px 80px var(--sombra); transform: rotate(1.5deg); }}
.busca {{ position: relative; margin: 1.75rem 0 .75rem; }}
.busca label {{ display: block; font-weight: 700; font-size: .9rem; margin-bottom: .4rem; color: var(--apagado); }}
.busca .campo {{ display: flex; gap: .5rem; }}
.busca input {{ flex: 1; min-width: 0; padding: .8rem 1rem .8rem 2.6rem; border-radius: 10px; font: 500 1rem "Manrope", sans-serif;
  background: var(--superficie) url("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23a9b5c7'%3E%3Cpath d='M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z'/%3E%3C/svg%3E") no-repeat .8rem center / 1.2rem;
  color: var(--texto); border: 1px solid var(--linha-forte); }}
.busca input:focus {{ border-color: var(--azul); outline: none; box-shadow: 0 0 0 3px color-mix(in srgb, var(--azul) 35%, transparent); }}
#sugestoes {{ position: absolute; left: 0; right: 0; top: 100%; margin: .35rem 0 0; padding: .35rem; list-style: none; z-index: 4;
  background: var(--destaque); border: 1px solid var(--linha-forte); border-radius: 10px; box-shadow: 0 16px 40px var(--sombra); }}
#sugestoes li {{ max-width: none; padding: .55rem .7rem; border-radius: 8px; cursor: pointer; display: flex; gap: .6rem; align-items: baseline; }}
#sugestoes li[aria-selected="true"], #sugestoes li:hover {{ background: var(--superficie); }}
#sugestoes .codigo {{ font-family: "JetBrains Mono", monospace; font-weight: 700; color: var(--azul-texto); min-width: 6.5rem; }}
#sugestoes .nome {{ color: var(--texto); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; min-width: 0; }}
#sugestoes .tipo {{ color: var(--sutil); font-size: .85rem; white-space: nowrap; }}
.exemplos {{ display: flex; flex-wrap: wrap; gap: .45rem; align-items: center; color: var(--apagado); font-size: .92rem; }}
.exemplos a {{ padding: .2rem .55rem; border-radius: 999px; background: var(--superficie); border: 1px solid var(--linha);
  color: var(--texto); text-decoration: none; }}
.exemplos a:hover {{ border-color: var(--azul); }}
.acoes {{ display: flex; flex-wrap: wrap; gap: .75rem; margin-top: 1.5rem; }}
.selo-beta {{ margin-top: 1.25rem; color: var(--apagado); font-size: .92rem; }}
.selo-beta span {{ display: inline-block; margin-right: .4rem; padding: .1rem .5rem; border-radius: 999px; font-weight: 700;
  font-size: .78rem; color: var(--atencao); border: 1px solid color-mix(in srgb, var(--atencao) 45%, transparent); }}
/* seções */
.secao {{ padding-block: clamp(2.5rem, 6vw, 4.5rem); border-top: 1px solid var(--linha); }}
.estreita {{ max-width: 52rem; border-top: 0; }}
/* faixas de largura total; a seção logo depois de uma faixa não precisa de linha em cima */
.escura > .secao, .escura + .secao {{ border-top: 0; }}
.grade {{ display: grid; gap: 1rem; margin-top: 1.5rem; }}
.grade.tres {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
.grade.quatro {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }}
.cartao, .pilar {{ background: var(--superficie); border: 1px solid var(--linha); border-radius: var(--raio); padding: 1.4rem;
  transition: border-color 180ms ease, transform 180ms ease; }}
.cartao:hover {{ border-color: var(--azul); transform: translateY(-2px); }}
.cartao p, .pilar p {{ color: var(--apagado); margin: 0 0 1rem; }}
.pilar p {{ margin: 0; font-size: .95rem; }}
.passos {{ list-style: none; padding: 0; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; counter-reset: passo; }}
.passos li {{ padding: 1.4rem; border-left: 2px solid var(--azul); background: var(--superficie); border-radius: 0 var(--raio) var(--raio) 0; }}
.passos p {{ color: var(--apagado); margin: 0; }}
.numero {{ display: inline-block; font-family: "JetBrains Mono", monospace; color: var(--azul-texto); font-weight: 700; margin-bottom: .4rem; }}
/* vitrine do Report Studio */
.vitrine .controles {{ display: inline-flex; flex-wrap: wrap; gap: .25rem; padding: .25rem; margin: 1rem 0 1.25rem;
  background: var(--superficie); border: 1px solid var(--linha); border-radius: 12px; }}
.vitrine .controles button {{ font: 600 .92rem "Manrope", sans-serif; color: var(--apagado); background: transparent;
  border: 0; border-radius: 9px; padding: .5rem .9rem; cursor: pointer; }}
.vitrine .controles button[aria-pressed="true"] {{ background: var(--azul); color: #fff; }}
.vitrine .folhas {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1.25rem; max-width: 56rem; }}
.vitrine img {{ border-radius: 8px; border: 1px solid var(--linha-forte); box-shadow: 0 18px 50px var(--sombra);
  transition: opacity 200ms ease; }}
.vitrine img.trocando {{ opacity: .35; }}
.legenda {{ color: var(--sutil); font-size: .88rem; margin-top: 1rem; }}
/* tabelas */
.tabela {{ overflow-x: auto; margin: 1.5rem 0; border: 1px solid var(--linha); border-radius: var(--raio); }}
table {{ border-collapse: collapse; width: 100%; font-size: .95rem; font-variant-numeric: tabular-nums; }}
th, td {{ text-align: left; padding: .75rem 1rem; border-bottom: 1px solid var(--linha); vertical-align: top; }}
thead th {{ background: var(--superficie); color: var(--apagado); font-size: .82rem; letter-spacing: .04em; text-transform: uppercase; }}
tbody tr:last-child th, tbody tr:last-child td {{ border-bottom: 0; }}
table.planos td {{ text-align: center; }}
table.planos thead th:not(:first-child) {{ text-align: center; color: var(--texto); font-size: .95rem; text-transform: none; letter-spacing: 0; }}
/* perguntas */
.faq details {{ border-bottom: 1px solid var(--linha); padding: 1rem 0; max-width: 52rem; }}
.faq summary {{ cursor: pointer; font-weight: 700; font-size: 1.05rem; list-style: none; }}
.faq summary::-webkit-details-marker {{ display: none; }}
.faq summary::after {{ content: "+"; float: right; color: var(--azul-texto); font-weight: 800; }}
.faq details[open] summary::after {{ content: "−"; }}
.faq p {{ color: var(--apagado); margin: .6rem 0 0; }}
.final {{ text-align: center; }}
.final p {{ margin-inline: auto; }}
/* textos longos (termos, privacidade, metodologia) */
.texto-longo h2 {{ font-size: 1.4rem; margin-top: 2.2rem; }}
.texto-longo h3 {{ margin-top: 1.6rem; }}
.texto-longo li {{ margin-bottom: .45rem; }}
.texto-longo li, .texto-longo p {{ color: color-mix(in srgb, var(--texto) 88%, var(--apagado)); }}
/* rodapé */
.rodape {{ padding-block: 2.5rem; margin-top: 2rem; }}
.rodape .faixa {{ display: grid; grid-template-columns: 1fr 2fr; gap: 1.5rem 2rem; }}
.rodape nav {{ display: flex; flex-wrap: wrap; gap: .5rem 1.4rem; align-content: start; }}
.rodape nav a {{ color: var(--apagado); text-decoration: none; }}
.rodape nav a:hover {{ color: var(--texto); }}
.rodape .aviso {{ grid-column: 1 / -1; color: var(--sutil); font-size: .86rem; max-width: none; margin: 0; }}
/* celular */
@media (max-width: 860px) {{
  .heroi {{ grid-template-columns: 1fr; }}
  .heroi-visual {{ display: none; }}
  .grade.tres, .grade.quatro, .passos {{ grid-template-columns: 1fr; }}
  .topo nav {{ display: none; }}
  .rodape .faixa {{ grid-template-columns: 1fr; }}
  .vitrine .folhas {{ grid-template-columns: 1fr 1fr; gap: .6rem; }}
}}
@media (max-width: 520px) {{
  .busca .campo {{ flex-direction: column; }}
  #sugestoes .tipo {{ display: none; }}
}}
@media (prefers-reduced-motion: reduce) {{
  * {{ transition: none !important; animation: none !important; scroll-behavior: auto !important; }}
}}
"""


JS = r"""// gerado por scripts/gerar_site.py — tema, busca de ativos e vitrine do Report Studio
(() => {
  "use strict";

  // --- tema: o site abre claro; a escolha do escuro fica guardada neste navegador -----------
  const raiz = document.documentElement;
  const corDaBarra = document.querySelector('meta[name="theme-color"]');
  const aplicarTema = (escuro) => {
    if (escuro) raiz.dataset.tema = "escuro"; else delete raiz.dataset.tema;
    // a barra do navegador no celular acompanha o fundo (a cor vem do próprio CSS)
    if (corDaBarra) corDaBarra.content = getComputedStyle(raiz).getPropertyValue("--fundo").trim();
    for (const botao of document.querySelectorAll("[data-tema-botao]")) {
      botao.setAttribute("aria-label", escuro ? "Usar o tema claro" : "Usar o tema escuro");
      botao.title = escuro ? "Tema claro" : "Tema escuro";
    }
  };
  aplicarTema(raiz.dataset.tema === "escuro");
  for (const botao of document.querySelectorAll("[data-tema-botao]")) {
    botao.addEventListener("click", () => {
      const escuro = raiz.dataset.tema !== "escuro";
      aplicarTema(escuro);
      try { localStorage.setItem("tema", escuro ? "escuro" : "claro"); } catch (e) {}
    });
  }
  const semAcento = (t) => t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

  // --- busca: filtra o catálogo enquanto a pessoa digita e abre a análise no app -----------
  const form = document.querySelector("[data-busca]");
  if (form) {
    const campo = form.querySelector("input");
    const lista = form.querySelector("#sugestoes");
    const app = form.dataset.app;
    let ativos = null, achados = [], escolhido = -1;
    const carregar = async () => {
      if (ativos) return ativos;
      try {
        const resposta = await fetch("/catalogo.json");
        ativos = (await resposta.json()).map((a) => ({
          simbolo: a[0], codigo: a[1], nome: a[2], bolsa: a[3], tipo: a[4],
          busca: semAcento(a[1] + " " + a[2]),
        }));
      } catch (erro) { ativos = []; }
      return ativos;
    };
    const fechar = () => { lista.hidden = true; campo.setAttribute("aria-expanded", "false"); escolhido = -1; };
    const abrirNoApp = (simbolo) => {
      window.location.href = app + "/visao-geral?ticker=" + encodeURIComponent(simbolo);
    };
    const mostrar = () => {
      lista.replaceChildren();
      achados.forEach((a, i) => {
        const item = document.createElement("li");
        item.id = "sugestao-" + i;
        item.setAttribute("role", "option");
        item.setAttribute("aria-selected", i === escolhido ? "true" : "false");
        for (const [classe, texto] of [["codigo", a.codigo], ["nome", a.nome], ["tipo", a.bolsa + (a.tipo && a.tipo !== a.bolsa ? " · " + a.tipo : "")]]) {
          const parte = document.createElement("span");
          parte.className = classe; parte.textContent = texto; item.append(parte);
        }
        item.addEventListener("mousedown", (e) => { e.preventDefault(); abrirNoApp(a.simbolo); });
        lista.append(item);
      });
      lista.hidden = achados.length === 0;
      campo.setAttribute("aria-expanded", String(!lista.hidden));
      campo.setAttribute("aria-activedescendant", escolhido >= 0 ? "sugestao-" + escolhido : "");
    };
    campo.addEventListener("input", async () => {
      const termo = semAcento(campo.value.trim());
      if (!termo) { achados = []; fechar(); return; }
      const todos = await carregar();
      const comeca = todos.filter((a) => semAcento(a.codigo).startsWith(termo));
      const contem = todos.filter((a) => !semAcento(a.codigo).startsWith(termo) && a.busca.includes(termo));
      achados = comeca.concat(contem).slice(0, 8);
      escolhido = achados.length ? 0 : -1;
      mostrar();
    });
    campo.addEventListener("keydown", (e) => {
      if (lista.hidden) return;
      if (e.key === "ArrowDown") { escolhido = Math.min(escolhido + 1, achados.length - 1); mostrar(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { escolhido = Math.max(escolhido - 1, 0); mostrar(); e.preventDefault(); }
      else if (e.key === "Escape") { fechar(); }
    });
    campo.addEventListener("blur", () => setTimeout(fechar, 120));
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      if (escolhido >= 0 && achados[escolhido]) { abrirNoApp(achados[escolhido].simbolo); return; }
      const texto = campo.value.trim();
      if (texto) abrirNoApp(texto.toUpperCase());
    });
  }

  // --- vitrine: troca o estilo das páginas do PDF de exemplo -------------------------------
  for (const vitrine of document.querySelectorAll("[data-vitrine]")) {
    const botoes = vitrine.querySelectorAll("button[data-estilo]");
    const folhas = vitrine.querySelectorAll("img[data-pagina]");
    botoes.forEach((botao) => botao.addEventListener("click", () => {
      botoes.forEach((b) => b.setAttribute("aria-pressed", String(b === botao)));
      folhas.forEach((img) => {
        img.classList.add("trocando");
        const nova = new Image();
        nova.onload = () => { img.src = nova.src; img.classList.remove("trocando"); };
        nova.src = "/relatorio/" + botao.dataset.estilo + "-" + img.dataset.pagina + ".webp";
      });
    }));
  }
})();
"""


def _dados_de_exemplo(ticker: str) -> pd.DataFrame:
    nome = ticker.replace("^", "_")
    return pd.read_csv(
        RAIZ / "dados_de_exemplo" / f"{nome}.csv", index_col=0, parse_dates=True
    )


def gerar_relatorio_de_exemplo(destino: Path) -> list[str]:
    """O PDF de exemplo (Pesquisa completa, estilo Research) e as imagens de 2 páginas em cada
    estilo, com a data fixa do último dado de exemplo (o arquivo não muda a cada geração)."""
    pasta = destino / "relatorio"
    pasta.mkdir(parents=True, exist_ok=True)
    dados = _dados_de_exemplo(TICKER_DO_EXEMPLO)
    gerado_em = datetime.combine(dados.index[-1].date(), datetime.min.time()).replace(
        hour=18, tzinfo=relatorios.FUSO
    )
    estilos = list(ESTILOS)
    for estilo in estilos:
        pdf = relatorios.relatorio_do_ativo(
            TICKER_DO_EXEMPLO,
            dados,
            periodo="5 anos",
            gerado_em=gerado_em,
            exemplo=True,
            config=relatorios.Configuracao(estilo=estilo),
        )
        if estilo == "research":
            (pasta / f"exemplo-{TICKER_DO_EXEMPLO}.pdf").write_bytes(pdf)
        for numero, png in enumerate(previa_pdf.paginas_em_png(pdf, 2, 560), start=1):
            imagem = Image.open(BytesIO(png)).convert("RGB")
            imagem.save(pasta / f"{estilo}-{numero}.webp", "WEBP", quality=82, method=6)
    return estilos


def gerar(destino: Path = DESTINO) -> None:
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True)
    for pasta, nomes in (
        (
            "fontes",
            (
                "Manrope-VariableFont_wght.ttf",
                "JetBrainsMono-VariableFont_wght.ttf",
                "OFL-Manrope.txt",
                "OFL-JetBrainsMono.txt",
            ),
        ),
        ("marca", ("simbolo.svg", "icone.png", "compartilhamento.png")),
    ):
        (destino / pasta).mkdir()
        for nome in nomes:
            shutil.copyfile(RAIZ / "static" / pasta / nome, destino / pasta / nome)
    estilos = gerar_relatorio_de_exemplo(destino)
    tabela = catalogo.carregar().reset_index()
    (destino / "catalogo.json").write_text(
        json.dumps(
            tabela[["simbolo", "codigo", "nome", "bolsa", "tipo"]].values.tolist(),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    paginas = {
        "index.html": landing(estilos),
        "precos.html": precos(),
        "metodologia.html": metodologia(),
        "termos.html": legal(
            "/termos.html",
            "termos.md",
            "Termos de uso",
            "Os termos de uso do TickerLab, plataforma de inteligência financeira para análise de ações.",
        ),
        "privacidade.html": legal(
            "/privacidade.html",
            "privacidade.md",
            "Política de privacidade",
            "Que dados o TickerLab trata, para quê, por quanto tempo e como exportar ou apagar.",
        ),
        "404.html": nao_encontrada(),
    }
    for nome, conteudo in paginas.items():
        (destino / nome).write_text(conteudo, encoding="utf-8")
    (destino / "estilo.css").write_text(css(), encoding="utf-8")
    (destino / "site.js").write_text(JS, encoding="utf-8")
    (destino / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {URL_DO_SITE}/sitemap.xml\n",
        encoding="utf-8",
    )
    enderecos = [n for n in paginas if n != "404.html"]
    (destino / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(
            f"  <url><loc>{URL_DO_SITE}/{'' if n == 'index.html' else n}</loc></url>\n"
            for n in enderecos
        )
        + "</urlset>\n",
        encoding="utf-8",
    )


def main() -> int:
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else DESTINO
    gerar(destino)
    total = sum(f.stat().st_size for f in destino.rglob("*") if f.is_file())
    print(f"site gerado em {destino} ({total / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
