"""O "papel timbrado" dos relatórios em PDF do TickerLab (fpdf2), com a identidade da marca.

Capa com o símbolo desenhado em vetor e o sumário, cabeçalho e rodapé em todas as páginas,
seções numeradas (que também viram marcadores do PDF, para navegar no leitor), cartões de números
(o principal maior), tabelas com números alinhados, gráficos (PNG de `graficos_pdf`) e um
glossário. As cores vêm do estilo escolhido (`estilos_pdf`: Research, Terminal ou Institucional).
As fontes (Manrope e JetBrains Mono) vão embutidas no arquivo, então o PDF abre igual em qualquer
computador.
"""

import re
from datetime import datetime
from io import BytesIO

from fpdf import FPDF
from fpdf.enums import MethodReturnValue, XPos, YPos

from src import marca
from src.estilos_pdf import PADRAO, Estilo

MARGEM = 18  # mm
# uma célula que é número já escrito ("R$ 1,7 bi", "11,1%", "370", "4,8"): vai à direita
NUMERO_ESCRITO = re.compile(r"^(R\$ |US\$ )?[-−]?[\d.,]+( mil| mi| bi)?%?$|^—$")
AVISO = (
    "Nada aqui é recomendação de investimento. Dados do Yahoo Finance, "
    "que podem ter atraso ou erros. Rentabilidade passada não garante resultado futuro."
)


def _rgb(cor: str) -> tuple[int, int, int]:
    cor = cor.lstrip("#")
    return int(cor[0:2], 16), int(cor[2:4], 16), int(cor[4:6], 16)


class RelatorioPDF(FPDF):
    def __init__(
        self,
        titulo: str,
        subtitulo: str,
        gerado_em: datetime,
        estilo: Estilo = PADRAO,
        aviso: str = AVISO,
    ) -> None:
        super().__init__(format="A4", unit="mm")
        self.aviso = aviso  # o rodapé de cada página (de onde vêm os dados)
        self.titulo_do_relatorio = titulo
        self.subtitulo = subtitulo
        self.gerado_em = gerado_em
        self.estilo = estilo
        self.numero_da_secao = 0
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
        self.creation_date = gerado_em  # a data dos dados, não a do computador
        self.set_text_color(*_rgb(estilo.texto))

    def _render_styled_text_line(self, *args, **kwargs) -> bool:  # noqa: ANN002, ANN003
        """Depois de cada linha de texto, obriga o fpdf2 a declarar a fonte de novo.

        Defeito do fpdf2 2.8.9: numa célula com a fonte reserva (as setas ▲ ▼ ■ vêm da JetBrains
        Mono), a troca de fonte fica dentro do `q … Q` da célula, que o PDF desfaz no fim; mesmo
        assim o fpdf2 passa a achar que a fonte já está declarada na página. A célula seguinte,
        na mesma fonte, saía desenhada com a fonte de antes: quadradinhos no lugar dos números
        (tabela "Cada ativo sozinho" da carteira e a tabela da comparação).
        """
        try:
            return super()._render_styled_text_line(*args, **kwargs)
        finally:
            self.current_font_is_set_on_page = False

    def _cor_do_texto(self, apagado: bool = False) -> None:
        self.set_text_color(
            *_rgb(self.estilo.apagado if apagado else self.estilo.texto)
        )

    # --- peças da marca ------------------------------------------------------------------
    def simbolo(
        self, x: float, y: float, tamanho: float, topo: str | None = None
    ) -> None:
        """O símbolo T geométrico em vetor (o mesmo SVG do site). O topo é marinho no papel e
        claro no fundo escuro e na faixa marinha; a haste é sempre azul elétrico."""
        if topo is None:
            topo = marca.CLARO if self.estilo.escuro else marca.MARINHO
        svg = marca.simbolo_svg(topo=topo).encode("utf-8")
        self.image(BytesIO(svg), x=x, y=y, w=tamanho, h=tamanho)

    def nome_da_marca(
        self, x: float, y: float, tamanho: float, sobre_a_faixa: bool = False
    ) -> None:
        texto = self.estilo.texto_da_faixa if sobre_a_faixa else self.estilo.texto
        # o azul elétrico perde contraste no escuro e na faixa marinha: lá vai o azul mais claro
        no_escuro = sobre_a_faixa or self.estilo.escuro
        lab = marca.AZUL_TEXTO if no_escuro else marca.AZUL
        self.set_xy(x, y)
        self.set_font("Manrope", "B", tamanho)
        self.set_text_color(*_rgb(texto))
        self.cell(self.get_string_width("Ticker"), tamanho * 0.42, "Ticker")
        self.set_text_color(*_rgb(lab))
        self.cell(self.get_string_width("Lab"), tamanho * 0.42, "Lab")
        self._cor_do_texto()

    def _pintar_o_fundo(self) -> None:
        if self.estilo.escuro:
            self.set_fill_color(*_rgb(self.estilo.fundo))
            self.rect(0, 0, self.w, self.h, style="F")

    def header(self) -> None:
        self._pintar_o_fundo()
        if self.page_no() == 1:  # a capa tem a própria marca
            return
        faixa = self.estilo.faixa
        if faixa:
            self.set_fill_color(*_rgb(faixa))
            self.rect(0, 0, self.w, 16, style="F")
            self.simbolo(MARGEM, 5, 6, topo=marca.CLARO)
            self.nome_da_marca(MARGEM + 8, 5.2, 11, sobre_a_faixa=True)
            self.set_text_color(*_rgb(self.estilo.texto_da_faixa))
            self.set_font("Manrope", "", 8)
            self.set_xy(MARGEM, 5.5)
            self.cell(self.epw, 5, self.titulo_do_relatorio, align="R")
        else:
            self.simbolo(MARGEM, 10, 6)
            self.nome_da_marca(MARGEM + 8, 10.2, 11)
            self.set_font("Manrope", "", 8)
            self._cor_do_texto(apagado=True)
            self.set_xy(MARGEM, 10.5)
            self.cell(self.epw, 5, self.titulo_do_relatorio, align="R")
            self.set_draw_color(*_rgb(self.estilo.linha))
            self.line(MARGEM, 18.5, self.w - MARGEM, 18.5)
        self._cor_do_texto()
        self.set_y(MARGEM + 6)

    def footer(self) -> None:
        self.set_y(-16)
        self.set_draw_color(*_rgb(self.estilo.linha))
        self.line(MARGEM, self.get_y() - 1, self.w - MARGEM, self.get_y() - 1)
        self.set_font("Manrope", "", 7)
        self._cor_do_texto(apagado=True)
        self.multi_cell(self.epw - 22, 3.4, self.aviso, align="L")
        self.set_xy(self.w - MARGEM - 22, -16)
        self.cell(22, 3.4, f"Página {self.page_no()} de {{nb}}", align="R")
        self._cor_do_texto()

    # --- capa e blocos -------------------------------------------------------------------
    def capa(
        self, linhas_de_resumo: list[tuple[str, str]], sumario: list[str] | None = None
    ) -> None:
        """A capa: marca, título, quadro de resumo e, se houver, o que vem no relatório."""
        self.add_page()
        faixa = self.estilo.faixa
        if faixa:  # Institucional: o topo da capa é um bloco marinho com a marca clara
            self.set_fill_color(*_rgb(faixa))
            self.rect(0, 0, self.w, 60, style="F")
            self.simbolo(MARGEM, 26.5, 13, topo=marca.CLARO)
            self.nome_da_marca(MARGEM + 17, 28, 24, sobre_a_faixa=True)
        else:
            self.simbolo(MARGEM, 34.5, 13)
            self.nome_da_marca(MARGEM + 17, 36, 24)
        self.set_xy(MARGEM, 72)
        self.set_font("Manrope", "I", 9)
        self.set_text_color(
            *_rgb(marca.AZUL_TEXTO if self.estilo.escuro else marca.AZUL)
        )
        self.cell(0, 5, "RELATÓRIO", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._cor_do_texto()
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
        self._cor_do_texto(apagado=True)
        self.multi_cell(
            0, 6.5, self.subtitulo, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT
        )
        self.ln(8)
        y = self.get_y()
        self.set_fill_color(*_rgb(self.estilo.superficie))
        altura = 8 + 6.5 * len(linhas_de_resumo)
        self.rect(
            MARGEM, y, self.epw, altura, style="F", round_corners=True, corner_radius=3
        )
        self.set_xy(MARGEM + 6, y + 4)
        for rotulo, valor in linhas_de_resumo:
            self.set_font("Manrope", "I", 9)
            self._cor_do_texto(apagado=True)
            self.cell(48, 6.5, rotulo)
            self.set_font("Manrope", "B", 10)
            self._cor_do_texto()
            self.cell(0, 6.5, valor, new_x=XPos.LEFT, new_y=YPos.NEXT)
            self.set_x(MARGEM + 6)
        self.set_y(y + altura + 8)
        if sumario:
            self.set_font("Manrope", "I", 9)
            self._cor_do_texto(apagado=True)
            self.cell(0, 5, "NESTE RELATÓRIO", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font("Manrope", "", 10)
            self._cor_do_texto()
            for n, titulo in enumerate(sumario, start=1):
                self.cell(
                    0, 5.6, f"{n}.  {titulo}", new_x=XPos.LMARGIN, new_y=YPos.NEXT
                )
            self.ln(5)
        self.set_font("Manrope", "", 9)
        self._cor_do_texto(apagado=True)
        self.multi_cell(
            0, 4.8,
            "Como ler: os números saem dos mesmos cálculos do site, com os dados do dia em que "
            f"o relatório foi gerado ({self.gerado_em:%d/%m/%Y às %H:%M}). Descreve o passado; "
            "não é previsão nem recomendação.",
        )  # fmt: skip
        self._cor_do_texto()

    def secao(
        self,
        titulo: str,
        texto: str | None = None,
        reservar: float = 70,
        numerada: bool = False,
    ) -> None:
        """Título de seção. `reservar` (mm): o que precisa caber embaixo, para o título não ficar
        sozinho no pé da página. Numerada, ela ganha o número e um marcador no PDF."""
        if self.get_y() > self.h - 22 - reservar:
            self.add_page()
        self.ln(3)
        if numerada:
            self.numero_da_secao += 1
            titulo = f"{self.numero_da_secao}. {titulo}"
            self.start_section(titulo)
        self.set_font("Manrope", "B", 14)
        self._cor_do_texto()
        self.multi_cell(0, 7, titulo, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if texto:
            self.paragrafo(texto, apagado=True)
        self.ln(1)

    def paragrafo(self, texto: str, apagado: bool = False) -> None:
        self.set_font("Manrope", "", 9.5)
        self._cor_do_texto(apagado)
        texto = texto.replace("**", "").replace(
            "`", ""
        )  # Markdown do site não vale no PDF
        self.multi_cell(0, 5, texto, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._cor_do_texto()

    def lista(self, itens: list[str]) -> None:
        """Uma lista com marcadores (os achados do resumo executivo)."""
        for item in itens:
            if self.get_y() > self.h - 34:
                self.add_page()
            self.set_font("Manrope", "B", 9.5)
            self.set_text_color(
                *_rgb(marca.AZUL_TEXTO if self.estilo.escuro else marca.AZUL)
            )
            self.cell(5, 5.4, "•")
            self.set_font("Manrope", "", 9.5)
            self._cor_do_texto()
            self.multi_cell(
                self.epw - 5, 5.4, item.replace("**", ""), new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )  # fmt: skip
            self.ln(1.2)
        self.ln(2)

    def pares(self, itens: list[tuple[str, str]]) -> None:
        """Rótulo e valor em duas colunas (metodologia e reprodutibilidade)."""
        for rotulo, valor in itens:
            if self.get_y() > self.h - 30:
                self.add_page()
            self.set_font("Manrope", "I", 8.5)
            self._cor_do_texto(apagado=True)
            self.cell(52, 5, rotulo)
            self.set_font("Manrope", "", 9)
            self._cor_do_texto()
            self.multi_cell(
                self.epw - 52, 5, valor, new_x=XPos.LMARGIN, new_y=YPos.NEXT
            )
            self.ln(0.8)
        self.ln(2)

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
                fundo = self.estilo.destaque if principal else self.estilo.superficie
                self.set_fill_color(*_rgb(fundo))
                self.rect(
                    x, y, w, altura, style="F", round_corners=True, corner_radius=2.5
                )
                self.set_xy(x + 3.5, y + 2.6)
                self.set_font("Manrope", "I", 7.5)
                self._cor_do_texto(apagado=True)
                self.cell(w - 7, 4, rotulo)
                self.set_xy(x + 3.5, y + 7.6)
                self.set_font("Manrope", "B", 15 if principal else 12.5)
                self.set_text_color(*_rgb(cor or self.estilo.texto))
                self.cell(w - 7, 7, valor)
                x += w + espaco
            self.set_y(y + altura + espaco)
        self._cor_do_texto()
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
        tamanho: float = 9,
    ) -> None:
        """Tabela simples: a primeira coluna à esquerda (nomes), as outras à direita (números).

        Com `tickers`, a primeira coluna usa a fonte monoespaçada, como numa tela de cotações.
        """
        larguras = larguras or [self.epw / len(cabecalho)] * len(cabecalho)
        if self.get_y() + 8 * (len(linhas) + 1) > self.h - 24:
            self.add_page()
        self.set_font("Manrope", "I", min(8, tamanho))
        self._cor_do_texto(apagado=True)
        for i, (texto, largura) in enumerate(zip(cabecalho, larguras, strict=True)):
            self.cell(largura, 7, texto, align="L" if i == 0 else "R")
        self.ln(7)
        self.set_draw_color(*_rgb(self.estilo.linha))
        for n, linha in enumerate(linhas):
            if self.get_y() + 7 > self.h - 24:
                self.add_page()
                self.set_draw_color(*_rgb(self.estilo.linha))
            y = self.get_y()
            self.line(MARGEM, y, self.w - MARGEM, y)
            for i, (texto, largura) in enumerate(zip(linha, larguras, strict=True)):
                cor = cores[n][i] if cores else None
                self.set_text_color(*_rgb(cor or self.estilo.texto))
                if i == 0:
                    self.set_font("Mono" if tickers else "Manrope", "", tamanho)
                else:
                    self.set_font("Manrope", "B", tamanho)
                self.cell(largura, 7, texto, align="L" if i == 0 else "R")
            self.ln(7)
        self.line(MARGEM, self.get_y(), self.w - MARGEM, self.get_y())
        self._cor_do_texto()
        self.ln(4)

    def _larguras_do_texto(self, colunas: list[list[str]]) -> list[float]:
        """Cada coluna com a largura do texto mais longo; sem caber, as mais largas dividem o que
        sobra por igual (e o texto delas quebra a linha)."""
        naturais = [
            max(self.get_string_width(texto) for texto in coluna) + 3
            for coluna in colunas
        ]
        if sum(naturais) <= self.epw:
            return [n * self.epw / sum(naturais) for n in naturais]
        teto, sobra, largas = self.epw / len(naturais), self.epw, sorted(naturais)
        for n, natural in enumerate(largas):
            teto = sobra / (len(largas) - n)
            if natural > teto:
                break
            sobra -= natural
        return [min(natural, teto) for natural in naturais]

    def tabela_de_texto(self, cabecalho: list[str], linhas: list[list[str]]) -> None:
        """Tabela de nomes e frases (as do dossiê da base): o texto longo quebra a linha, as colunas
        de número ficam à direita."""
        self.set_font("Manrope", "", 8.5)
        larguras = self._larguras_do_texto(
            [list(coluna) for coluna in zip(cabecalho, *linhas, strict=True)]
        )
        numeros = [
            all(NUMERO_ESCRITO.match(linha[i]) for linha in linhas)
            for i in range(len(cabecalho))
        ]
        alinhar = ["R" if numero else "L" for numero in numeros]
        if self.get_y() + 7 * min(len(linhas) + 1, 4) > self.h - 24:
            self.add_page()
        self.set_font("Manrope", "I", 8)
        self._cor_do_texto(apagado=True)
        for texto, largura, lado in zip(cabecalho, larguras, alinhar, strict=True):
            self.cell(largura, 7, texto, align=lado)
        self.ln(7)
        self.set_draw_color(*_rgb(self.estilo.linha))
        self.set_font("Manrope", "", 8.5)
        self._cor_do_texto()
        for linha in linhas:
            partes = [
                self.multi_cell(
                    largura - 1.5,
                    4.4,
                    texto,
                    dry_run=True,
                    output=MethodReturnValue.LINES,
                )
                for texto, largura in zip(linha, larguras, strict=True)
            ]
            altura = max(len(p) for p in partes) * 4.4 + 2.6
            if self.get_y() + altura > self.h - 24:
                self.add_page()
                self.set_draw_color(*_rgb(self.estilo.linha))
            y = self.get_y()
            self.line(MARGEM, y, self.w - MARGEM, y)
            x = MARGEM
            for texto, largura, lado in zip(linha, larguras, alinhar, strict=True):
                self.set_xy(x, y + 1.3)
                self.multi_cell(largura - 1.5, 4.4, texto, align=lado)
                x += largura
            self.set_xy(MARGEM, y + altura)
        self.line(MARGEM, self.get_y(), self.w - MARGEM, self.get_y())
        self.ln(4)

    def glossario(self, termos: dict[str, str]) -> None:
        """O que cada número quer dizer (textos do glossário do site)."""
        for termo, texto in termos.items():
            if self.get_y() > self.h - 40:
                self.add_page()
            self.set_font("Manrope", "B", 9.5)
            self._cor_do_texto()
            self.multi_cell(0, 5, termo, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.paragrafo(texto, apagado=True)
            self.ln(1.5)

    def item(
        self,
        titulo: str,
        texto: str,
        link: str = "",
        rotulo_do_link: str = "",
        nota: str = "",
    ) -> None:
        """Um item de lista longa (a Newsletter): título, texto, nota apagada e link clicável."""
        if self.get_y() > self.h - 50:
            self.add_page()
        self.set_font("Manrope", "B", 10)
        self._cor_do_texto()
        self.multi_cell(0, 5.4, titulo, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.paragrafo(texto)
        if nota:
            self.paragrafo(nota, apagado=True)
        if link:
            self.set_font("Manrope", "I", 8.5)
            self.set_text_color(
                *_rgb(marca.AZUL_TEXTO if self.estilo.escuro else marca.AZUL)
            )
            self.cell(0, 5, rotulo_do_link or "Abrir o documento original", link=link,
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)  # fmt: skip
            self._cor_do_texto()
        self.ln(2.5)

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
        self.set_fill_color(*_rgb(self.estilo.aviso))
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
        self._cor_do_texto()
        self.multi_cell(self.epw - 10, 4.8, texto)
        self.set_y(y + altura + 4)

    def para_bytes(self) -> bytes:
        return bytes(self.output())
