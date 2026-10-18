"""PDF do relatório completo de empresa (série 2 da base de ML, PR 7): as mesmas seções e números da
página (a mesma estrutura de `src/relatorio_empresa.py`), com "Limites e perguntas em aberto" e os gráficos."""

from io import BytesIO

from pypdf import PdfReader

from src import relatorio_empresa as re_
from src.relatorio_empresa_pdf import relatorio_da_empresa
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
