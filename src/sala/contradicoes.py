"""A regra das contradições entre documentos da sala (B-20, PR 4, D10).

Duas medidas se contradizem quando falam da mesma coisa (mesma métrica, período, unidade e
moeda) em documentos diferentes e os valores diferem mais que a tolerância. É regra fixa: nenhum
modelo decide. A regra é simétrica (trocar A por B dá a mesma resposta) e dentro da tolerância
nunca abre uma contradição.

A tolerância é a maior entre 0,5% do maior dos dois valores e 1 unidade: os 0,5% deixam passar
arredondamento de números grandes, e a unidade deixa passar arredondamento de números pequenos.
"""

import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations

TOLERANCIA_RELATIVA = Decimal("0.005")
TOLERANCIA_EM_UNIDADES = Decimal(1)

_ESPACOS = re.compile(r"\s+")


@dataclass(frozen=True)
class Medida:
    """O que uma evidência diz, só com o que a regra precisa."""

    evidencia_id: uuid.UUID
    documento_id: uuid.UUID
    metrica: str
    periodo: str
    valor: Decimal
    unidade: str | None
    moeda: str | None


def normalizar(texto: str | None) -> str:
    """Sem diferença de caixa nem de espaços; `None` e vazio são o mesmo."""
    return _ESPACOS.sub(" ", texto or "").strip().casefold()


def mesma_medida(a: Medida, b: Medida) -> bool:
    return (
        normalizar(a.metrica) == normalizar(b.metrica)
        and normalizar(a.periodo) == normalizar(b.periodo)
        and normalizar(a.unidade) == normalizar(b.unidade)
        and normalizar(a.moeda) == normalizar(b.moeda)
    )


def diferenca(a: Medida, b: Medida) -> Decimal:
    return abs(a.valor - b.valor)


def tolerancia(a: Medida, b: Medida) -> Decimal:
    maior = max(abs(a.valor), abs(b.valor))
    return max(TOLERANCIA_RELATIVA * maior, TOLERANCIA_EM_UNIDADES)


def se_contradizem(a: Medida, b: Medida) -> bool:
    return (
        a.documento_id != b.documento_id
        and mesma_medida(a, b)
        and diferenca(a, b) > tolerancia(a, b)
    )


def achar_contradicoes(
    medidas: list[Medida],
) -> list[tuple[Medida, Medida, Decimal]]:
    """Os pares que se contradizem, cada um uma vez, com a evidência de menor id primeiro."""
    ordenadas = sorted(medidas, key=lambda m: m.evidencia_id.hex)
    return [
        (a, b, diferenca(a, b))
        for a, b in combinations(ordenadas, 2)
        if se_contradizem(a, b)
    ]
