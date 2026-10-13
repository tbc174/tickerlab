"""Foto de antes e depois dos relatórios em PDF: seções e números guardados não mudam sem querer.

A foto (`tests/arquivos/fotos_dos_relatorios.json`) tem, para cada relatório de exemplo, as seções
na ordem e os números de cada uma, como aparecem no PDF. Este teste gera os PDFs de novo e compara.
Mudou um relatório de propósito? Rode `python -m scripts.gerar_fotos_dos_relatorios` e explique no
PR (o diff do JSON mostra o que mudou).
"""

import json

import pytest

from scripts import gerar_fotos_dos_relatorios as fotos

REGRAVAR = (
    "rode python -m scripts.gerar_fotos_dos_relatorios se a mudança foi de propósito"
)


@pytest.fixture(scope="module")
def guardada() -> dict:
    return json.loads(fotos.DESTINO.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def agora() -> dict:
    return fotos.calcular()


def _primeira_diferenca(antes: list[str], depois: list[str]) -> str:
    for posicao, (a, d) in enumerate(zip(antes, depois, strict=False)):
        if a != d:
            return f"o {posicao + 1}º número era {a} e agora é {d}"
    return f"eram {len(antes)} números e agora são {len(depois)}"


def test_os_mesmos_relatorios_estao_na_foto(guardada, agora):
    assert set(agora) == set(guardada), REGRAVAR


def test_secoes_e_numeros_iguais_aos_da_foto(guardada, agora):
    diferencas = []
    for relatorio, antes in guardada.items():
        depois = agora.get(relatorio, {})
        if list(depois) != list(antes):
            diferencas.append(f"{relatorio}: as seções mudaram ({list(depois)})")
            continue
        diferencas += [
            f"{relatorio} / {secao}: {_primeira_diferenca(numeros, depois[secao])}"
            for secao, numeros in antes.items()
            if depois[secao] != numeros
        ]
    assert not diferencas, "\n".join([*diferencas, REGRAVAR])


def test_a_foto_acusa_um_numero_mudado(guardada):
    """O próprio teste funciona: trocar um número da seção de números é acusado com a posição."""
    secao = next(s for s in guardada["ativo PETR4.SA"] if s.endswith("Números-chave"))
    numeros = guardada["ativo PETR4.SA"][secao]
    mexido = ["+999,9%", *numeros[1:]]
    assert (
        _primeira_diferenca(numeros, mexido)
        == f"o 1º número era {numeros[0]} e agora é +999,9%"
    )
