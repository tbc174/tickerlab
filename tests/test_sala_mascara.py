"""O CPF no texto lido da sala sai mascarado (B-20, PR 2): só os dígitos verificadores ficam."""

from hypothesis import given
from hypothesis import strategies as st

from src.sala import mascara
from tests.ajudantes_da_sala import CPF_INVALIDO, CPF_VALIDO


def _verificador(digitos: list[int]) -> int:
    # conta independente da do módulo: peso decrescente a partir de len+1, resto 0 ou 1 vira 0
    soma = sum(
        d * p for d, p in zip(digitos, range(len(digitos) + 1, 1, -1), strict=True)
    )
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def _cpf(nove: list[int]) -> str:
    digitos = list(nove)
    digitos.append(_verificador(digitos))
    digitos.append(_verificador(digitos))
    return "".join(map(str, digitos))


def test_mascara_o_cpf_formatado_e_o_so_numeros():
    texto = f"Sócio: Fulano, CPF {CPF_VALIDO}; procurador CPF 52998224725."
    assert mascara.mascarar_cpfs(texto) == (
        "Sócio: Fulano, CPF ***.***.***-25; procurador CPF ***.***.***-25."
    )


def test_nao_mexe_no_que_nao_e_cpf():
    textos = [
        f"Número {CPF_INVALIDO} com verificador errado",
        "Receita de 1.234.567.890,12 no ano",  # valor com pontos
        "CNPJ 11.222.333/0001-81",
        "Conta 123456789012 (12 dígitos)",
        "Valor 52998224725,00 em reais",  # 11 dígitos seguidos de decimal
        "Telefone 11999998888",  # 11 dígitos que não fecham a conta do CPF
        "Todos iguais 111.111.111-11",
    ]
    for texto in textos:
        assert mascara.mascarar_cpfs(texto) == texto, texto


def test_cpf_valido_e_invalido():
    assert mascara.e_cpf_valido("52998224725")
    assert not mascara.e_cpf_valido("52998224726")
    assert not mascara.e_cpf_valido("00000000000")


@given(base=st.integers(0, 999_999_999), formatado=st.booleans())
def test_nenhum_cpf_valido_sobra_no_texto(base, formatado):
    numero = _cpf([int(d) for d in f"{base:09d}"])
    if len(set(numero)) == 1:
        return  # todos iguais: não é CPF (a Receita não emite)
    escrito = (
        f"{numero[:3]}.{numero[3:6]}.{numero[6:9]}-{numero[9:]}"
        if formatado
        else numero
    )
    mascarado = mascara.mascarar_cpfs(f"Sócio {escrito}, fim.")
    assert mascarado == f"Sócio ***.***.***-{numero[9:]}, fim."
    assert (
        mascara.mascarar_cpfs(mascarado) == mascarado
    )  # mascarar de novo não muda nada
