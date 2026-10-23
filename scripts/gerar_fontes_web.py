"""Gera as fontes do site e do app em WOFF2 (`static/fontes/*.woff2`) a partir dos TTF oficiais.

    pip install brotli   # o WOFF2 comprime com Brotli; fica fora do requirements (só este script usa)
    python -m scripts.gerar_fontes_web

O site carregava os TTF inteiros (~350 KB, uns 70% da primeira visita). Em WOFF2, só com o latim e o
latim estendido (o português e nomes de fora, como Škoda e Ørsted), as duas ficam com ~86 KB; um
caractere fora da faixa cai na fonte do sistema. Os TTF continuam em `static/fontes` para o PDF e o
Streamlit. Rode de novo só quando trocar a versão de uma fonte, e faça o commit dos .woff2.
"""

from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

PASTA = Path(__file__).resolve().parent.parent / "static" / "fontes"
FONTES = ("Manrope-VariableFont_wght", "JetBrainsMono-VariableFont_wght")
FAIXAS = (
    "U+0000-024F",  # latim básico, Latin-1 e latim estendido A e B
    "U+0259,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0300-036F",  # schwa, modificadores e acentos soltos
    "U+1E00-1EFF",  # latim estendido adicional (vietnamita e afins)
    "U+2000-206F,U+20A0-20CF,U+2100-2122",  # pontuação, moedas (€) e símbolos de letra (™)
    "U+2190-21FF,U+2212,U+2215,U+2713,U+25B2,U+25BC",  # setas, menos, ✓ e ▲▼ que o site usa
    "U+FEFF,U+FFFD",
)


def gerar(nome: str) -> Path:
    """Grava `<nome>.woff2` ao lado do TTF, só com as FAIXAS e com todos os recursos tipográficos."""
    opcoes = subset.Options()
    opcoes.flavor = "woff2"
    opcoes.layout_features = ["*"]  # algarismos tabulares, ligaduras etc.
    fonte = TTFont(PASTA / f"{nome}.ttf")
    recorte = subset.Subsetter(opcoes)
    recorte.populate(unicodes=subset.parse_unicodes(",".join(FAIXAS)))
    recorte.subset(fonte)
    destino = PASTA / f"{nome}.woff2"
    fonte.flavor = "woff2"
    fonte.save(destino)
    return destino


def main() -> None:
    for nome in FONTES:
        destino = gerar(nome)
        print(f"{destino.name}: {destino.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
