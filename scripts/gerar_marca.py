"""Gera os arquivos do símbolo do TickerLab em static/marca/ a partir de src/marca.py.

    python -m scripts.gerar_marca

Rodar só quando a marca mudar. Fica fora de src/ porque usa a biblioteca de imagens (Pillow),
que o site no ar não precisa: ele só serve os arquivos já gerados.
"""

import re

from PIL import Image, ImageDraw, ImageFont

from src.marca import (
    AREA_VISIVEL,
    ARQUIVO_DA_ASSINATURA,
    ARQUIVO_DA_ASSINATURA_CLARA,
    ARQUIVO_DA_FONTE,
    ARQUIVO_DE_COMPARTILHAMENTO,
    ARQUIVO_DO_ICONE,
    ARQUIVO_DO_ICONE_DO_IPHONE,
    ARQUIVO_DO_ICONE_MASCARAVEL,
    ARQUIVO_DO_SIMBOLO,
    AZUL,
    AZUL_TEXTO,
    CLARO,
    ICONES_DO_APP,
    MARINHO,
    TEXTO_APAGADO,
    TRACO_DA_HASTE,
    TRACO_DO_TOPO,
    icone_svg,
)

SUPERAMOSTRA = (
    4  # desenha 4× maior e reduz: bordas suaves (o Pillow não suaviza polígonos)
)
PONTOS_POR_CURVA = 24
ASSINATURA_INSTITUCIONAL = "Menos ruído. Mais inteligência para investir."


def pontos_do_traco(caminho: str) -> list[tuple[float, float]]:
    """O contorno de um traço do SVG (só os comandos absolutos M, H, V, L, C e Z, os únicos que o
    símbolo usa), com as curvas trocadas por segmentos curtos."""
    pontos: list[tuple[float, float]] = []
    for comando, numeros in re.findall(r"([MHVLCZ])([^MHVLCZ]*)", caminho):
        valores = [float(n) for n in numeros.split()]
        x, y = pontos[-1] if pontos else (0.0, 0.0)
        if comando in "ML":
            pontos.append((valores[0], valores[1]))
        elif comando == "H":
            pontos.append((valores[0], y))
        elif comando == "V":
            pontos.append((x, valores[0]))
        elif comando == "C":
            x1, y1, x2, y2, x3, y3 = valores
            for passo in range(1, PONTOS_POR_CURVA + 1):
                t = passo / PONTOS_POR_CURVA
                u = 1 - t
                pontos.append(
                    (
                        u**3 * x + 3 * u**2 * t * x1 + 3 * u * t**2 * x2 + t**3 * x3,
                        u**3 * y + 3 * u**2 * t * y1 + 3 * u * t**2 * y2 + t**3 * y3,
                    )
                )
    return pontos


def desenhar_simbolo_png(tamanho: int, topo: str = CLARO) -> Image.Image:
    """O símbolo (só a área visível, quadrada) em fundo transparente. O padrão é a versão para
    fundo escuro (topo claro), a do topo do app e da imagem de compartilhamento."""
    grande = tamanho * SUPERAMOSTRA
    x0, y0, lado, _ = AREA_VISIVEL
    escala = grande / lado
    imagem = Image.new("RGBA", (grande, grande), (0, 0, 0, 0))
    lapis = ImageDraw.Draw(imagem)
    for traco, cor in ((TRACO_DO_TOPO, topo), (TRACO_DA_HASTE, AZUL)):
        lapis.polygon(
            [((x - x0) * escala, (y - y0) * escala) for x, y in pontos_do_traco(traco)],
            fill=cor,
        )
    return imagem.resize((tamanho, tamanho), Image.Resampling.LANCZOS)


def desenhar_icone_png(tamanho: int = 128) -> Image.Image:
    """O ícone do app (aba do navegador e atalhos): o símbolo de fundo escuro num quadrado
    marinho de cantos arredondados, para aparecer em qualquer cor de aba."""
    grande = tamanho * SUPERAMOSTRA
    imagem = Image.new("RGBA", (grande, grande), (0, 0, 0, 0))
    ImageDraw.Draw(imagem).rounded_rectangle(
        [0, 0, grande - 1, grande - 1], radius=grande * 0.22, fill=MARINHO
    )
    imagem = imagem.resize((tamanho, tamanho), Image.Resampling.LANCZOS)
    lado = round(tamanho * 0.64)
    margem = (tamanho - lado) // 2
    simbolo = desenhar_simbolo_png(lado)
    imagem.paste(simbolo, (margem, margem), simbolo)
    return imagem


def desenhar_icone_mascaravel_png(tamanho: int = 512) -> Image.Image:
    """O ícone "maskable" do app instalado: marinho até a borda (o celular recorta em círculo ou
    gota) e o símbolo pequeno o bastante para caber no círculo de 80% do meio, a zona segura."""
    imagem = Image.new("RGBA", (tamanho, tamanho), MARINHO)
    lado = round(
        tamanho * 0.5
    )  # a diagonal do símbolo (0,71 do lado) fica dentro dos 80%
    margem = (tamanho - lado) // 2
    simbolo = desenhar_simbolo_png(lado)
    imagem.paste(simbolo, (margem, margem), simbolo)
    return imagem


def _fonte(tamanho: int, peso: str) -> ImageFont.FreeTypeFont:
    fonte = ImageFont.truetype(str(ARQUIVO_DA_FONTE), tamanho)
    fonte.set_variation_by_name(peso)
    return fonte


def desenhar_nome(
    lapis: ImageDraw.ImageDraw,
    x: float,
    meio: float,
    fonte: ImageFont.FreeTypeFont,
    cor_do_lab: str = AZUL_TEXTO,
    cor_do_ticker: str = CLARO,
) -> None:
    """ "Ticker" claro + "Lab" em azul, centrados na altura `meio` (versão para fundo escuro).

    Em tamanho de destaque o "Lab" vai no azul elétrico, como nas peças aprovadas; pequeno, no
    azul mais claro, que se lê sobre o marinho."""
    lapis.text((x, meio), "Ticker", font=fonte, fill=cor_do_ticker, anchor="lm")
    largura_ticker = lapis.textlength("Ticker", font=fonte)
    lapis.text(
        (x + largura_ticker, meio), "Lab", font=fonte, fill=cor_do_lab, anchor="lm"
    )


def desenhar_assinatura_png(altura: int = 96, clara: bool = False) -> Image.Image:
    """Símbolo + "Ticker" + "Lab" numa imagem só, para o `st.logo` do topo do app. `clara` é a
    versão do tema claro (topo do símbolo e "Ticker" em marinho, "Lab" no azul elétrico).

    O texto é desenhado com a própria Manrope ExtraBold, então a imagem não depende de fonte
    nenhuma no navegador. Fundo transparente.
    """
    simbolo = desenhar_simbolo_png(altura, topo=MARINHO if clara else CLARO)
    fonte = _fonte(int(altura * 0.62), "ExtraBold")
    folga = int(altura * 0.28)
    rascunho = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    largura_nome = rascunho.textlength("TickerLab", font=fonte)
    imagem = Image.new(
        "RGBA", (altura + folga + int(largura_nome) + 4, altura), (0, 0, 0, 0)
    )
    imagem.paste(simbolo, (0, 0), simbolo)
    cores = {"cor_do_lab": AZUL, "cor_do_ticker": MARINHO} if clara else {}
    desenhar_nome(ImageDraw.Draw(imagem), altura + folga, altura / 2, fonte, **cores)
    return imagem


def desenhar_compartilhamento_png(
    largura: int = 1200, altura: int = 630
) -> Image.Image:
    """A imagem dos links compartilhados (WhatsApp, LinkedIn): fundo marinho, a assinatura e a
    frase institucional do manual, alinhadas à esquerda com margem ampla."""
    imagem = Image.new("RGB", (largura, altura), MARINHO)
    lapis = ImageDraw.Draw(imagem)
    margem = 96
    lado = 120
    simbolo = desenhar_simbolo_png(lado)
    topo = 150
    imagem.paste(simbolo, (margem, topo), simbolo)
    desenhar_nome(
        lapis, margem + lado + 34, topo + lado / 2, _fonte(96, "ExtraBold"), AZUL
    )
    frase = _fonte(46, "Bold")
    linha_1, linha_2 = ASSINATURA_INSTITUCIONAL.split(". ", 1)
    lapis.text((margem, 360), linha_1 + ".", font=frase, fill=CLARO)
    lapis.text((margem, 418), linha_2, font=frase, fill=CLARO)
    lapis.rectangle([margem, 520, margem + 64, 524], fill=AZUL)
    lapis.text(
        (margem, 548),
        "tickerlab.com.br",
        font=_fonte(26, "SemiBold"),
        fill=TEXTO_APAGADO,
    )
    return imagem


def gerar_arquivos() -> None:
    """Grava o ícone da aba (SVG e PNG), a assinatura do topo e a imagem de compartilhamento."""
    ARQUIVO_DO_SIMBOLO.parent.mkdir(parents=True, exist_ok=True)
    ARQUIVO_DO_SIMBOLO.write_text(icone_svg() + "\n", encoding="utf-8")
    desenhar_icone_png(128).save(ARQUIVO_DO_ICONE)
    for arquivo, lado in ICONES_DO_APP.items():
        sem_cantos = arquivo in (
            ARQUIVO_DO_ICONE_MASCARAVEL,
            ARQUIVO_DO_ICONE_DO_IPHONE,
        )
        desenho = (
            desenhar_icone_mascaravel_png(lado)
            if sem_cantos
            else desenhar_icone_png(lado)
        )
        desenho.save(arquivo, optimize=True)
    desenhar_assinatura_png(96).save(ARQUIVO_DA_ASSINATURA)
    desenhar_assinatura_png(96, clara=True).save(ARQUIVO_DA_ASSINATURA_CLARA)
    desenhar_compartilhamento_png().save(ARQUIVO_DE_COMPARTILHAMENTO, optimize=True)


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
