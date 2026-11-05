"""O número único do processo CNJ (`base/numero_cnj.py`)."""

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from base import numero_cnj

# ação civil pública contra a CPFL no TJSP (consultada no DataJud e no DJEN em 03/11/2026)
DA_CPFL = "1007218-33.2024.8.26.0451"


def test_decodifica_o_numero_com_mascara():
    numero = numero_cnj.decodificar(DA_CPFL)
    assert numero.ano == 2024
    assert numero.segmento == "8"
    assert numero.nome_do_segmento == "Justiça Estadual"
    assert numero.tribunal == "26"
    assert numero.origem == "0451"
    assert numero.formatado == DA_CPFL
    assert numero.algarismos == "10072183320248260451"


def test_decodifica_o_numero_sem_mascara():
    assert numero_cnj.decodificar("10072183320248260451").formatado == DA_CPFL


@pytest.mark.parametrize(
    "errado",
    [
        "1007218-34.2024.8.26.0451",  # dígito trocado
        "1007218-33.2024.0.26.0451",  # segmento 0 não existe
        "1007218-33.2024.8.26.045",  # falta um algarismo
        "",
    ],
)
def test_numero_que_nao_confere_e_recusado(errado: str):
    with pytest.raises(numero_cnj.NumeroInvalido):
        numero_cnj.decodificar(errado)
    assert not numero_cnj.confere(errado)


@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    sequencial=st.integers(0, 9_999_999),
    ano=st.integers(1900, 2099),
    segmento=st.sampled_from(sorted(numero_cnj.SEGMENTOS)),
    tribunal=st.integers(0, 99),
    origem=st.integers(0, 9999),
)
def test_numero_montado_com_o_digito_certo_volta_igual(
    sequencial: int, ano: int, segmento: str, tribunal: int, origem: int
):
    partes = (
        f"{sequencial:07d}",
        f"{ano:04d}",
        segmento,
        f"{tribunal:02d}",
        f"{origem:04d}",
    )
    digito = numero_cnj.digito_esperado(*partes)
    texto = f"{partes[0]}-{digito}.{partes[1]}.{partes[2]}.{partes[3]}.{partes[4]}"
    numero = numero_cnj.decodificar(texto)
    assert numero.formatado == texto
    assert numero.ano == ano
