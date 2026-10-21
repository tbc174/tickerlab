"""Arquivos de teste da sala de dados (B-20), gerados na hora: os bons e os maliciosos.

Nada vem da internet: cada arquivo é montado aqui com fpdf2, pypdf, openpyxl ou zipfile, do
tamanho mínimo que ainda prova o ponto.
"""

import io
import zipfile
import zlib

from fpdf import FPDF
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, TextStringObject

# um CPF válido (os dígitos verificadores batem) e o mesmo número com o último dígito errado
CPF_VALIDO = "529.982.247-25"
CPF_INVALIDO = "529.982.247-26"

_TIPOS_DO_XLSX = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Override PartName="/xl/workbook.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    "</Types>"
)
_TIPOS_DO_DOCX = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Override PartName="/word/document.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)
_NS_DO_WORD = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def pdf(*paginas: str) -> bytes:
    """Um PDF simples, uma página por texto."""
    documento = FPDF()
    documento.set_font("helvetica", size=12)
    for texto in paginas or ("",):
        documento.add_page()
        if texto:
            documento.cell(text=texto)
    return bytes(documento.output())


def _pelo_pypdf(mudar) -> bytes:
    escritor = PdfWriter(clone_from=io.BytesIO(pdf("pagina")))
    mudar(escritor)
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()


def pdf_com_javascript() -> bytes:
    def abrir_com_javascript(escritor: PdfWriter) -> None:
        acao = {
            "/S": NameObject("/JavaScript"),
            "/JS": TextStringObject("app.alert(1);"),
        }
        escritor.add_open_action(
            DictionaryObject({NameObject(nome): valor for nome, valor in acao.items()})
        )

    return _pelo_pypdf(abrir_com_javascript)


def pdf_cifrado(senha_para_abrir: str = "senha") -> bytes:
    """Cifrado; com `senha_para_abrir=""`, abre sem pedir senha (só a do dono restringe)."""
    return _pelo_pypdf(
        lambda escritor: escritor.encrypt(senha_para_abrir, owner_password="dono")
    )


def pdf_com_anexo() -> bytes:
    return _pelo_pypdf(lambda escritor: escritor.add_attachment("a.exe", b"MZ\x90\x00"))


def _pdf_cru(*objetos: bytes) -> bytes:
    """Um PDF montado à mão (sem tabela xref válida): só para a conferência por fora."""
    corpo = b"%PDF-1.7\n"
    for numero, objeto in enumerate(objetos, start=1):
        corpo += b"%d 0 obj\n" % numero + objeto + b"\nendobj\n"
    return corpo + b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"


def pdf_com_javascript_escondido_num_fluxo() -> bytes:
    """O `/JavaScript` dentro de um fluxo comprimido (como num `/ObjStm`): só aparece descomprimido."""
    escondido = zlib.compress(b"5 0 << /S /JavaScript /JS (app.alert(1)) >>")
    fluxo = (
        b"<< /Type /ObjStm /N 1 /First 4 /Filter /FlateDecode /Length %d >>\nstream\n"
        % len(escondido)
    )
    return _pdf_cru(b"<< /Type /Catalog >>", fluxo + escondido + b"\nendstream")


def pdf_com_nome_escapado() -> bytes:
    """`/J#61vaScript` é `/JavaScript` escrito com escape hexadecimal (vale pela especificação)."""
    return _pdf_cru(b"<< /Type /Catalog /OpenAction << /S /J#61vaScript /JS (x) >> >>")


def pdf_com_paginas(quantas: int) -> bytes:
    return pdf(*(str(numero) for numero in range(quantas)))


def _zip(entradas: dict[str, bytes], metodo: int = zipfile.ZIP_DEFLATED) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", metodo) as arquivo:
        for nome, conteudo in entradas.items():
            arquivo.writestr(nome, conteudo)
    return saida.getvalue()


def xlsx(*linhas: tuple) -> bytes:
    """Uma planilha de verdade (openpyxl), uma aba."""
    import openpyxl

    livro = openpyxl.Workbook()
    for linha in linhas:
        livro.worksheets[0].append(list(linha))
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()


def xlsx_mexido(
    acrescentar: dict[str, bytes] | None = None, tipos: str | None = None
) -> bytes:
    """Uma planilha de verdade com entradas a mais ou outro `[Content_Types].xml`."""
    with zipfile.ZipFile(io.BytesIO(xlsx(("a", 1)))) as original:
        entradas = {nome: original.read(nome) for nome in original.namelist()}
    if tipos is not None:
        entradas["[Content_Types].xml"] = tipos.encode()
    entradas.update(acrescentar or {})
    return _zip(entradas)


def xlsx_com_macro() -> bytes:
    return xlsx_mexido({"xl/vbaProject.bin": b"\xd0\xcf\x11\xe0 macro"})


def xlsx_que_se_diz_com_macro() -> bytes:
    tipos = _TIPOS_DO_XLSX.replace(
        "spreadsheetml.sheet.main+xml", "spreadsheetml.sheet.macroEnabled.main+xml"
    )
    return xlsx_mexido(tipos=tipos)


def zip_bomba() -> bytes:
    """Poucos KB que dizem ter 20 MB descomprimidos (razão bem acima de 100:1)."""
    return _zip(
        {
            "[Content_Types].xml": _TIPOS_DO_XLSX.encode(),
            "xl/workbook.xml": b"<workbook/>",
            "xl/zeros.xml": b"\x00" * (20 * 1024 * 1024),
        }
    )


def zip_com_entradas_demais(quantas: int) -> bytes:
    entradas = {f"xl/{numero}.xml": b"" for numero in range(quantas)}
    entradas["[Content_Types].xml"] = _TIPOS_DO_XLSX.encode()
    entradas["xl/workbook.xml"] = b"<workbook/>"
    return _zip(entradas, zipfile.ZIP_STORED)


def zip_com_caminho(nome: str) -> bytes:
    return xlsx_mexido({nome: b"x"})


def zip_com_senha() -> bytes:
    """Uma entrada marcada como cifrada (o bit 0 dos flags, no cabeçalho local e no índice).

    O `zipfile` não grava ZIP cifrado: o bit é posto à mão nos bytes depois.
    """
    conteudo = bytearray(
        _zip(
            {
                "[Content_Types].xml": _TIPOS_DO_XLSX.encode(),
                "xl/workbook.xml": b"<workbook/>",
                "xl/secreto.xml": b"cifrado",
            }
        )
    )
    for assinatura, posicao_dos_flags in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        inicio = conteudo.find(assinatura)
        while inicio >= 0:
            conteudo[inicio + posicao_dos_flags] |= 0x1
            inicio = conteudo.find(assinatura, inicio + 1)
    return bytes(conteudo)


def zip_sem_office() -> bytes:
    return _zip({"leia.txt": b"so um zip"})


def docx(*paginas: list[str]) -> bytes:
    """Um DOCX mínimo: cada página é uma lista de parágrafos, separadas por quebra manual."""
    corpo = []
    for numero, paragrafos in enumerate(paginas):
        if numero:
            corpo.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        corpo.extend(
            f"<w:p><w:r><w:t>{texto}</w:t></w:r></w:p>" for texto in paragrafos
        )
    documento = (
        f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{_NS_DO_WORD}">'
        f"<w:body>{''.join(corpo)}</w:body></w:document>"
    )
    return _zip(
        {
            "[Content_Types].xml": _TIPOS_DO_DOCX.encode(),
            "word/document.xml": documento.encode(),
        }
    )


def docx_com_entidade_externa() -> bytes:
    """Um DOCX com XXE (entidade que lê um arquivo do servidor): o defusedxml recusa."""
    documento = (
        '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        f'<w:document xmlns:w="{_NS_DO_WORD}"><w:body><w:p><w:r><w:t>&x;</w:t></w:r></w:p>'
        "</w:body></w:document>"
    )
    return _zip(
        {
            "[Content_Types].xml": _TIPOS_DO_DOCX.encode(),
            "word/document.xml": documento.encode(),
        }
    )


OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 504  # um .xls ou .doc antigo
