"""CNPJ com letras (IN RFB 2.229/2024; PR 2 da rede de entidades, ADR 0077).

Regra do dígito verificador pela FAQ da Receita ("CNPJ alfanumérico", pergunta 14) e pelo documento do
Serpro: cada caractere vale o código ASCII − 48, pesos e resto por 11 como no CNPJ só com números.
"""

import pandas as pd
from hypothesis import given
from hypothesis import strategies as st

from base import cnpj

EXEMPLO_DA_RECEITA = "12ABC34501DE35"


def test_exemplo_oficial_da_receita():
    assert cnpj.dv_confere(EXEMPLO_DA_RECEITA)
    assert not cnpj.dv_confere("12ABC34501DE36")


def test_dv_de_cnpj_conhecido_so_com_numeros():
    assert cnpj.dv_confere("33000167000101")  # Petrobras
    assert not cnpj.dv_confere("33000167000102")
    assert not cnpj.dv_confere("00000000000000")  # todos iguais, como no fidc
    assert not cnpj.dv_confere("123")


def _dv_so_com_numeros(digitos: str) -> bool:
    """O cálculo de antes da IN 2.229 (o que `base/fidc.py` usava), para comparar."""
    if digitos == digitos[0] * 14:
        return False

    def dv(base: str, pesos: list[int]) -> str:
        resto = sum(int(c) * k for c, k in zip(base, pesos, strict=True)) % 11
        return str(0 if resto < 2 else 11 - resto)

    pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    primeiro = dv(digitos[:12], pesos)
    segundo = dv(digitos[:12] + primeiro, [6, *pesos])
    return digitos[12:] == primeiro + segundo


@given(st.text(alphabet="0123456789", min_size=14, max_size=14))
def test_numerico_continua_igual(digitos):
    assert cnpj.dv_confere(digitos) == _dv_so_com_numeros(digitos)


def test_normalizar():
    assert cnpj.normalizar_cnpj("12.abc.345/01de-35") == EXEMPLO_DA_RECEITA
    assert cnpj.normalizar_cnpj("33.256.439/0001-39") == "33256439000139"
    assert cnpj.normalizar_cnpj("8884213000135.0") == "08884213000135"
    assert cnpj.normalizar_cnpj(8884213000135) == "08884213000135"
    assert (
        cnpj.normalizar_cnpj("03645752") == "00000003645752"
    )  # só a raiz, como o cnpj14
    assert cnpj.normalizar_cnpj("12ABC345") is None  # com letra, só os 14
    assert cnpj.normalizar_cnpj("12ABC34501DEA5") is None  # DV com letra
    assert cnpj.normalizar_cnpj("") is None
    assert cnpj.normalizar_cnpj("0.0") is None
    assert cnpj.normalizar_cnpj(None) is None
    assert cnpj.normalizar_cnpj(float("nan")) is None
    assert cnpj.normalizar_cnpj("123456789012345") is None  # 15 caracteres


def test_normalizar_nao_confere_o_dv():
    """Como o cnpj14 de hoje: a forma decide; quem quer o DV chama dv_confere (dado da fonte fica)."""
    assert cnpj.normalizar_cnpj("33000167000102") == "33000167000102"


def test_raiz():
    assert cnpj.raiz("12.ABC.345/01DE-35") == "12ABC345"
    assert cnpj.raiz("33.000.167/0001-01") == "33000167"
    assert cnpj.raiz("lixo") is None


def test_formatar():
    assert cnpj.formatar(EXEMPLO_DA_RECEITA) == "12.ABC.345/01DE-35"
    assert cnpj.formatar("33000167000101") == "33.000.167/0001-01"


def test_tem_letra():
    assert cnpj.tem_letra(EXEMPLO_DA_RECEITA)
    assert not cnpj.tem_letra("33000167000101")


def test_completo_nao_transforma_cpf_em_cnpj():
    """Coluna que mistura CPF e CNPJ: só os 14 contam (o CPF não ganha zeros e vira "CNPJ")."""
    assert cnpj.completo("12.abc.345/01de-35") == EXEMPLO_DA_RECEITA
    assert cnpj.completo("33.000.167/0001-01") == "33000167000101"
    assert cnpj.completo("123.456.789-09") is None
    assert cnpj.completo("03645752") is None
    assert cnpj.completo(None) is None


def test_raiz_em_numero_e_unica_e_aceita_letras():
    """Milhões de raízes num conjunto: 8 bytes cada (base 36), em vez de um texto do Python."""
    raizes = pd.Series(["00000000", "11222333", "12ABC345", "ZZZZZZZZ", "11222334"])
    numeros = cnpj.raizes_em_numeros(raizes)
    assert numeros.dtype == "int64"
    assert len(set(numeros.tolist())) == 5
    assert numeros[0] == 0
    assert numeros[3] == 36**8 - 1


def test_contem_pelos_numeros_ordenados():
    conjunto = cnpj.ordenados(
        cnpj.raizes_em_numeros(pd.Series(["11222333", "12ABC345"]))
    )
    procurados = cnpj.raizes_em_numeros(
        pd.Series(["12ABC345", "99999999", "11222333", "00000000"])
    )
    assert cnpj.contem(conjunto, procurados).tolist() == [True, False, True, False]
    vazio = cnpj.ordenados(cnpj.raizes_em_numeros(pd.Series([], dtype=str)))
    assert cnpj.contem(vazio, procurados).tolist() == [False] * 4


def test_raiz_em_numero_em_pedacos_da_o_mesmo(monkeypatch):
    """Milhões de raízes de uma vez criavam cópias de 64 bits de tudo (2,3 GB no servidor)."""
    raizes = pd.Series(
        [f"{n:08d}" for n in range(0, 99_999_999, 7_654_321)] + ["12ABC345"]
    )
    inteiro = cnpj.raizes_em_numeros(raizes)
    monkeypatch.setattr(cnpj, "RAIZES_POR_PEDACO", 3)
    pd.testing.assert_series_equal(
        pd.Series(cnpj.raizes_em_numeros(raizes)), pd.Series(inteiro)
    )
    assert cnpj.raizes_em_numeros(pd.Series(["00000123"]))[0] == 1 * 36**2 + 2 * 36 + 3
