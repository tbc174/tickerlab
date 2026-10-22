"""O deck em PPT (.pptx, 16:9) da ficha e do relatório do setor, com as cores da marca. Lê a mesma
`Apresentacao` do PDF (`src/apresentacao_pdf.py`), então os dois formatos têm os mesmos slides e os
mesmos números. A biblioteca é a python-pptx (MIT). A fonte é a Manrope da marca; no computador sem
ela instalada o PowerPoint troca por outra, e o texto continua legível (as caixas têm folga)."""

from datetime import datetime
from io import BytesIO

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.slide import Slide as SlidePPT
from pptx.text.text import TextFrame, _Paragraph
from pptx.util import Emu, Inches, Length, Pt

from src import marca
from src.apresentacao import CAPA, Apresentacao, Slide
from src.estilos_pdf import PADRAO, Estilo
from src.relatorio_pdf import NUMERO_ESCRITO

LARGURA = Inches(13.333)
ALTURA = Inches(7.5)
MARGEM = Inches(0.6)
TOPO = Inches(1.5)
FONTE = "Manrope"
TAMANHO_DO_CORPO = 20
TAMANHO_DA_TABELA = 14
CARACTERES_POR_LINHA = 95  # estimativa para diminuir o corpo de texto longo


def _cor(hexa: str) -> RGBColor:
    return RGBColor.from_string(hexa.lstrip("#").upper())


def _caixa(
    slide: SlidePPT, x: Length, y: Length, largura: Length, altura: Length
) -> TextFrame:
    caixa = slide.shapes.add_textbox(x, y, largura, altura)
    caixa.text_frame.word_wrap = True
    return caixa.text_frame


def _paragrafo(
    quadro: TextFrame,
    texto: str,
    tamanho: int,
    cor: str,
    negrito: bool = False,
    primeiro: bool = False,
) -> _Paragraph:
    p = quadro.paragraphs[0] if primeiro else quadro.add_paragraph()
    corrida = p.add_run()
    corrida.text = texto
    corrida.font.name = FONTE
    corrida.font.size = Pt(tamanho)
    corrida.font.bold = negrito
    corrida.font.color.rgb = _cor(cor)
    return p


def _fundo(slide: SlidePPT, estilo: Estilo) -> None:
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _cor(estilo.fundo)
    if estilo.faixa:
        faixa = slide.shapes.add_shape(1, 0, 0, LARGURA, Inches(0.25))
        faixa.fill.solid()
        faixa.fill.fore_color.rgb = _cor(estilo.faixa)
        faixa.line.fill.background()


def _rodape(
    slide: SlidePPT, deck: Apresentacao, estilo: Estilo, numero: int, total: int
) -> None:
    quadro = _caixa(
        slide,
        MARGEM,
        ALTURA - Inches(0.6),
        LARGURA - 2 * MARGEM - Inches(1.2),
        Inches(0.5),
    )
    _paragrafo(quadro, deck.aviso, 10, estilo.apagado, primeiro=True)
    quadro = _caixa(
        slide,
        LARGURA - MARGEM - Inches(1.2),
        ALTURA - Inches(0.6),
        Inches(1.2),
        Inches(0.4),
    )
    p = _paragrafo(quadro, f"{numero} / {total}", 10, estilo.apagado, primeiro=True)
    p.alignment = PP_ALIGN.RIGHT


def _marca(slide: SlidePPT, estilo: Estilo, x, y, tamanho) -> None:  # noqa: ANN001
    quadro = _caixa(slide, x + tamanho + Inches(0.1), y, Inches(4), tamanho)
    p = quadro.paragraphs[0]
    for texto, cor in (
        ("Ticker", estilo.texto),
        ("Lab", marca.AZUL_TEXTO if estilo.escuro else marca.AZUL),
    ):
        corrida = p.add_run()
        corrida.text = texto
        corrida.font.name = FONTE
        corrida.font.bold = True
        corrida.font.size = Pt(28)
        corrida.font.color.rgb = _cor(cor)


def _titulo(slide: SlidePPT, texto: str, estilo: Estilo) -> None:
    quadro = _caixa(slide, MARGEM, Inches(0.4), LARGURA - 2 * MARGEM, Inches(0.9))
    _paragrafo(
        quadro,
        texto,
        30 if len(texto) < 60 else 22,
        estilo.texto,
        negrito=True,
        primeiro=True,
    )
    traco = slide.shapes.add_shape(1, MARGEM, Inches(1.3), Inches(0.7), Inches(0.05))
    traco.fill.solid()
    traco.fill.fore_color.rgb = _cor(marca.AZUL)
    traco.line.fill.background()


def _topicos(slide: SlidePPT, topicos: tuple[str, ...], estilo: Estilo) -> None:
    caracteres = sum(len(t) for t in topicos)
    tamanho = TAMANHO_DO_CORPO if caracteres < 550 else 16 if caracteres < 800 else 13
    quadro = _caixa(slide, MARGEM, TOPO, LARGURA - 2 * MARGEM, Inches(4.5))
    for i, topico in enumerate(topicos):
        p = _paragrafo(quadro, f"• {topico}", tamanho, estilo.texto, primeiro=i == 0)
        p.space_after = Pt(8)


def _tabela(slide: SlidePPT, conteudo: Slide, estilo: Estilo) -> None:
    linhas, colunas = len(conteudo.linhas) + 1, len(conteudo.cabecalho)
    largura = LARGURA - 2 * MARGEM
    forma = slide.shapes.add_table(
        linhas, colunas, MARGEM, TOPO, largura, Inches(0.5) * linhas
    )
    tabela = forma.table
    numeros = [
        all(NUMERO_ESCRITO.match(linha[i]) for linha in conteudo.linhas)
        for i in range(colunas)
    ]
    tamanho = TAMANHO_DA_TABELA if colunas <= 4 else 12
    textos = [conteudo.cabecalho, *conteudo.linhas]
    for r, linha in enumerate(textos):
        for c, texto in enumerate(linha):
            celula = tabela.cell(r, c)
            celula.fill.solid()
            celula.fill.fore_color.rgb = _cor(
                estilo.superficie if r == 0 else estilo.fundo
            )
            quadro = celula.text_frame
            quadro.word_wrap = True
            p = _paragrafo(
                quadro,
                texto,
                tamanho,
                estilo.apagado if r == 0 else estilo.texto,
                negrito=r > 0 and c == 1,
                primeiro=True,
            )
            if numeros[c]:
                p.alignment = PP_ALIGN.RIGHT
    tabela.columns[0].width = Emu(int(largura * (0.34 if colunas > 2 else 0.5)))
    resto = largura - tabela.columns[0].width
    for c in range(1, colunas):
        tabela.columns[c].width = Emu(int(resto / (colunas - 1)))


def _notas(slide: SlidePPT, notas: tuple[str, ...], estilo: Estilo) -> None:
    if not notas:
        return
    quadro = _caixa(
        slide, MARGEM, ALTURA - Inches(1.5), LARGURA - 2 * MARGEM, Inches(0.8)
    )
    for i, nota in enumerate(notas):
        _paragrafo(quadro, nota, 11, estilo.apagado, primeiro=i == 0)


def _capa(slide: SlidePPT, conteudo: Slide, estilo: Estilo) -> None:
    _marca(slide, estilo, MARGEM, Inches(0.8), Inches(0.7))
    quadro = _caixa(slide, MARGEM, Inches(2.4), LARGURA - 2 * MARGEM, Inches(3.5))
    _paragrafo(quadro, conteudo.titulo, 44, estilo.texto, negrito=True, primeiro=True)
    _paragrafo(
        quadro,
        conteudo.subtitulo,
        24,
        marca.AZUL_TEXTO if estilo.escuro else marca.AZUL,
    )
    for nota in conteudo.notas:
        _paragrafo(quadro, nota, 14, estilo.apagado)


def apresentacao_em_pptx(
    deck: Apresentacao, gerado_em: datetime, estilo: Estilo = PADRAO
) -> bytes:
    """Os bytes do deck em .pptx, um slide por página do PDF."""
    arquivo = Presentation()
    arquivo.slide_width, arquivo.slide_height = LARGURA, ALTURA
    arquivo.core_properties.title = f"TickerLab — {deck.titulo}"
    arquivo.core_properties.author = "TickerLab"
    arquivo.core_properties.created = gerado_em
    total = len(deck.slides)
    for numero, conteudo in enumerate(deck.slides, start=1):
        slide = arquivo.slides.add_slide(arquivo.slide_layouts[6])  # em branco
        _fundo(slide, estilo)
        if conteudo.tipo == CAPA:
            _capa(slide, conteudo, estilo)
        else:
            _titulo(slide, conteudo.titulo, estilo)
            if conteudo.linhas:
                _tabela(slide, conteudo, estilo)
            if conteudo.topicos:
                _topicos(slide, conteudo.topicos, estilo)
            _notas(slide, conteudo.notas, estilo)
        _rodape(slide, deck, estilo, numero, total)
    saida = BytesIO()
    arquivo.save(saida)
    return saida.getvalue()
