"""Uma leitura por conjunto da API externa (B-32a): só pela porta da base, campo a campo pelo portão."""

from collections.abc import Callable
from datetime import date
from typing import Protocol

# o portão de um pedido: `permitido(fonte, campo, derivado)`; campo negado não aparece
Permitido = Callable[[str, str, bool], bool]


class Servido(Protocol):
    """O que uma leitura entrega à rota: o corpo, as fontes usadas (para a atribuição) e as linhas."""

    @property
    def corpo(self) -> dict: ...

    @property
    def fontes(self) -> set[str]: ...

    @property
    def linhas(self) -> int: ...


class AntesDaPrimeiraData(Exception):
    """O pedido não foi servido porque o dia é anterior ao primeiro dado da base. Leva o código do erro e o
    primeiro dia que funciona. Só se levanta depois de o portão liberar o pedido, para a recusa do contrato
    seguir com a mesma cara de `not_available`; a rota a responde como 400 com `first_known_at`."""

    def __init__(self, codigo: str, primeira: date) -> None:
        super().__init__(codigo)
        self.codigo = codigo
        self.primeira = primeira
