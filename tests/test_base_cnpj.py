"""CNPJ com letras (IN RFB 2.229/2024; PR 2 da rede de entidades, ADR 0077).

Regra do dígito verificador pela FAQ da Receita ("CNPJ alfanumérico", pergunta 14) e pelo documento do
Serpro: cada caractere vale o código ASCII − 48, pesos e resto por 11 como no CNPJ só com números.
"""

from hypothesis import given
from hypothesis import strategies as st

from base import cnpj, fidc

EXEMPLO_DA_RECEITA = "12ABC34501DE35"


def test_exemplo_oficial_da_receita():
    assert cnpj.dv_confere(EXEMPLO_DA_RECEITA)
    assert not cnpj.dv_confere("12ABC34501DE36")


def test_dv_de_cnpj_conhecido_so_com_numeros():
    assert cnpj.dv_confere("33000167000101")  # Petrobras
    assert not cnpj.dv_confere("33000167000102")
    assert not cnpj.dv_confere("00000000000000")  # todos iguais, como no fidc
    assert not cnpj.dv_confere("123")


@given(st.text(alphabet="0123456789", min_size=14, max_size=14))
def test_numerico_continua_igual(digitos):
    assert cnpj.dv_confere(digitos) == fidc._cnpj_valido(digitos)


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
