"""O "papel timbrado" dos relatórios em PDF do TickerLab (fpdf2), com a identidade da marca.

Versão em fundo claro (`marca.PAPEL_*`): capa com o símbolo desenhado em vetor, cabeçalho e
rodapé em todas as páginas, cartões de números (o principal maior), tabelas com números
alinhados, gráficos (PNG de `graficos_pdf`) e um glossário curto no fim. As fontes (Manrope e
JetBrains Mono) vão embutidas no arquivo, então o PDF abre igual em qualquer computador.
"""

from datetime import datetime
from io import BytesIO

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from src import marca

MARGEM = 18  # mm
AVISO = (
    "Projeto educacional: nada aqui é recomendação de investimento. Dados do Yahoo Finance, "
    "que podem ter atraso ou erros. Rentabilidade passada não garante resultado futuro."
)


def _rgb(cor: str) -> tuple[int, int, int]:
    cor = cor.lstrip("#")
    return int(cor[0:2], 16), int(cor[2:4], 16), int(cor[4:6], 16)


class RelatorioPDF(FPDF):
    def __init__(self, titulo: str, subtitulo: str, gerado_em: datetime) -> None:
        super().__init__(format="A4", unit="mm")
        self.titulo_do_relatorio = titulo
        self.subtitulo = subtitulo
        self.gerado_em = gerado_em
        self.set_margins(MARGEM, MARGEM + 6, MARGEM)
        self.set_auto_page_break(True, margin=22)
        self.add_font("Manrope", "", str(marca.FONTE_PDF_TEXTO))
        self.add_font("Manrope", "B", str(marca.FONTE_PDF_TITULO))
        self.add_font(
            "Manrope", "I", str(marca.FONTE_PDF_MEDIA)
        )  # "médio" (rótulos), não itálico
        self.add_font("Mono", "", str(marca.FONTE_PDF_MONO))
        # a Manrope não tem ▲ ▼ ■ (as setas de alta e queda): esses vêm da JetBrains Mono
        self.set_fallback_fonts(["Mono"], exact_match=False)
        self.set_title(f"TickerLab — {titulo}")
        self.set_author("TickerLab")
        self.set_creator("TickerLab (tickerlab.com.br)")
        self.set_text_color(*_rgb(marca.PAPEL_TEXTO))

    # --- peças da marca ------------------------------------------------------------------
    def simbolo(self, x: float, y: float, tamanho: float) -> None:
        """A "Vela T" em vetor, na mesma grade de 32 do símbolo do site."""
        e = tamanho / 32
        self.set_fill_color(*_rgb(marca.AZUL))
        self.rect(
            x, y, tamanho, tamanho, style="F", round_corners=True, corner_radius=8 * e
        )
        self.set_fill_color(255, 255, 255)
        for rx, ry, largura, altura, raio in (
            (7, 7, 18, 3.6, 1.8),
            (14.6, 10, 2.8, 16, 1.4),
            (11.6, 13.5, 8.8, 9, 2),
        ):
            self.rect(
                x + rx * e, y + ry * e, largura * e, altura * e, style="F",
                round_corners=True, corner_radius=raio * e,
            )  # fmt: skip

    def nome_da_marca(self, x: float, y: float, tamanho: float) -> None:
        self.set_xy(x, y)
        self.set_font("Manrope", "B", tamanho)
        self.set_text_color(*_rgb(marca.PAPEL_TEXTO))
        self.cell(self.get_string_width("Ticker"), tamanho * 0.42, "Ticker")
        self.set_text_color(*_rgb(marca.AZUL))
        self.cell(self.get_string_width("Lab"), tamanho * 0.42, "Lab")
        self.set_text_color(*_rgb(marca.PAPEL_TEXTO))

    def header(self) -> None:
        if self.page_no() == 1:  # a capa tem a própria marca
            return
        self.simbolo(MARGEM, 10, 6)
        self.nome_da_marca(MARGEM + 8, 10.2, 11)
        self.set_font("Manrope", "", 8)
        self.set_text_color(*_rgb(marca.PAPEL_APAGADO))
        self.set_xy(MARGEM, 10.5)
        self.cell(self.epw, 5, self.titulo_do_relatorio, align="R")
        self.set_draw_color(*_rgb(marca.PAPEL_LINHA))
        self.line(MARGEM, 18.5, self.w - MARGEM, 18.5)
        self.set_text_color(*_rgb(marca.PAPEL_TEXTO))
        self.set_y(MARGEM + 6)

    def footer(self) -> None:
        self.set_y(-16)
        self.set_draw_color(*_rgb(marca.PAPEL_LINHA))
        self.line(MARGEM, self.get_y() - 1, self.w - MARGEM, self.get_y() - 1)
        self.set_font("Manrope", "", 7)
        self.set_text_color(*_rgb(marca.PAPEL_APAGADO))
        self.multi_cell(self.epw - 22, 3.4, AVISO, align="L")
        self.set_xy(self.w - MARGEM - 22, -16)
        self.cell(22, 3.4, f"Página {self.page_no()} de {{nb}}", align="R")
        self.set_text_color(*_rgb(marca.PAPEL_TEXTO))

    # --- capa e blocos -------------------------------------------------------------------
    def capa(self, linhas_de_resumo: list[tuple[str, str]]) -> None:
        self.add_page()
        self.simbolo(MARGEM, 30, 20)
        self.nome_da_marca(MARGEM + 25, 36, 24)
        self.set_xy(MARGEM, 72)
        self.set_font("Manrope", "I", 9)
        self.set_text_color(*_rgb(marca.AZUL))
        self.cell(0, 5, "RELATÓRIO", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*_rgb(marca.PAPEL_TEXTO))
        self.set_font("Manrope", "B", 26)
        self.multi_cell(
            0,
            11,
            self.titulo_do_relatorio,
            align="L",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        self.set_font("Manrope", "", 12)
        self.set_text_color(*_rgb(marca.PAPEL_APAGADO))
        self.multi_cell(
            0, 6.5, self.subtitulo, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT
        )
        self.ln(8)
        y = self.get_y()
        self.set_fill_color(*_rgb(marca.PAPEL_SUPERFICIE))
        altura = 8 + 6.5 * len(linhas_de_resumo)
        self.rect(
            MARGEM, y, self.epw, altura, style="F", round_corners=True, corner_radius=3
        )
        self.set_xy(MARGEM + 6, y + 4)
        for rotulo, valor in linhas_de_resumo:
            self.set_font("Manrope", "I", 9)
            self.set_text_color(*_rgb(marca.PAPEL_APAGADO))
            self.cell(48, 6.5, rotulo)
            self.set_font("Manrope", "B", 10)
            self.set_text_color(*_rgb(marca.PAPEL_TEXTO))
            self.cell(0, 6.5, valor, new_x=XPos.LEFT, new_y=YPos.NEXT)
            self.set_x(MARGEM + 6)
        self.set_y(y + altura + 10)
        self.set_font("Manrope", "", 9)
        self.set_text_color(*_rgb(marca.PAPEL_APAGADO))
        self.multi_cell(
            0, 4.8,
            "Como ler: cada número deste relatório tem uma explicação curta no glossário da "
            "última página. Os cálculos são os mesmos do site, com os dados do dia em que o "
            f"relatório foi gerado ({self.gerado_em:%d/%m/%Y às %H:%M}).",
        )  # fmt: skip
        self.set_text_color(*_rgb(marca.PAPEL_TEXTO))

    def secao(
        self, titulo: str, texto: str | None = None, reservar: float = 70
    ) -> None:
        """Título de seção. `reservar` (mm): o que precisa caber embaixo, para o título não ficar
        sozinho no pé da página."""
        if self.get_y() > self.h - 22 - reservar:
            self.add_page()
        self.ln(3)
        self.set_font("Manrope", "B", 14)
        self.set_text_color(*_rgb(marca.PAPEL_TEXTO))
        self.multi_cell(0, 7, titulo, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if texto:
            self.paragrafo(texto, apagado=True)
        self.ln(1)

    def paragrafo(self, texto: str, apagado: bool = False) -> None:
        self.set_font("Manrope", "", 9.5)
        self.set_text_color(
            *_rgb(marca.PAPEL_APAGADO if apagado else marca.PAPEL_TEXTO)
        )
        texto = texto.replace("**", "").replace(
            "`", ""
        )  # Markdown do site não vale no PDF
        self.multi_cell(0, 5, texto, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*_rgb(marca.PAPEL_TEXTO))

    def cartoes(
        self, itens: list[tuple[str, str, str | None]], por_linha: int = 4
    ) -> None:
        """Cartões de números. Cada item: (rótulo, valor, cor do valor ou None).

        O primeiro é o número principal: ocupa duas vagas e tem o valor maior. Nenhuma linha
        fica com buraco: a última divide a largura entre os cartões que sobraram.
        """
        espaco, altura = 3, 17
        linhas: list[list[tuple[int, int]]] = [[]]  # (índice do item, vagas)
        ocupadas = 0
        for i in range(len(itens)):
            vagas = 2 if i == 0 else 1
            if ocupadas + vagas > por_linha:
                linhas.append([])
                ocupadas = 0
            linhas[-1].append((i, vagas))
            ocupadas += vagas
        if len(linhas) > 1 and len(linhas[-1]) == 1 and len(linhas[-2]) > 2:
            linhas[-1].insert(
                0, linhas[-2].pop()
            )  # nenhum cartão sozinho na última linha
        for linha in linhas:
            if self.get_y() + altura > self.h - 25:
                self.add_page()
            y = self.get_y()
            total = sum(v for _, v in linha)
            unidade = (self.epw - espaco * (len(linha) - 1)) / total
            x = MARGEM
            for i, vagas in linha:
                rotulo, valor, cor = itens[i]
                principal = i == 0
                w = unidade * vagas
                fundo = "#e8eefc" if principal else marca.PAPEL_SUPERFICIE
                self.set_fill_color(*_rgb(fundo))
                self.rect(
                    x, y, w, altura, style="F", round_corners=True, corner_radius=2.5
                )
                self.set_xy(x + 3.5, y + 2.6)
                self.set_font("Manrope", "I", 7.5)
                self.set_text_color(*_rgb(marca.PAPEL_APAGADO))
                self.cell(w - 7, 4, rotulo)
                self.set_xy(x + 3.5, y + 7.6)
                self.set_font("Manrope", "B", 15 if principal else 12.5)
                self.set_text_color(*_rgb(cor or marca.PAPEL_TEXTO))
                self.cell(w - 7, 7, valor)
                x += w + espaco
            self.set_y(y + altura + espaco)
        self.set_text_color(*_rgb(marca.PAPEL_TEXTO))
        self.ln(2)

    def imagem(self, png: bytes, altura_mm: float | None = None) -> None:
        """Um gráfico na largura útil da página (quebra de página se não couber)."""
        # largura e altura ficam nos bytes 16 a 24 do cabeçalho de todo PNG
        largura_px = int.from_bytes(png[16:20], "big")
        altura_px = int.from_bytes(png[20:24], "big")
        altura = altura_mm or self.epw * altura_px / largura_px
        if self.get_y() + altura > self.h - 24:
            self.add_page()
        self.image(BytesIO(png), x=MARGEM, w=self.epw, h=altura)
        self.ln(3)

    def tabela(
        self,
        cabecalho: list[str],
        linhas: list[list[str]],
        larguras: list[float] | None = None,
        cores: list[list[str | None]] | None = None,
        tickers: bool = False,
    ) -> None:
        """Tabela simples: a primeira coluna à esquerda (nomes), as outras à direita (números).

        Com `tickers`, a primeira coluna usa a fonte monoespaçada, como numa tela de cotações.
        """
        larguras = larguras or [self.epw / len(cabecalho)] * len(cabecalho)
        if self.get_y() + 8 * (len(linhas) + 1) > self.h - 24:
            self.add_page()
        self.set_font("Manrope", "I", 8)
        self.set_text_color(*_rgb(marca.PAPEL_APAGADO))
        for i, (texto, largura) in enumerate(zip(cabecalho, larguras, strict=True)):
            self.cell(largura, 7, texto, align="L" if i == 0 else "R")
        self.ln(7)
        self.set_draw_color(*_rgb(marca.PAPEL_LINHA))
        for n, linha in enumerate(linhas):
            y = self.get_y()
            self.line(MARGEM, y, self.w - MARGEM, y)
            for i, (texto, largura) in enumerate(zip(linha, larguras, strict=True)):
                cor = cores[n][i] if cores else None
                self.set_text_color(*_rgb(cor or marca.PAPEL_TEXTO))
                if i == 0:
                    self.set_font("Mono" if tickers else "Manrope", "", 9)
                else:
                    self.set_font("Manrope", "B", 9)
                self.cell(largura, 7, texto, align="L" if i == 0 else "R")
            self.ln(7)
        self.line(MARGEM, self.get_y(), self.w - MARGEM, self.get_y())
        self.set_text_color(*_rgb(marca.PAPEL_TEXTO))
        self.ln(4)

    def glossario(self, termos: dict[str, str]) -> None:
        """O que cada número quer dizer (textos do glossário do site)."""
        if not termos:
            return
        self.secao("Glossário", "O que cada número deste relatório quer dizer.")
        for termo, texto in termos.items():
            if self.get_y() > self.h - 40:
                self.add_page()
            self.set_font("Manrope", "B", 9.5)
            self.multi_cell(0, 5, termo, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.paragrafo(texto, apagado=True)
            self.ln(1.5)

    def aviso_destacado(self, texto: str) -> None:
        y = self.get_y() + 2
        self.set_font("Manrope", "", 9)
        linhas = len(
            self.multi_cell(self.epw - 10, 4.8, texto, dry_run=True, output="LINES")
        )
        altura = 6 + 4.8 * linhas
        if y + altura > self.h - 24:
            self.add_page()
            y = self.get_y()
        self.set_fill_color(253, 246, 228)
        self.rect(
            MARGEM,
            y,
            self.epw,
            altura,
            style="F",
            round_corners=True,
            corner_radius=2.5,
        )
        self.set_xy(MARGEM + 5, y + 3)
        self.set_text_color(*_rgb(marca.PAPEL_TEXTO))
        self.multi_cell(self.epw - 10, 4.8, texto)
        self.set_y(y + altura + 4)

    def para_bytes(self) -> bytes:
        return bytes(self.output())
