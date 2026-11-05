"""Uma leitura por conjunto da API externa (B-32a): só pela porta da base, campo a campo pelo portão."""

from collections.abc import Callable
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
