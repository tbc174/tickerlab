"""Fonte clicável em cada número do setor e da ficha (linha 601 da fila)."""

import pytest

from src import relatorio_empresa as re_
from src.enderecos_das_fontes import (
    enderecos_da_fonte,
    fonte_com_endereco,
    paragrafo_com_endereco,
    separar,
)


def test_dfp_e_itr_levam_um_endereco_cada():
    pares = dict(enderecos_da_fonte(re_.FONTE_DAS_DEMONSTRACOES))
    assert pares["DFP"].startswith("https://dados.cvm.gov.br/")
    assert pares["ITR"].endswith("cia_aberta-doc-itr")


def test_a_aneel_e_o_formulario_de_referencia():
    texto = "ODbL (dados abertos da ANEEL, SAMP), pelo formulário de referência da CVM"
    rotulos = [r for r, _ in enderecos_da_fonte(texto)]
    assert rotulos == ["FRE", "ANEEL"]


def test_cvm_sozinha_vai_ao_portal_e_fonte_desconhecida_fica_igual():
    assert fonte_com_endereco("dados da CVM").endswith("https://dados.cvm.gov.br/")
    assert fonte_com_endereco("conta feita pelo app") == "conta feita pelo app"
    assert fonte_com_endereco("") == ""


def test_e_idempotente():
    uma_vez = fonte_com_endereco(re_.FONTE_DOS_TICKERS)
    assert fonte_com_endereco(uma_vez) == uma_vez


def test_o_paragrafo_de_fonte_mantem_o_ponto_e_os_outros_ficam_iguais():
    p = paragrafo_com_endereco(f"Fonte: {re_.FONTE_DOS_TICKERS}.")
    assert p.startswith("Fonte: FCA entregue") and "https://" in p
    assert p.endswith(".")
    assert paragrafo_com_endereco("Outro texto da CVM.") == "Outro texto da CVM."


def test_separar_devolve_o_texto_e_os_enderecos():
    texto, enderecos = separar(fonte_com_endereco(re_.FONTE_DAS_DEMONSTRACOES))
    assert texto == re_.FONTE_DAS_DEMONSTRACOES
    assert [r for r, _ in enderecos] == ["DFP", "ITR"]


@pytest.mark.parametrize("fonte", [re_.FONTE_DO_SETOR, re_.FONTE_DOS_MULTIPLOS])
def test_as_fontes_da_ficha_ganham_endereco(fonte):
    assert "https://" in fonte_com_endereco(fonte)
