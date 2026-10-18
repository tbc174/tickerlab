"""Plano B leve do leitor (18/10/2026): formato do documento, porta de legibilidade e OCR de
reserva quando o PDF volta vazio ou embaralhado. Sem internet: os modelos do RapidOCR vêm dentro
do pacote; os testes de lógica usam um OCR de mentira."""

import io

import pytest
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont

from src import leitura
from tests.test_leitura import FATO, _pdf

EMBARALHADO = (
    "&RPSDQKLD $EHUWD &13- Q 5HODo}HV FRP ,QYHVWLGRUHV )DWR 5HOHYDQWH D &RPSDQKLD "
    "FRPXQLFD DRV VHXV DFLRQLVWDV H DR PHUFDGR HP JHUDO TXH R &RQVHOKR DSURYRX"
)
OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100


def _pdf_so_imagem(texto: str) -> bytes:
    """Um PDF escaneado de mentira: a página é uma imagem com o texto desenhado, sem camada de texto."""
    imagem = Image.new("RGB", (1240, 600), "white")
    desenho = ImageDraw.Draw(imagem)
    fonte = ImageFont.load_default(size=28)
    for i, linha in enumerate(texto.splitlines()):
        desenho.text((60, 60 + i * 44), linha, fill="black", font=fonte)
    pdf = FPDF(unit="pt", format=(1240, 600))
    pdf.add_page()
    pdf.image(imagem, x=0, y=0, w=1240, h=600)
    return bytes(pdf.output())


def _ocr_de_mentira(texto: str):
    chamadas: list[int] = []

    def ocr(conteudo: bytes, max_paginas: int) -> str:
        chamadas.append(max_paginas)
        return texto

    return ocr, chamadas


# --- formato do documento --------------------------------------------------------------------
@pytest.mark.parametrize(
    ("conteudo", "formato"),
    [
        (_pdf("Um PDF inteiro."), leitura.PDF),
        (_pdf("cortado")[:200], leitura.PDF_CORTADO),
        (b"<html><body>Limite de downloads atingido</body></html>", leitura.HTML),
        (b"\n  <!DOCTYPE html><html>", leitura.HTML),
        (OLE, leitura.WORD),
        (b"PK\x03\x04" + b"\x00" * 50, leitura.ZIP),
        (b"\x00\x01\x02 nada", leitura.DESCONHECIDO),
    ],
)
def test_formato_do_documento(conteudo, formato):
    assert leitura.formato_do_documento(conteudo) == formato


def test_so_a_pagina_de_aviso_e_o_pdf_cortado_param_a_fila():
    assert leitura.parece_limite_da_cvm(leitura.HTML)
    assert leitura.parece_limite_da_cvm(leitura.PDF_CORTADO)
    assert not leitura.parece_limite_da_cvm(
        leitura.WORD
    )  # um .doc antigo não é o limite
    assert not leitura.parece_limite_da_cvm(leitura.ZIP)
    assert not leitura.parece_limite_da_cvm(leitura.DESCONHECIDO)


# --- porta de legibilidade -------------------------------------------------------------------
def test_texto_de_verdade_tem_palavras_comuns():
    assert (
        leitura.taxa_de_palavras_comuns(FATO) >= leitura.TAXA_MINIMA_DE_PALAVRAS_COMUNS
    )
    assert leitura.e_legivel(FATO)
    assert not leitura.esta_embaralhado(FATO)


def test_fonte_embaralhada_e_pega_pela_taxa():
    assert (
        leitura.taxa_de_palavras_comuns(EMBARALHADO)
        < leitura.TAXA_MINIMA_DE_PALAVRAS_COMUNS
    )
    assert leitura.esta_embaralhado(EMBARALHADO)
    assert not leitura.e_legivel(EMBARALHADO * 5)  # nem com muitas "palavras"


def test_texto_curto_nao_e_legivel_nem_embaralhado():
    assert not leitura.e_legivel("Comunicado curto, mas de verdade.")
    assert not leitura.esta_embaralhado("&RPS")  # poucas palavras: não dá para julgar
    assert leitura.taxa_de_palavras_comuns("") == 0.0


# --- ler_documento ----------------------------------------------------------------------------
def test_pdf_com_texto_nao_passa_pelo_ocr():
    def ocr_proibido(conteudo: bytes, max_paginas: int) -> str:
        raise AssertionError("o OCR não devia rodar")

    lido = leitura.ler_documento(_pdf(FATO), ocr=ocr_proibido)
    assert lido.legivel and lido.origem == leitura.TEXTO
    assert "aquisição" in lido.texto and lido.paginas == 1 and lido.paginas_por_ocr == 0
    assert lido.texto == leitura.texto_do_pdf(_pdf(FATO))  # o mesmo texto de antes


def test_pdf_so_imagem_vai_para_o_ocr_com_o_teto_de_paginas():
    ocr, chamadas = _ocr_de_mentira(FATO)
    lido = leitura.ler_documento(_pdf_so_imagem("x"), ocr=ocr)
    assert chamadas == [leitura.MAX_PAGINAS_OCR]
    assert lido.legivel and lido.origem == leitura.OCR
    assert lido.texto == FATO and lido.paginas_por_ocr == 1


def test_fonte_embaralhada_vai_para_o_ocr():
    ocr, chamadas = _ocr_de_mentira(FATO)
    lido = leitura.ler_documento(_pdf(EMBARALHADO), ocr=ocr)
    assert chamadas and lido.origem == leitura.OCR and lido.texto == FATO


def test_lixo_do_ocr_nao_vira_texto():
    """ADR 0069: o OCR de uma página de jornal rende lixo; a porta segura e fica o motivo."""
    ocr, _ = _ocr_de_mentira(EMBARALHADO * 10)
    lido = leitura.ler_documento(_pdf_so_imagem("x"), ocr=ocr)
    assert not lido.legivel and lido.texto == "" and lido.origem == ""
    assert (
        "só imagem" in lido.motivo and "não leu texto que faça sentido" in lido.motivo
    )
    assert lido.paginas_por_ocr == 1


def test_motivo_diz_que_a_fonte_estava_embaralhada():
    ocr, _ = _ocr_de_mentira("")
    lido = leitura.ler_documento(_pdf(EMBARALHADO), ocr=ocr)
    assert lido.motivo and "embaralhada" in lido.motivo


def test_sem_o_ocr_instalado_fica_o_motivo():
    def sem_pacote(conteudo: bytes, max_paginas: int) -> str:
        raise ImportError("rapidocr")

    lido = leitura.ler_documento(_pdf_so_imagem("x"), ocr=sem_pacote)
    assert not lido.legivel and "não está instalado" in lido.motivo


def test_ocr_que_falha_nao_derruba_a_fila():
    def quebrado(conteudo: bytes, max_paginas: int) -> str:
        raise RuntimeError("modelo corrompido")

    lido = leitura.ler_documento(_pdf_so_imagem("x"), ocr=quebrado)
    assert not lido.legivel and "o OCR falhou" in lido.motivo


def test_documento_que_nao_e_pdf_fica_com_o_motivo():
    lido = leitura.ler_documento(OLE)
    assert not lido.legivel and lido.motivo == "O documento não é PDF (word): não lido."
    assert lido.paginas == 0


def test_pdf_malformado_fica_com_o_motivo():
    assert leitura.ler_documento(b"%PDF-1.4 lixo %%EOF").motivo == "PDF ilegível."


# --- o OCR de verdade (RapidOCR, modelos dentro do pacote) --------------------------------------
def test_ocr_de_verdade_le_um_pdf_escaneado():
    texto = "\n".join(
        [
            "FATO RELEVANTE",
            "A Companhia Exemplo comunica aos seus acionistas e ao mercado em geral",
            "que o Conselho de Administracao aprovou a recompra de acoes da Companhia",
            "e o pagamento de dividendos no valor de R$ 1,20 por acao, com base no",
            "lucro do exercicio. A operacao sera concluida em ate seis meses, depois",
            "da aprovacao dos acionistas em assembleia, nos termos da lei e do estatuto",
            "social da Companhia, que manteve o mercado informado sobre o andamento.",
            "A Companhia reafirma o compromisso com os seus acionistas e com o mercado.",
        ]
    )
    conteudo = _pdf_so_imagem(texto)
    assert leitura.texto_do_pdf(conteudo).strip() == ""  # sem camada de texto
    lido = leitura.ler_documento(conteudo)
    assert lido.legivel and lido.origem == leitura.OCR, lido.motivo
    assert "recompra" in lido.texto.lower() and "dividendos" in lido.texto.lower()


def test_texto_por_ocr_respeita_o_teto_de_paginas():
    pdf = FPDF()
    for _ in range(3):
        pdf.add_page()
    conteudo = bytes(pdf.output())
    assert leitura.numero_de_paginas(conteudo) == 3
    assert (
        leitura.texto_por_ocr(conteudo, max_paginas=1) == ""
    )  # páginas em branco: nada


def test_pdf_so_imagem_salva_em_arquivo_bytes():
    assert leitura.e_pdf(_pdf_so_imagem("x"))
    assert io.BytesIO(_pdf_so_imagem("x")).read(5) == b"%PDF-"
