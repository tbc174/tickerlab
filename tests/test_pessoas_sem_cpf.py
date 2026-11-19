"""O CPF que vem no fim da razão social do MEI nunca sai (ADR 0106, regra 3.1; RIPD R16)."""

import re

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from base.cnpj import cpf_confere
from base.pessoas.sem_cpf import (
    tirar_cpf,
    tirar_cpf_da_coluna,
    tirar_numero_longo_e_email,
)
from tests.ajudantes_de_cpf import formatado

ONZE_DIGITOS = re.compile(r"(?<!\d)\d{11}(?!\d)")
NOVE_INVENTADOS = (
    "888000001"  # nove dígitos inventados; o CPF que confere sai de _cpf_valido
)


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
    cpf = _cpf_valido(NOVE_INVENTADOS)
    assert tirar_cpf(f"FULANO DE TAL {cpf}") == "FULANO DE TAL"


def test_tira_o_cpf_formatado_e_o_mascarado():
    assert tirar_cpf(f"FULANO {formatado(_cpf_valido(NOVE_INVENTADOS))}") == "FULANO"
    assert tirar_cpf("FULANO ***.000.001-**") == "FULANO"


def test_tira_o_cpf_com_espaco_em_volta_do_hifen():
    # achado na recarga de 11/11/2026: "... CPF: ddd.ddd.ddd - dd ..." passava pelo detector
    cpf = _cpf_valido(NOVE_INVENTADOS)
    pontuado = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]} - {cpf[9:]}"
    assert tirar_cpf(f"FULANO DE TAL {pontuado}") == "FULANO DE TAL"
    assert tirar_cpf(f"FULANO CPF: {pontuado} ME") == "FULANO ME"
    assert (
        tirar_cpf("FULANO CPF: 888.000.001 - 00 ME") == "FULANO ME"
    )  # com a palavra CPF sai sempre
    assert (
        tirar_cpf("FULANO 888 000 001 - 00") == "FULANO 888 000 001 - 00"
    )  # sem a palavra e sem fechar


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
    coluna = tirar_cpf_da_coluna(
        pd.Series([f"A {_cpf_valido('888000002')}", None, "B"])
    )
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

    assert _texto(f"MEI DE FULANO {_cpf_valido('888000003')}") == "MEI DE FULANO"


def test_tira_o_cpf_com_outros_separadores_e_colado_a_palavra_cpf():
    # revisão cruzada do PR 1019: só espaço, travessões, vírgula, barra e "CPF-"/"CPF/" colados ao número
    v = _cpf_valido(NOVE_INVENTADOS)
    g = (v[:3], v[3:6], v[6:9], v[9:])
    formas = [
        f"{g[0]} {g[1]} {g[2]} {g[3]}",
        f"{g[0]}.{g[1]}.{g[2]} {g[3]}",
        f"{v[:9]} {g[3]}",
        f"{g[0]}.{g[1]}.{g[2]}—{g[3]}",
        f"{g[0]}-{g[1]}-{g[2]}-{g[3]}",
        f"{g[0]},{g[1]},{g[2]}-{g[3]}",
        f"{g[0]}.{g[1]}.{g[2]}/{g[3]}",
        f"CPF-{g[0]}.{g[1]}.{g[2]} - {g[3]}",
        f"CPF/{g[0]}.{g[1]}.{g[2]}-{g[3]}",
    ]
    for forma in formas:
        limpo = tirar_cpf(f"FULANO {forma} ME")
        assert not re.search(r"\d{3}", limpo), forma


def test_cnpj_e_numero_que_nao_fecha_como_cpf_ficam():
    assert tirar_cpf("EMPRESA 11.222.333/0001-81 ME") == "EMPRESA 11.222.333/0001-81 ME"
    assert tirar_cpf("EMPRESA 888 000 001 00 ME") == "EMPRESA 888 000 001 00 ME"


@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        ("FULANA EXEMPLO 11222333", "FULANA EXEMPLO"),  # a raiz do CNPJ no fim
        ("11222333 FULANA EXEMPLO", "FULANA EXEMPLO"),
        ("FULANA EXEMPLO 01001-000", "FULANA EXEMPLO"),  # cara de CEP
        ("FULANA EXEMPLO 88800000-12", "FULANA EXEMPLO"),  # CPF com um dígito a menos
        (
            "FULANA 88800000 EXEMPLO 12",
            "FULANA EXEMPLO 12",
        ),  # dois dígitos soltos ficam
        ("FULANA EXEMPLO ME88800000", "FULANA EXEMPLO ME"),
        ("FULANA EXEMPLO fulana@exemplo.com.br", "FULANA EXEMPLO"),
        ("fulana9@exemplo.com", ""),
        ("LOJA 24 HORAS DE EXEMPLO 2023", "LOJA 24 HORAS DE EXEMPLO 2023"),
        ("", ""),
    ],
)
def test_numero_longo_e_email_saem_do_nome(nome, esperado):
    assert tirar_numero_longo_e_email(pd.Series([nome])).iloc[0] == esperado


@given(
    st.from_regex(
        r"[A-Z ]{0,12}[0-9 .\-/@*:_|\u200b·–]{0,20}[A-Z ]{0,12}", fullmatch=True
    )
)
def test_nome_limpo_nunca_tem_arroba_nem_cinco_digitos_seguidos(nome):
    limpo = tirar_numero_longo_e_email(pd.Series([nome])).iloc[0]
    assert "@" not in limpo
    assert not re.search(r"\d(?:(?:[^\w]|_)*\d){4}", limpo)


@pytest.mark.parametrize("separador", ["*", ":", "_", "|", "\u200b", "·", " ; "])
def test_cpf_com_separador_fora_do_comum_sai_do_nome(separador):
    cpf = _cpf_valido(NOVE_INVENTADOS)
    partido = separador.join((cpf[:3], cpf[3:6], cpf[6:9], cpf[9:]))
    limpo = tirar_numero_longo_e_email(pd.Series([f"FULANA {partido} EXEMPLO"])).iloc[0]
    assert limpo == "FULANA EXEMPLO"
