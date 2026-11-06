"""Que arquivos entram na sala de dados (B-20, PR 2): o tipo pelo conteúdo e os maliciosos fora.

Todo arquivo malicioso é gerado aqui (`ajudantes_da_sala`), sem internet, e só na hora do teste
(cada caso guarda a função que gera, não os bytes). O que esta conferência não vê por fora
(JavaScript que só o PDFium acha, por exemplo) é conferido de novo na leitura
(`test_sala_leitura.py`).
"""

import pytest

from src.sala import arquivos
from tests import ajudantes_da_sala as gerar


def _motivo(conteudo: bytes, nome: str) -> str:
    with pytest.raises(arquivos.ArquivoRecusado) as recusa:
        arquivos.conferir(conteudo, nome)
    assert recusa.value.motivo in arquivos.MOTIVOS_DE_RECUSA
    return recusa.value.motivo


def _caso(id_, gerador, *resto):
    return pytest.param(gerador, *resto, id=id_)


@pytest.mark.parametrize(
    ("gerador", "nome", "tipo"),
    [
        _caso("pdf", lambda: gerar.pdf("um", "dois"), "balanco.pdf", "pdf"),
        _caso("xlsx", lambda: gerar.xlsx(("receita", 100)), "Planilha.XLSX", "xlsx"),
        _caso("docx", lambda: gerar.docx(["contrato"]), "contrato.docx", "docx"),
        _caso("csv-utf8", lambda: "a;b\n1;ação\n".encode(), "dados.csv", "csv"),
        # o Excel em português salva CSV em cp1252
        _caso(
            "csv-cp1252", lambda: "a;b\n1;ação\n".encode("cp1252"), "dados.csv", "csv"
        ),
        _caso(
            "pasta-windows",
            lambda: gerar.pdf("x"),
            r"C:\Users\f\Desktop\laudo.pdf",
            "pdf",
        ),
    ],
)
def test_aceita_os_quatro_tipos_pelo_conteudo(gerador, nome, tipo):
    assert arquivos.conferir(gerador(), nome) == tipo


@pytest.mark.parametrize(
    ("gerador", "nome", "motivo"),
    [
        _caso("vazio", lambda: b"", "vazio.pdf", arquivos.VAZIO),
        _caso(
            "25mb-mais-1",
            lambda: b"%PDF-" + b"0" * arquivos.TAMANHO_MAXIMO_DO_ARQUIVO,
            "g.pdf",
            arquivos.GRANDE_DEMAIS,
        ),
        _caso(
            "pdf-que-e-zip",
            lambda: gerar.xlsx(("a", 1)),
            "p.pdf",
            arquivos.EXTENSAO_NAO_BATE,
        ),
        _caso(
            "csv-que-e-pdf", lambda: gerar.pdf("x"), "l.csv", arquivos.EXTENSAO_NAO_BATE
        ),
        _caso(
            "sem-extensao", lambda: gerar.pdf("x"), "laudo", arquivos.EXTENSAO_NAO_BATE
        ),
        _caso(
            "xlsm", lambda: gerar.xlsx(("a", 1)), "planilha.xlsm", arquivos.COM_MACRO
        ),
        _caso("docm", lambda: gerar.docx(["x"]), "modelo.docm", arquivos.COM_MACRO),
        _caso("ole-antigo", lambda: gerar.OLE, "antigo.xls", arquivos.TIPO_NAO_ACEITO),
        _caso(
            "exe", lambda: b"MZ\x90\x00prog", "programa.exe", arquivos.TIPO_NAO_ACEITO
        ),
        _caso(
            "html", lambda: b"<script>x</script>", "p.html", arquivos.TIPO_NAO_ACEITO
        ),
        _caso(
            "zip-comum", gerar.zip_sem_office, "pacote.xlsx", arquivos.TIPO_NAO_ACEITO
        ),
        _caso("csv-binario", lambda: b"a;b\x00\x01;c", "b.csv", arquivos.CSV_BINARIO),
        _caso(
            "zip-quebrado",
            lambda: b"PK\x03\x04 nao e zip",
            "q.xlsx",
            arquivos.ARQUIVO_DANIFICADO,
        ),
    ],
)
def test_recusa_pelo_tipo_e_pelo_tamanho(gerador, nome, motivo):
    assert _motivo(gerador(), nome) == motivo


def test_o_limite_de_tamanho_aceita_ate_25_mb_exatos():
    preenchimento = b"\n" * (arquivos.TAMANHO_MAXIMO_DO_ARQUIVO - len(gerar.pdf("x")))
    assert arquivos.conferir(gerar.pdf("x") + preenchimento, "a.pdf") == "pdf"


# --- PDF ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("gerador", "motivo"),
    [
        _caso("javascript", gerar.pdf_com_javascript, arquivos.PDF_ATIVO),
        _caso(
            "js-num-fluxo",
            gerar.pdf_com_javascript_escondido_num_fluxo,
            arquivos.PDF_ATIVO,
        ),
        _caso("nome-escapado", gerar.pdf_com_nome_escapado, arquivos.PDF_ATIVO),
        _caso("anexo", gerar.pdf_com_anexo, arquivos.PDF_ATIVO),
        _caso("cifrado", gerar.pdf_cifrado, arquivos.PDF_CIFRADO),
        _caso(
            "301-paginas",
            lambda: gerar.pdf_com_paginas(arquivos.PAGINAS_MAXIMAS + 1),
            arquivos.PAGINAS_DEMAIS,
        ),
    ],
)
def test_recusa_pdf_que_age_sozinho_cifrado_ou_grande(gerador, motivo):
    assert _motivo(gerador(), "documento.pdf") == motivo


def test_aceita_pdf_com_o_maximo_de_paginas():
    assert (
        arquivos.conferir(gerar.pdf_com_paginas(arquivos.PAGINAS_MAXIMAS), "a.pdf")
        == "pdf"
    )


def test_a_palavra_javascript_no_texto_nao_e_nome_do_pdf():
    """Um balanço que fala de JavaScript no texto entra: só o nome `/JavaScript` é ação."""
    assert arquivos.conferir(gerar.pdf("Gastos com JavaScript e JS"), "a.pdf") == "pdf"


# --- XLSX e DOCX --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("gerador", "motivo"),
    [
        _caso("vbaProject", gerar.xlsx_com_macro, arquivos.COM_MACRO),
        _caso("macroEnabled", gerar.xlsx_que_se_diz_com_macro, arquivos.COM_MACRO),
        _caso(
            "activeX",
            lambda: gerar.xlsx_mexido({"xl/activeX/activeX1.xml": b"<ax/>"}),
            arquivos.COM_MACRO,
        ),
        _caso("zip-bomba", gerar.zip_bomba, arquivos.ZIP_GRANDE_DEMAIS),
        _caso(
            "entradas-demais",
            lambda: gerar.zip_com_entradas_demais(arquivos.ENTRADAS_MAXIMAS_NO_ZIP + 1),
            arquivos.ZIP_GRANDE_DEMAIS,
        ),
        _caso(
            "sobe-pasta",
            lambda: gerar.zip_com_caminho("../../etc/cron.d/x"),
            arquivos.ZIP_CAMINHO_ESTRANHO,
        ),
        _caso(
            "caminho-absoluto",
            lambda: gerar.zip_com_caminho("/etc/passwd"),
            arquivos.ZIP_CAMINHO_ESTRANHO,
        ),
        _caso(
            "drive-windows",
            lambda: gerar.zip_com_caminho("C:/Windows/x.dll"),
            arquivos.ZIP_CAMINHO_ESTRANHO,
        ),
        _caso(
            "barra-invertida",
            lambda: gerar.zip_com_caminho("xl\\..\\..\\x"),
            arquivos.ZIP_CAMINHO_ESTRANHO,
        ),
        _caso("com-senha", gerar.zip_com_senha, arquivos.ARQUIVO_DANIFICADO),
        _caso(
            "tamanho-declarado-menor",
            gerar.zip_que_declara_menos_do_que_tem,
            arquivos.ZIP_GRANDE_DEMAIS,
        ),
        _caso(
            "tamanho-declarado-menor-e-pequeno",
            lambda: gerar.zip_que_declara_menos_do_que_tem(real=500),
            arquivos.ZIP_GRANDE_DEMAIS,
        ),
        _caso("ole-no-xlsx", gerar.xlsx_com_ole, arquivos.OBJETO_EMBUTIDO),
    ],
)
def test_recusa_office_com_macro_bomba_ou_caminho_estranho(gerador, motivo):
    assert _motivo(gerador(), "planilha.xlsx") == motivo


def test_docx_nao_passa_por_xlsx_nem_o_contrario():
    assert _motivo(gerar.docx(["x"]), "a.xlsx") == arquivos.EXTENSAO_NAO_BATE
    assert _motivo(gerar.xlsx(("a", 1)), "a.docx") == arquivos.EXTENSAO_NAO_BATE


def test_todo_motivo_tem_codigo_curto_sem_espaco():
    """O código vai para a auditoria e para a tela: nunca texto livre."""
    assert len(set(arquivos.MOTIVOS_DE_RECUSA)) == len(arquivos.MOTIVOS_DE_RECUSA)
    for motivo in arquivos.MOTIVOS_DE_RECUSA:
        assert motivo.isascii() and " " not in motivo and len(motivo) <= 30


# --- objeto OLE embutido e tamanho real do ZIP --------------------------------------------


def test_docx_com_objeto_ole_embutido_e_recusado():
    assert _motivo(gerar.docx_com_ole(), "a.docx") == arquivos.OBJETO_EMBUTIDO


def test_docx_com_ole_ligado_a_arquivo_de_fora_e_recusado():
    conteudo = gerar.docx_com_ole_ligado_por_fora()
    assert _motivo(conteudo, "a.docx") == arquivos.OBJETO_EMBUTIDO


def test_docx_com_grafico_de_planilha_embutida_continua_aceito():
    """A planilha de um gráfico é `package`, não OLE: o que já entrava segue entrando."""
    assert arquivos.conferir(gerar.docx_com_grafico_de_planilha(), "a.docx") == "docx"


def test_zip_que_declara_o_tamanho_certo_continua_aceito():
    assert arquivos.conferir(gerar.xlsx(("a", 1), ("b", 2)), "a.xlsx") == "xlsx"
    assert arquivos.conferir(gerar.docx(["um"], ["dois"]), "a.docx") == "docx"


def test_o_tamanho_real_e_contado_sem_depender_do_sistema(monkeypatch):
    """Nada de `resource` (só existe no Linux): a conta é pelos bytes lidos de verdade."""
    monkeypatch.setattr(arquivos, "DESCOMPRIMIDO_MAXIMO", 1024)
    conteudo = gerar.zip_que_declara_menos_do_que_tem(real=5000)
    assert _motivo(conteudo, "a.xlsx") == arquivos.ZIP_GRANDE_DEMAIS
