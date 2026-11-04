"""Os arquivos para levar do relatório de setor da página pública: o PDF e o deck (PDF e PPTX).

Saem do mesmo conteúdo da página (`relatorio_semanal.para_o_site`), então os números, as fontes e os
"Limites e cuidados" são os mesmos nos três. Quem escreve os arquivos no site é `scripts/gerar_site.py`.
"""

import zipfile
from datetime import datetime
from io import BytesIO

from src.apresentacao import do_relatorio_semanal
from src.apresentacao_pdf import apresentacao_em_pdf
from src.apresentacao_pptx import apresentacao_em_pptx
from src.estilos_pdf import PADRAO, Estilo
from src.relatorio_empresa_pdf import _titulo_da_tabela
from src.relatorio_pdf import RelatorioPDF

TITULO_DOS_DESTAQUES = "O que os dados mostram"
TITULO_DO_QUE_FALTA = "O que este relatório ainda não traz"
TITULO_DOS_LIMITES = "Limites e cuidados"


def relatorio_em_pdf(
    conteudo: dict, gerado_em: datetime, estilo: Estilo = PADRAO
) -> bytes:
    """O PDF do relatório de setor: aviso, destaques, tabelas, o que falta, fontes e limites."""
    pdf = RelatorioPDF(
        f"Relatório do setor: {conteudo['titulo']}",
        conteudo["setor"],
        gerado_em,
        estilo,
        conteudo["aviso"],
    )
    pdf.capa(
        [
            ("Setor", conteudo["titulo"]),
            ("Dados da base de", conteudo["dados_de"]),
            ("Gerado em", f"{gerado_em:%d/%m/%Y às %H:%M}"),
        ],
        [
            TITULO_DOS_DESTAQUES,
            *(t["titulo"] for t in conteudo["tabelas"]),
            TITULO_DO_QUE_FALTA,
            TITULO_DOS_LIMITES,
        ],
    )
    pdf.add_page()
    pdf.aviso_destacado(conteudo["aviso"])
    pdf.secao(TITULO_DOS_DESTAQUES, reservar=40, numerada=True)
    for destaque in conteudo["destaques"]:
        pdf.item(
            destaque["titulo"],
            destaque["texto"],
            nota=f"Fonte: {destaque['fonte']}; dado de {destaque['data']}.",
        )
    for tabela in conteudo["tabelas"]:
        _titulo_da_tabela(pdf, tabela["titulo"])
        pdf.tabela_de_texto(tabela["colunas"], tabela["linhas"])
    pdf.secao(TITULO_DO_QUE_FALTA, reservar=40, numerada=True)
    pdf.lista(
        [
            f"{f['kpi']}: {f['motivo']} Fonte: {f['fonte']}."
            for f in conteudo["nao_temos"]
        ]
    )
    pdf.secao(TITULO_DOS_LIMITES, reservar=40, numerada=True)
    pdf.lista(conteudo["limites"])
    return pdf.para_bytes()


def apresentacao_em_pdf_do_relatorio(conteudo: dict, gerado_em: datetime) -> bytes:
    """O deck do relatório de setor em PDF, um slide por página."""
    return apresentacao_em_pdf(do_relatorio_semanal(conteudo, gerado_em), gerado_em)


def apresentacao_em_pptx_do_relatorio(conteudo: dict, gerado_em: datetime) -> bytes:
    """O deck do relatório de setor em PowerPoint, com os mesmos slides do PDF."""
    bruto = apresentacao_em_pptx(do_relatorio_semanal(conteudo, gerado_em), gerado_em)
    return _zip_com_data_fixa(bruto, gerado_em)


def _zip_com_data_fixa(conteudo: bytes, momento: datetime) -> bytes:
    """O mesmo .pptx com a data de cada arquivo do zip trocada pela do relatório: o python-pptx grava
    a hora da geração, e o arquivo do site não pode mudar a cada geração."""
    saida = BytesIO()
    with (
        zipfile.ZipFile(BytesIO(conteudo)) as origem,
        zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as destino,
    ):
        for entrada in origem.infolist():
            nova = zipfile.ZipInfo(entrada.filename, momento.timetuple()[:6])
            nova.compress_type = zipfile.ZIP_DEFLATED
            destino.writestr(nova, origem.read(entrada.filename))
    return saida.getvalue()
