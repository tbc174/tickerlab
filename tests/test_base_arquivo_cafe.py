"""Fontes do balanço mundial do café no arquivista (PR 4): USDA PSD, FAOSTAT e ICO (a FNC saiu da coleta em 22/10/2026)."""

from datetime import UTC, datetime

import pytest

from base.arquivo import destinos, fontes
from base.arquivo.coleta import ErroDeDescoberta, Resposta
from src.banco import coletas

AGORA = datetime(2026, 10, 18, 5, tzinfo=UTC)
PAGINA_DA_ICO = b"""
<a href="http://www.ico.org/documents/cy2025-26/cmr-0826-e.pdf">Aug</a>
<a href="http://www.ico.org/documents/cy2025-26/cmr-0926-e.pdf">Sep</a>
<a href="http://www.ico.org/documents/cy2025-26/cmr-0926-e.pdf">Sep de novo</a>
<a href="http://www.ico.org/documents/cy2025-26/outro.pdf">Outro</a>
"""


class ClienteFalso:
    def __init__(self, conteudo: bytes):
        self.conteudo = conteudo
        self.pedidos: list[str] = []

    def ler(self, url, **_):
        self.pedidos.append(url)
        return Resposta(url, self.conteudo, {})


def test_as_fontes_do_cafe_tem_destino_certo():
    assert destinos.DESTINOS["usda-psd-cafe"].tipo == destinos.TABELA
    assert destinos.DESTINOS["usda-psd-cafe"].tabelas == ("usda_psd_cafe",)
    faostat = destinos.DESTINOS["faostat-cafe"]
    assert faostat.tipo == destinos.TABELA
    assert faostat.tabelas == ("faostat_cafe",)
    ico = destinos.DESTINOS["ico-relatorio-mensal"]
    assert (
        ico.tipo == destinos.PLANEJADA
    )  # coleta normal (ADR 0102); a tabela vem no PR 4
    assert "ICO" in ico.porque and "ADR 0102" in ico.porque


def test_psd_baixa_o_zip_completo_toda_semana():
    fonte = fontes.POR_ID["usda-psd-cafe"]
    assert fonte.grupo == "semanal"
    [alvo] = fonte.descobrir(None, AGORA)
    assert alvo.url.endswith("/psdonline/downloads/psd_coffee_csv.zip")
    assert fonte.tipo == "zip"


def test_faostat_e_pesada_e_pega_o_arquivo_de_producao():
    fonte = fontes.POR_ID["faostat-cafe"]
    assert fonte.pesada
    [alvo] = fonte.descobrir(None, AGORA)
    assert "Production_Crops_Livestock_E_All_Data_(Normalized).zip" in alvo.url


def test_ico_descobre_os_pdfs_do_relatorio_mensal_sem_repetir():
    fonte = fontes.POR_ID["ico-relatorio-mensal"]
    assert fonte.tipo == "pdf" and fonte.grupo == "mensal"
    alvos = fonte.descobrir(ClienteFalso(PAGINA_DA_ICO), AGORA)
    assert [a.url.rsplit("/", 1)[1] for a in alvos] == [
        "cmr-0826-e.pdf",
        "cmr-0926-e.pdf",
    ]


def test_ico_sem_nenhum_pdf_na_pagina_e_falha():
    with pytest.raises(ErroDeDescoberta):
        fontes.POR_ID["ico-relatorio-mensal"].descobrir(ClienteFalso(b"<html/>"), AGORA)


@pytest.mark.parametrize(
    ("fonte", "familia"),
    [
        ("usda-psd-cafe", "usda"),
        ("faostat-cafe", "faostat"),
        ("ico-relatorio-mensal", "ico"),
    ],
)
def test_licenca_e_revenda_estao_escritas(fonte, familia):
    assert coletas.licenca_da_fonte(fonte) != coletas.SEM_LICENCA_CONHECIDA
    assert coletas.revenda_da_fonte(fonte)
    assert coletas.LICENCAS[familia]


def test_ico_tem_a_marca_registrada_e_entra_em_todos_os_usos():
    """ADR 0102: a marca "não comercial" fica registrada e não barra coleta, tela nem modelo."""
    assert coletas.revenda_da_fonte("ico-relatorio-mensal") == coletas.NAO_COMERCIAL
    assert coletas.marca_da_fonte("ico-relatorio-mensal") == coletas.Marca.NAO_COMERCIAL
    assert all(coletas.pode_usar(uso, "ico-relatorio-mensal") for uso in coletas.USOS)
