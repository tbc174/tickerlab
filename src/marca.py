"""A identidade visual do TickerLab: o único lugar das cores e do símbolo.

Segue o Manual de identidade v1 (13/10/2026), que substituiu a marca de 11/10 (a "Vela T"). Vale
para tudo da marca: o site, o app, os relatórios em PDF, a Newsletter e o que vier do projeto de
trading. O CSS (`src/estilo.py`), o tema dos gráficos (`src/graficos.py`), o site
(`scripts/gerar_site.py`) e os arquivos do símbolo em `static/marca/` vêm daqui. O tema do
Streamlit (`.streamlit/config.toml`) repete estas cores; um teste confere que batem.

Do manual: quatro cores institucionais (marinho, azul elétrico, claro e azul claro), o azul
elétrico com moderação, e o símbolo T geométrico em dois traços que não se redesenham. A fonte
continua a Manrope (a "direção original" do manual): a Segoe UI das peças das redes é do Windows e
não pode ser servida num site.

Regras do app: tema escuro em marinho, com a profundidade dada pela cor das superfícies (quanto
mais importante, mais clara); verde e vermelho só para alta e queda, sempre com seta e sinal; as
cores dos gráficos sempre nesta ordem.
"""

from pathlib import Path

# as quatro cores institucionais do manual
MARINHO = "#0a1f44"  # fundo institucional; títulos e texto em superfícies claras
AZUL = (
    "#2962ff"  # azul elétrico: ações (botões, seleção), destaques e a haste do símbolo
)
CLARO = "#f6f8fb"  # fundo claro; texto em superfícies escuras
AZUL_CLARO = "#e8f0ff"  # cartões e camadas em superfícies claras

# tema escuro (app, site no modo escuro, PDF Terminal): superfícies do fundo para cima
FUNDO = "#071733"  # um marinho mais fundo, para os cartões em marinho se destacarem
SUPERFICIE = MARINHO
DESTAQUE = "#102752"
LINHA = "rgba(232, 240, 255, 0.12)"
LINHA_FORTE = "rgba(232, 240, 255, 0.24)"
# texto no escuro (contraste WCAG AA sobre as três superfícies)
TEXTO = CLARO
TEXTO_APAGADO = "#a9b8d6"  # descrições
TEXTO_SUTIL = "#8796b5"  # só metadados curtos, nunca texto essencial
AZUL_TEXTO = "#6e95ff"  # azul legível sobre o marinho (o elétrico fica em 3:1: só em peças grandes)
# significado
ALTA = "#2ebd85"
QUEDA = (
    "#f76169"  # um pouco mais claro que antes, para passar no contraste sobre o marinho
)
ATENCAO = "#f5b83d"
# séries dos gráficos, sempre nesta ordem (vizinhas distinguíveis por daltônicos)
SERIES = ("#6e95ff", "#f5a524", "#2bc4a9", "#e874b6", "#e8d44d", "#a98bff")

# Tema claro (site no modo claro, relatórios em PDF, e-mails): marinho sobre claro, cartões em
# azul claro. Verde, vermelho e as séries ficam mais escuros para ter contraste sobre o claro.
PAPEL_FUNDO = "#ffffff"  # o PDF fica no branco do papel (gasta menos tinta)
PAPEL_SUPERFICIE = AZUL_CLARO
PAPEL_LINHA = "#d6deec"
PAPEL_TEXTO = MARINHO
PAPEL_APAGADO = "#4a5a78"
PAPEL_SUTIL = "#5f6d88"
PAPEL_AZUL_TEXTO = (
    "#1f55e8"  # o elétrico um tom abaixo: texto pequeno sobre o azul claro (AA)
)
PAPEL_ALTA = "#178a5d"
PAPEL_QUEDA = "#cf3540"
PAPEL_ATENCAO = "#9a6700"  # o âmbar escurecido, para texto sobre o claro
PAPEL_SERIES = ("#2962ff", "#c77700", "#11897a", "#b8417f", "#8a7a00", "#6b4fe0")

FONTE = "Manrope"
FONTE_MONO = "JetBrains Mono"

PASTA_ESTATICA = Path(__file__).resolve().parent.parent / "static"
ARQUIVO_DO_SIMBOLO = PASTA_ESTATICA / "marca" / "simbolo.svg"
ARQUIVO_DO_ICONE = PASTA_ESTATICA / "marca" / "icone.png"
# símbolo + "TickerLab", para o st.logo; os arquivos saem de `python -m scripts.gerar_marca`
ARQUIVO_DA_ASSINATURA = PASTA_ESTATICA / "marca" / "assinatura.png"
# imagem que aparece quando alguém compartilha o link do site (1200 × 630)
ARQUIVO_DE_COMPARTILHAMENTO = PASTA_ESTATICA / "marca" / "compartilhamento.png"
ARQUIVO_DA_FONTE = PASTA_ESTATICA / "fontes" / "Manrope-VariableFont_wght.ttf"
# versões de um peso só, para os relatórios em PDF (geradas por `python -m scripts.gerar_marca`)
FONTE_PDF_TEXTO = PASTA_ESTATICA / "fontes" / "Manrope-Regular.ttf"
FONTE_PDF_MEDIA = PASTA_ESTATICA / "fontes" / "Manrope-SemiBold.ttf"
FONTE_PDF_TITULO = PASTA_ESTATICA / "fontes" / "Manrope-ExtraBold.ttf"
FONTE_PDF_MONO = PASTA_ESTATICA / "fontes" / "JetBrainsMono-SemiBold.ttf"


def seta(valor: float) -> str:
    """A seta que acompanha a cor de alta ou de queda (nunca a cor sozinha)."""
    if valor > 0:
        return "▲"
    if valor < 0:
        return "▼"
    return "■"


# Os dois traços do símbolo, copiados do SVG original do manual (grade de 80; a área visível vai
# de 9 a 69 na horizontal e de 14 a 74 na vertical). Nunca redesenhar nem trocar pela letra T.
TRACO_DO_TOPO = "M9 14 H69 V25 C69 32 64 35 57 35 H9 Z"
TRACO_DA_HASTE = "M32 35 L51 26 V59 C51 64 48 67 43 70 L32 74 Z"
AREA_VISIVEL = (9, 14, 60, 60)  # x, y, largura, altura


def simbolo_svg(topo: str = MARINHO, haste: str = AZUL) -> str:
    """O símbolo T geométrico: topo marinho em fundo claro (`topo=CLARO` em fundo escuro); a haste
    é sempre azul elétrico. `topo="currentColor"` deixa o CSS escolher a cor pelo tema."""
    x, y, largura, altura = AREA_VISIVEL
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x} {y} {largura} {altura}" '
        'width="32" height="32" aria-hidden="true">'
        f'<path d="{TRACO_DO_TOPO}" fill="{topo}"/>'
        f'<path d="{TRACO_DA_HASTE}" fill="{haste}"/>'
        "</svg>"
    )


def icone_svg() -> str:
    """O ícone da aba do navegador: o símbolo, com o topo claro quando o navegador está escuro."""
    x, y, largura, altura = AREA_VISIVEL
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x} {y} {largura} {altura}" '
        'width="32" height="32">'
        f"<style>@media (prefers-color-scheme: dark) {{ .topo {{ fill: {CLARO}; }} }}</style>"
        f'<path class="topo" d="{TRACO_DO_TOPO}" fill="{MARINHO}"/>'
        f'<path d="{TRACO_DA_HASTE}" fill="{AZUL}"/>'
        "</svg>"
    )
