"""O CPF que vem no fim da razão social do MEI nunca sai (ADR 0106, regra 3.1; RIPD R16)."""

import re

import pandas as pd
from hypothesis import given
from hypothesis import strategies as st

from base.cnpj import cpf_confere
from base.pessoas.sem_cpf import tirar_cpf, tirar_cpf_da_coluna

ONZE_DIGITOS = re.compile(r"(?<!\d)\d{11}(?!\d)")


def _cpf_valido(base: str) -> str:
    """Completa 9 dígitos com os dois verificadores."""
    digitos = [int(d) for d in base]
    for peso_inicial in (10, 11):
        soma = sum(
            d * p for d, p in zip(digitos, range(peso_inicial, 1, -1), strict=False)
        )
        resto = soma * 10 % 11
        digitos.append(0 if resto == 10 else resto)
    return "".join(map(str, digitos))


def test_tira_o_cpf_do_fim_da_razao_social_do_mei():
    cpf = _cpf_valido("123456789")
    assert tirar_cpf(f"FULANO DE TAL {cpf}") == "FULANO DE TAL"


def test_tira_o_cpf_formatado_e_o_mascarado():
    assert tirar_cpf("FULANO 123.456.789-09") == "FULANO"
    assert tirar_cpf("FULANO ***.456.789-**") == "FULANO"


def test_nome_de_empresa_nao_muda():
    assert tirar_cpf("PETROBRAS S.A.") == "PETROBRAS S.A."
    assert tirar_cpf("LOJA 24 HORAS LTDA") == "LOJA 24 HORAS LTDA"


def test_onze_digitos_que_nao_sao_cpf_ficam():
    # o dígito verificador não fecha: pode ser outro número (e o nome não é dado pessoal)
    assert tirar_cpf("EMPRESA 12345678900") == "EMPRESA 12345678900"


def test_nao_confunde_cnpj_nem_valor():
    assert tirar_cpf("FILIAL 11222333000181") == "FILIAL 11222333000181"


def test_vazio_e_ausente_passam():
    assert tirar_cpf("") == ""
    assert tirar_cpf(None) is None
    coluna = tirar_cpf_da_coluna(pd.Series(["A 11144477735", None, "B"]))
    assert coluna.iloc[0] == "A" and coluna.iloc[2] == "B"
    assert pd.isna(coluna.iloc[1])


@given(
    nome=st.text(alphabet="ABCDEFGHIJ", min_size=3, max_size=12),
    base=st.integers(0, 999_999_999).map(lambda n: f"{n:09d}"),
    mascara=st.sampled_from(["{n} {c}", "{n}  {c}", "{c} {n}", "{n} {c} LTDA"]),
)
def test_nenhuma_saida_tem_cpf_valido(nome, base, mascara):
    cpf = _cpf_valido(base)
    if len(set(cpf)) == 1:  # 111.111.111-11 não é CPF
        return
    saida = tirar_cpf(mascara.format(n=nome, c=cpf))
    assert not any(cpf_confere(m) for m in ONZE_DIGITOS.findall(saida))
    assert nome in saida


def test_a_tela_do_dossie_tira_o_cpf():
    from src.dossie import _texto

    assert _texto(f"MEI DE FULANO {_cpf_valido('987654321')}") == "MEI DE FULANO"
