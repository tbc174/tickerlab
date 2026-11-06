"""Filtro de pessoa jurídica das coletas de arquivo: CNPJ com letras (desde julho de 2026) fica."""

import pytest

from base import cnpj as cnpjs
from base.arquivo.obter_pj import e_pessoa_juridica, item_so_pj


def _cnpj_alfanumerico_valido(base: str = "12ABC34501DE") -> str:
    primeiro = cnpjs._digito(base, cnpjs.PESOS)
    segundo = cnpjs._digito(base + str(primeiro), (6, *cnpjs.PESOS))
    return f"{base}{primeiro}{segundo}"


def test_cnpj_alfanumerico_valido_passa_com_e_sem_mascara():
    puro = _cnpj_alfanumerico_valido()
    assert cnpjs.dv_confere(puro)
    mascarado = f"{puro[:2]}.{puro[2:5]}.{puro[5:8]}/{puro[8:12]}-{puro[12:]}"
    assert e_pessoa_juridica(puro)
    assert e_pessoa_juridica(mascarado)


@pytest.mark.parametrize(
    "valor",
    [
        "123.456.789-09",  # CPF com máscara
        "12345678909",  # CPF sem máscara
        "**.***.101/***-**",  # CNPJ mascarado
        "12ABC34501DE00",  # letras, mas dígito verificador errado
        "12ABC34501DE",  # 12 caracteres
    ],
)
def test_cpf_mascara_e_alfanumerico_invalido_ficam_de_fora(valor):
    assert not e_pessoa_juridica(valor)


def test_documento_em_branco_e_cnpj_de_14_digitos_continuam_passando():
    assert e_pessoa_juridica("")
    assert e_pessoa_juridica(None)
    assert e_pessoa_juridica("11.222.333/0001-81")


def test_item_da_api_com_cnpj_alfanumerico_nao_e_descartado():
    item = {"cnpjFornecedor": _cnpj_alfanumerico_valido(), "valor": 10}
    assert item_so_pj(item) == item
    assert item_so_pj({"cnpjFornecedor": "123.456.789-09", "valor": 10}) is None
