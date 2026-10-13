"""Markdown dos termos e da política para HTML (só o que esses textos usam).

Usado pelo exportador do site (`scripts/exportar_conteudo.py`): títulos, parágrafos, listas, tabelas,
negrito, itálico, código e links.
"""

import html
import re


def esc(texto: str) -> str:
    return html.escape(texto, quote=True)


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
