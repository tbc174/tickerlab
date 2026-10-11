"""A prévia do Report Studio: páginas do PDF de verdade transformadas em imagens.

A prévia não é um desenho parecido com o relatório: é o próprio PDF, gerado pelo mesmo código,
renderizado pelo PDFium (o motor de PDF do Chrome, via `pypdfium2`). Por isso o que se vê é
exatamente o que se baixa (blueprint, PDF-01).
"""

from io import BytesIO

import pypdfium2

PONTOS_POR_POLEGADA = 72


def contar_paginas(pdf: bytes) -> int:
    documento = pypdfium2.PdfDocument(pdf)
    try:
        return len(documento)
    finally:
        documento.close()


def paginas_em_png(
    pdf: bytes, paginas: int | None = None, largura_px: int = 640
) -> list[bytes]:
    """As primeiras `paginas` (todas, se None) como PNG com `largura_px` de largura."""
    documento = pypdfium2.PdfDocument(pdf)
    try:
        total = len(documento) if paginas is None else min(paginas, len(documento))
        imagens = []
        for i in range(total):
            pagina = documento[i]
            escala = largura_px / pagina.get_width()
            arquivo = BytesIO()
            pagina.render(scale=escala).to_pil().save(arquivo, format="PNG")
            imagens.append(arquivo.getvalue())
            pagina.close()
        return imagens
    finally:
        documento.close()
