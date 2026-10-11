"""A identidade visual do TickerLab: o único lugar das cores e do símbolo.

Aprovada pelo Tiago em 11/10/2026 (proposta "Marca TickerLab"). Vale para tudo da marca: o site,
a página TickerLab Trade e o que vier do projeto de trading. O CSS (`src/estilo.py`), o tema dos
gráficos (`src/graficos.py`) e os arquivos do símbolo em `static/marca/` vêm daqui. O tema do
Streamlit (`.streamlit/config.toml`) repete estas cores; um teste confere que batem.

Regras: tema escuro sem preto puro, com a profundidade dada pela cor das superfícies (quanto mais
importante, mais clara); verde e vermelho só para alta e queda, sempre com seta e sinal; as cores
dos gráficos sempre nesta ordem.
"""

from pathlib import Path

# superfícies (do fundo para cima)
FUNDO = "#0a0d13"
SUPERFICIE = "#10141c"
DESTAQUE = "#161b26"
LINHA = "rgba(148, 163, 190, 0.14)"
LINHA_FORTE = "rgba(148, 163, 190, 0.26)"
# texto
TEXTO = "#e8ecf4"
TEXTO_APAGADO = "#93a0b8"
# marca
AZUL = "#2962ff"  # ações (botões, seleção) e o símbolo
AZUL_TEXTO = "#6e95ff"  # azul legível sobre o fundo escuro (links, destaques)
# significado
ALTA = "#2ebd85"
QUEDA = "#f0525b"
ATENCAO = "#f5b83d"
# séries dos gráficos, sempre nesta ordem (vizinhas distinguíveis por daltônicos)
SERIES = ("#6e95ff", "#f5a524", "#2bc4a9", "#e874b6", "#e8d44d", "#a98bff")

# Versão "papel" (relatórios em PDF): a mesma identidade em fundo claro, que gasta menos tinta e
# lê melhor impressa. Verde, vermelho e as séries ficam um pouco mais escuros para ter contraste
# sobre o branco; o azul da marca é o mesmo.
PAPEL_FUNDO = "#ffffff"
PAPEL_SUPERFICIE = "#f3f5fa"
PAPEL_LINHA = "#dde3ee"
PAPEL_TEXTO = "#0f1420"
PAPEL_APAGADO = "#5b667a"
PAPEL_ALTA = "#178a5d"
PAPEL_QUEDA = "#cf3540"
PAPEL_SERIES = ("#2962ff", "#c77700", "#11897a", "#b8417f", "#8a7a00", "#6b4fe0")

FONTE = "Manrope"
FONTE_MONO = "JetBrains Mono"

PASTA_ESTATICA = Path(__file__).resolve().parent.parent / "static"
ARQUIVO_DO_SIMBOLO = PASTA_ESTATICA / "marca" / "simbolo.svg"
ARQUIVO_DO_ICONE = PASTA_ESTATICA / "marca" / "icone.png"
# símbolo + "TickerLab", para o st.logo; os arquivos saem de `python -m scripts.gerar_marca`
ARQUIVO_DA_ASSINATURA = PASTA_ESTATICA / "marca" / "assinatura.png"
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


def simbolo_svg(fundo: str = AZUL, desenho: str = "#ffffff") -> str:
    """O símbolo "Vela T": uma vela de gráfico cujo topo forma um T, numa grade de 32."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32">'
        f'<rect width="32" height="32" rx="8" fill="{fundo}"/>'
        f'<rect x="7" y="7" width="18" height="3.6" rx="1.8" fill="{desenho}"/>'
        f'<rect x="14.6" y="10" width="2.8" height="16" rx="1.4" fill="{desenho}"/>'
        f'<rect x="11.6" y="13.5" width="8.8" height="9" rx="2" fill="{desenho}"/>'
        "</svg>"
    )
