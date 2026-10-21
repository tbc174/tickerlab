"""PDF do relatório completo de empresa (série 2 da base de ML, PR 7): as mesmas seções e números da
página (a mesma estrutura de `src/relatorio_empresa.py`), com "Limites e perguntas em aberto" e os gráficos."""

from datetime import date
from io import BytesIO

from pypdf import PdfReader

from src import relatorio_empresa as re_
from src.relatorio_empresa_pdf import TITULO_DO_ANEXO, relatorio_da_empresa
from tests.test_relatorio_empresa import _entradas, dados_da_weg  # noqa: F401


def _texto(pdf: bytes) -> str:
    return " ".join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)


def _sem_espacos(texto: str) -> str:
    return "".join(texto.split())


def test_pdf_tem_as_mesmas_secoes_e_numeros_da_pagina(dados_da_weg):  # noqa: F811
    relatorio = re_.montar(_entradas(dados_da_weg))
    pdf = relatorio_da_empresa(relatorio)
    assert pdf.startswith(b"%PDF")
    texto = _sem_espacos(_texto(pdf))
    for secao in relatorio.secoes:
        assert _sem_espacos(secao.titulo) in texto, secao.titulo
    receita = next(
        i for i in relatorio.secao("resultado").itens if i.chave == "receita"
    )
    assert _sem_espacos(receita.texto) in texto


def test_pdf_tem_limites_e_cuidados(dados_da_weg):  # noqa: F811
    relatorio = re_.montar(_entradas(dados_da_weg))
    texto = _sem_espacos(_texto(relatorio_da_empresa(relatorio)))
    assert _sem_espacos(re_.SECOES["limites"]) in texto
    assert _sem_espacos("não é recomendação") in texto


def _links(pdf: bytes) -> list[str]:
    return [
        anotacao.get_object()["/A"]["/URI"]
        for pagina in PdfReader(BytesIO(pdf)).pages
        for anotacao in pagina.get("/Annots", [])
        if "/URI" in anotacao.get_object().get("/A", {})
    ]


def test_pdf_fecha_com_o_anexo_de_como_cada_numero_foi_calculado(dados_da_weg):  # noqa: F811
    """Item 7 do lançamento: no papel, o rastro de cada número e o link de cada documento."""
    relatorio = re_.montar(_entradas(dados_da_weg))
    pdf = relatorio_da_empresa(relatorio)
    texto = _sem_espacos(_texto(pdf))
    assert _sem_espacos(TITULO_DO_ANEXO) in texto
    margem = next(
        i for s in relatorio.secoes for i in s.itens if i.chave == "margem_ebit"
    )
    assert margem.rastro is not None
    assert _sem_espacos(margem.rastro.formula) in texto
    assert _sem_espacos(margem.rastro.versao_do_calculo) in texto
    urls = {d.url for d in margem.rastro.documentos if d.url}
    assert urls and urls <= set(_links(pdf))  # o documento original, clicável


def test_pdf_sem_rastro_nao_tem_o_anexo(dados_da_weg):  # noqa: F811
    relatorio = re_.montar(_entradas(dados_da_weg))
    texto = _sem_espacos(_texto(relatorio_da_empresa(relatorio, com_rastro=False)))
    assert _sem_espacos(TITULO_DO_ANEXO) not in texto


def test_amostra_publica_leva_o_anexo_quando_a_ficha_tem_rastro():
    """O PDF da amostra do site mostra como cada número foi calculado ("pode" do Tiago, 21/10). A
    ficha congelada da CPFL é de antes do rastro: aqui ela ganha o rastro de um item."""
    from src import amostra_do_relatorio, dossie

    ficha = dossie.ler_ficha(dossie.FICHA_DE_EXEMPLO)
    assert ficha is not None
    item = next(i for s in ficha.secoes for i in s.itens if i.valor is not None)
    item.rastro = dossie.RastroDaFicha(
        formula="soma das linhas da tabela de teste",
        versao_do_calculo="1",
        fonte_id="cvm",
        publicado_em=date(2026, 5, 14),
    )
    pdf = amostra_do_relatorio.pdf(amostra_do_relatorio.montar(ficha))
    texto = _sem_espacos(_texto(pdf))
    assert _sem_espacos(TITULO_DO_ANEXO) in texto
    assert _sem_espacos("soma das linhas da tabela de teste") in texto
    assert _sem_espacos("14/05/2026") in texto


PASSOS = [("Receita", 10e9), ("Custo", -6e9), ("Outras", -2.5e9), ("Lucro", 1.5e9)]


def test_grafico_de_cascata_da_tela_marca_o_total():
    from src.graficos import criar_grafico_cascata

    figura = criar_grafico_cascata(PASSOS, "Da receita ao lucro")
    barras = figura.data[0]
    assert list(barras.measure) == ["absolute", "relative", "relative", "total"]
    assert list(barras.y) == [10.0, -6.0, -2.5, 1.5]  # em bilhões


def test_grafico_de_cascata_do_pdf_e_png():
    from src.graficos_pdf import grafico_de_cascata

    assert grafico_de_cascata(PASSOS, "Da receita ao lucro").startswith(b"\x89PNG")


def test_pdf_cita_a_fonte_restrita_e_a_frase_da_iex(dados_da_weg):  # noqa: F811
    from dataclasses import replace

    from src.banco.coletas import FRASE_DA_IEX, citacoes_das_fontes

    relatorio = re_.montar(_entradas(dados_da_weg))
    texto = _sem_espacos(_texto(relatorio_da_empresa(relatorio)))
    assert _sem_espacos("Yahoo Finance") in texto
    com_iex = replace(
        relatorio, fontes=(*relatorio.fontes, *citacoes_das_fontes(["iex"]))
    )
    texto = _sem_espacos(_texto(relatorio_da_empresa(com_iex)))
    assert _sem_espacos(FRASE_DA_IEX[:40]) in texto
