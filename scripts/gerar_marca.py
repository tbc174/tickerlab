"""Gera os arquivos do símbolo do TickerLab em static/marca/ a partir de src/marca.py.

    python -m scripts.gerar_marca

Rodar só quando a marca mudar. Fica fora de src/ porque usa a biblioteca de imagens (Pillow),
que o site no ar não precisa: ele só serve os arquivos já gerados.
"""

from PIL import Image, ImageDraw, ImageFont

from src.marca import (
    ARQUIVO_DA_ASSINATURA,
    ARQUIVO_DA_FONTE,
    ARQUIVO_DO_ICONE,
    ARQUIVO_DO_SIMBOLO,
    AZUL,
    AZUL_TEXTO,
    TEXTO,
    simbolo_svg,
)


def desenhar_icone_png(tamanho: int = 256) -> Image.Image:
    """O símbolo como imagem (Pillow), para o ícone da aba do navegador."""
    escala = tamanho / 32
    imagem = Image.new("RGBA", (tamanho, tamanho), (0, 0, 0, 0))
    lapis = ImageDraw.Draw(imagem)

    def retangulo(
        x: float, y: float, largura: float, altura: float, raio: float, cor: str
    ) -> None:
        lapis.rounded_rectangle(
            [x * escala, y * escala, (x + largura) * escala, (y + altura) * escala],
            radius=raio * escala,
            fill=cor,
        )

    retangulo(0, 0, 32, 32, 8, AZUL)
    retangulo(7, 7, 18, 3.6, 1.8, "#ffffff")
    retangulo(14.6, 10, 2.8, 16, 1.4, "#ffffff")
    retangulo(11.6, 13.5, 8.8, 9, 2, "#ffffff")
    return imagem


def desenhar_assinatura_png(altura: int = 96) -> Image.Image:
    """Símbolo + "Ticker" + "Lab" (azul claro) numa imagem só, para o `st.logo` do topo.

    O texto é desenhado com a própria Manrope ExtraBold, então a imagem não depende de fonte
    nenhuma no navegador. Fundo transparente.
    """
    simbolo = desenhar_icone_png(altura)
    fonte = ImageFont.truetype(str(ARQUIVO_DA_FONTE), int(altura * 0.62))
    fonte.set_variation_by_name("ExtraBold")
    folga = int(altura * 0.28)
    rascunho = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    largura_ticker = rascunho.textlength("Ticker", font=fonte)
    largura_lab = rascunho.textlength("Lab", font=fonte)
    largura = altura + folga + int(largura_ticker + largura_lab) + 4
    imagem = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    imagem.paste(simbolo, (0, 0), simbolo)
    lapis = ImageDraw.Draw(imagem)
    meio = altura / 2
    lapis.text((altura + folga, meio), "Ticker", font=fonte, fill=TEXTO, anchor="lm")
    lapis.text(
        (altura + folga + largura_ticker, meio),
        "Lab",
        font=fonte,
        fill=AZUL_TEXTO,
        anchor="lm",
    )
    return imagem


def gerar_arquivos() -> None:
    """Grava o símbolo (SVG), o ícone da aba e a assinatura do topo (depois de mudar a marca)."""
    ARQUIVO_DO_SIMBOLO.parent.mkdir(parents=True, exist_ok=True)
    ARQUIVO_DO_SIMBOLO.write_text(simbolo_svg() + "\n", encoding="utf-8")
    desenhar_icone_png(256).resize((128, 128)).save(ARQUIVO_DO_ICONE)
    desenhar_assinatura_png(96).save(ARQUIVO_DA_ASSINATURA)


FONTES_ESTATICAS = {
    # arquivo de saída: (fonte variável de origem, peso)
    "Manrope-Regular.ttf": ("Manrope-VariableFont_wght.ttf", 400),
    "Manrope-SemiBold.ttf": ("Manrope-VariableFont_wght.ttf", 600),
    "Manrope-ExtraBold.ttf": ("Manrope-VariableFont_wght.ttf", 800),
    "JetBrainsMono-SemiBold.ttf": ("JetBrainsMono-VariableFont_wght.ttf", 600),
}


def gerar_fontes_estaticas() -> None:
    """Fontes de um peso só, para os relatórios em PDF (o matplotlib não escolhe o peso de uma
    fonte variável e ficava no padrão da Manrope, 200, fino demais)."""
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont

    pasta = ARQUIVO_DA_FONTE.parent
    for saida, (origem, peso) in FONTES_ESTATICAS.items():
        try:  # atualiza o nome interno ("Manrope ExtraBold"); nem toda fonte tem os dados
            fonte = instantiateVariableFont(
                TTFont(pasta / origem), {"wght": peso}, updateFontNames=True
            )
        except (
            ValueError
        ):  # a JetBrains Mono não tem: os arquivos são carregados pelo caminho
            fonte = instantiateVariableFont(TTFont(pasta / origem), {"wght": peso})
        fonte.save(pasta / saida)


if __name__ == "__main__":
    gerar_arquivos()
    gerar_fontes_estaticas()
