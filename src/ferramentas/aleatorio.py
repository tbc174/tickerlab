"""Gerador pseudoaleatório pequeno (mulberry32), igual ao de `web/src/ferramentas/contas/aleatorio.ts`.

O `random` do Python e o `Math.random` do navegador dão números diferentes; com o mesmo algoritmo
dos dois lados, a mesma semente dá as mesmas estratégias no site e aqui, e o golden confere. Não
serve para nada que precise de segurança: é só para simulações reproduzíveis.
"""

MASCARA = 0xFFFFFFFF  # as contas do mulberry32 são em inteiros de 32 bits
INCREMENTO = 0x6D2B79F5
ESCALA = 2**32


def _imul(a: int, b: int) -> int:
    """A multiplicação de 32 bits do `Math.imul` do JavaScript."""
    return (a * b) & MASCARA


class Gerador:
    """Números entre 0 (incluído) e 1 (excluído), sempre os mesmos para a mesma semente."""

    def __init__(self, semente: int) -> None:
        self._estado = semente & MASCARA

    def proximo(self) -> float:
        self._estado = (self._estado + INCREMENTO) & MASCARA
        a = self._estado
        t = _imul(a ^ (a >> 15), 1 | a)
        t = ((t + _imul(t ^ (t >> 7), 61 | t)) & MASCARA) ^ t
        return ((t ^ (t >> 14)) & MASCARA) / ESCALA


def sequencia(semente: int, quantidade: int) -> list[float]:
    """Os `quantidade` primeiros números da `semente` (o golden compara com o TypeScript)."""
    gerador = Gerador(semente)
    return [gerador.proximo() for _ in range(quantidade)]
