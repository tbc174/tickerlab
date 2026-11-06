"""O deck em PDF (16:9) da ficha e do relatório do setor: um slide por página, com as cores e as fontes
da marca (`src/marca.py`, `src/estilos_pdf.py`). Lê a `Apresentacao` de `src/apresentacao.py`; o
`src/apresentacao_pptx.py` lê a mesma, então os dois formatos saem com os mesmos slides."""

from datetime import datetime
from io import BytesIO

from fpdf import FPDF
from fpdf.enums import MethodReturnValue, XPos, YPos

from src import marca
from src.apresentacao import CAPA, Apresentacao, Slide
from src.estilos_pdf import PADRAO, Estilo
from src.relatorio_pdf import NUMERO_ESCRITO, _rgb

LARGURA = 297.0  # mm; a página 16:9
ALTURA = 167.0
MARGEM = 16.0
TOPO = 38.0  # onde o corpo começa (embaixo do título)
RODAPE = 14.0
ESPACO_DAS_NOTAS = 12.0
TAMANHO_DO_CORPO = 14.0
TAMANHO_DA_TABELA = 11.0
TAMANHO_MINIMO = 8.0
MM_POR_PONTO = 0.3528


class DeckPDF(FPDF):
    def __init__(self, deck: Apresentacao, gerado_em: datetime, estilo: Estilo) -> None:
        super().__init__(orientation="L", unit="mm", format=(ALTURA, LARGURA))
        self.deck = deck
        self.estilo = estilo
        self.set_margins(MARGEM, MARGEM, MARGEM)
        self.set_auto_page_break(False)
        self.add_font("Manrope", "", str(marca.FONTE_PDF_TEXTO))
        self.add_font("Manrope", "B", str(marca.FONTE_PDF_TITULO))
        self.add_font(
            "Manrope", "I", str(marca.FONTE_PDF_MEDIA)
        )  # "médio", não itálico
        self.add_font("Mono", "", str(marca.FONTE_PDF_MONO))
        self.set_fallback_fonts(["Mono"], exact_match=False)
        self.set_title(f"TickerLab — {deck.titulo}")
        self.set_author("TickerLab")
        self.set_creator("TickerLab (tickerlab.com.br)")
        self.creation_date = gerado_em

    def _render_styled_text_line(self, *args, **kwargs) -> bool:  # noqa: ANN002, ANN003
        """Mesmo conserto do `RelatorioPDF`: depois de uma linha com fonte reserva, o fpdf2 2.8.9
        acha que a fonte já está declarada na página e a célula seguinte sai com a fonte errada."""
        try:
            return super()._render_styled_text_line(*args, **kwargs)
        finally:
            self.current_font_is_set_on_page = False

    # --- peças --------------------------------------------------------------------------
    def _texto(self, apagado: bool = False) -> None:
        cor = self.estilo.apagado if apagado else self.estilo.texto
        self.set_text_color(*_rgb(cor))

    def _azul(self) -> None:
        cor = marca.AZUL_TEXTO if self.estilo.escuro else marca.AZUL
        self.set_text_color(*_rgb(cor))

    def _fundo(self) -> None:
        self.set_fill_color(*_rgb(self.estilo.fundo))
        self.rect(0, 0, self.w, self.h, style="F")
        if self.estilo.faixa:
            self.set_fill_color(*_rgb(self.estilo.faixa))
            self.rect(0, 0, self.w, 6, style="F")

    def _marca(self, x: float, y: float, tamanho: float) -> None:
        topo = marca.CLARO if self.estilo.escuro else marca.MARINHO
        svg = marca.simbolo_svg(topo=topo).encode("utf-8")
        self.image(BytesIO(svg), x=x, y=y, w=tamanho, h=tamanho)
        self.set_xy(x + tamanho + 2, y + tamanho * 0.18)
        self.set_font("Manrope", "B", tamanho * 1.6)
        self._texto()
        self.cell(self.get_string_width("Ticker"), tamanho * 0.64, "Ticker")
        self._azul()
        self.cell(self.get_string_width("Lab"), tamanho * 0.64, "Lab")
        self._texto()

    def _rodape(self, pagina: int, total: int) -> None:
        y = self.h - RODAPE
        self.set_draw_color(*_rgb(self.estilo.linha))
        self.line(MARGEM, y, self.w - MARGEM, y)
        self.set_font("Manrope", "", 7.5)
        self._texto(apagado=True)
        self.set_xy(MARGEM, y + 1.5)
        self.multi_cell(self.w - 2 * MARGEM - 24, 3.6, self.deck.aviso, align="L")
        self.set_xy(self.w - MARGEM - 24, y + 1.5)
        self.cell(24, 3.6, f"{pagina} / {total}", align="R")

    def _titulo(self, slide: Slide) -> None:
        self.set_xy(MARGEM, 13)
        self.set_font("Manrope", "B", 22 if len(slide.titulo) < 60 else 17)
        self._texto()
        self.multi_cell(
            self.w - 2 * MARGEM, 9, slide.titulo, new_x=XPos.LMARGIN, new_y=YPos.NEXT
        )
        self.set_fill_color(*_rgb(marca.AZUL))
        self.rect(MARGEM, 30, 18, 1.2, style="F")

    def _linhas(self, largura: float, passo: float, texto: str) -> int:
        return len(
            self.multi_cell(
                largura, passo, texto, dry_run=True, output=MethodReturnValue.LINES
            )
        )

    # --- corpo ---------------------------------------------------------------------------
    def _topicos(self, topicos: tuple[str, ...], limite: float) -> float:
        """Os tópicos com marcador; o corpo diminui até caber. Devolve o y onde terminou."""
        largura = self.w - 2 * MARGEM - 7
        tamanho = TAMANHO_DO_CORPO
        while True:
            self.set_font("Manrope", "", tamanho)
            passo = tamanho * MM_POR_PONTO * 1.45
            altura = sum(self._linhas(largura, passo, t) * passo + 2.5 for t in topicos)
            if TOPO + altura <= limite or tamanho <= TAMANHO_MINIMO:
                break
            tamanho -= 0.5
        y = TOPO
        for topico in topicos:
            self.set_xy(MARGEM, y)
            self.set_font("Manrope", "B", tamanho)
            self._azul()
            self.cell(7, passo, "•")
            self.set_font("Manrope", "", tamanho)
            self._texto()
            self.multi_cell(largura, passo, topico, align="L")
            y = self.get_y() + 2.5
        return y

    def _larguras(self, colunas: list[list[str]], total: float) -> list[float]:
        """Cada coluna com a largura do texto mais longo; sem caber, as mais largas dividem o que
        sobra (e o texto delas quebra a linha)."""
        naturais = [max(self.get_string_width(t) for t in c) + 4 for c in colunas]
        if sum(naturais) <= total:
            return [n * total / sum(naturais) for n in naturais]
        teto, sobra = total / len(naturais), total
        for n, natural in enumerate(sorted(naturais)):
            teto = sobra / (len(naturais) - n)
            if natural > teto:
                break
            sobra -= natural
        return [min(n, teto) for n in naturais]

    def _tabela(self, slide: Slide, limite: float) -> float:
        largura_total = self.w - 2 * MARGEM
        tamanho = TAMANHO_DA_TABELA
        while True:
            passo = tamanho * MM_POR_PONTO * 1.35
            self.set_font("Manrope", "", tamanho)
            larguras = self._larguras(
                [list(c) for c in zip(slide.cabecalho, *slide.linhas, strict=True)],
                largura_total,
            )
            alturas = [
                max(
                    self._linhas(w - 2, passo, texto)
                    for texto, w in zip(linha, larguras, strict=True)
                )
                * passo
                + 3
                for linha in slide.linhas
            ]
            if TOPO + 8 + sum(alturas) <= limite or tamanho <= TAMANHO_MINIMO:
                break
            tamanho -= 0.5
        numeros = [
            all(NUMERO_ESCRITO.match(linha[i]) for linha in slide.linhas)
            for i in range(len(slide.cabecalho))
        ]
        self.set_font("Manrope", "I", min(9, tamanho))
        self._texto(apagado=True)
        x = MARGEM
        for texto, w, direita in zip(slide.cabecalho, larguras, numeros, strict=True):
            self.set_xy(x, TOPO)
            self.cell(w, 6, texto, align="R" if direita else "L")
            x += w
        y = TOPO + 8
        self.set_draw_color(*_rgb(self.estilo.linha))
        for linha, altura in zip(slide.linhas, alturas, strict=True):
            self.line(MARGEM, y, self.w - MARGEM, y)
            x = MARGEM
            for i, (texto, w) in enumerate(zip(linha, larguras, strict=True)):
                self.set_xy(x, y + 1.5)
                self.set_font("Manrope", "B" if i == 1 else "", tamanho)
                self._texto()
                self.multi_cell(w - 2, passo, texto, align="R" if numeros[i] else "L")
                x += w
            y += altura
        self.line(MARGEM, y, self.w - MARGEM, y)
        return y + 3

    def _notas(self, notas: tuple[str, ...], de: float) -> None:
        if not notas:
            return
        self.set_font("Manrope", "", 8)
        self._texto(apagado=True)
        self.set_xy(MARGEM, de)
        self.multi_cell(self.w - 2 * MARGEM, 3.8, "\n".join(notas), align="L")

    def _capa(self, slide: Slide) -> None:
        self._marca(MARGEM, 22, 14)
        self.set_xy(MARGEM, 62)
        self.set_font("Manrope", "B", 34)
        self._texto()
        self.multi_cell(self.w - 2 * MARGEM, 14, slide.titulo, new_x=XPos.LMARGIN)
        self.set_font("Manrope", "", 18)
        self._azul()
        self.set_x(MARGEM)
        self.multi_cell(self.w - 2 * MARGEM, 9, slide.subtitulo)
        self._notas(slide.notas, self.get_y() + 8)

    def escrever(self) -> None:
        total = len(self.deck.slides)
        for numero, slide in enumerate(self.deck.slides, start=1):
            self.add_page()
            self._fundo()
            if slide.tipo == CAPA:
                self._capa(slide)
            else:
                limite = self.h - RODAPE - ESPACO_DAS_NOTAS
                self._titulo(slide)
                fim = self._tabela(slide, limite) if slide.linhas else TOPO
                if slide.topicos:
                    fim = self._topicos(slide.topicos, limite)
                self._notas(slide.notas, min(fim + 2, limite))
            self._rodape(numero, total)


def apresentacao_em_pdf(
    deck: Apresentacao, gerado_em: datetime, estilo: Estilo = PADRAO
) -> bytes:
    """Os bytes do deck em PDF, um slide por página."""
    pdf = DeckPDF(deck, gerado_em, estilo)
    pdf.escrever()
    return bytes(pdf.output())
