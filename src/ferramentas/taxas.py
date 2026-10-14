"""Juro real e taxa nominal (equação de Fisher).

Juro real é quanto o dinheiro rende além da inflação: (1 + nominal) / (1 + inflação) − 1. Não é a
subtração: 13,75% com 5% de inflação dão 8,33% reais, não 8,75%. Para trocar uma taxa de prazo
(mensal ↔ anual), use `juros.taxa_equivalente`.
"""


def _conferir(inflacao: float) -> None:
    if inflacao <= -1:
        raise ValueError("A inflação precisa ser maior que -100%.")


def juro_real(nominal: float, inflacao: float) -> float:
    """O rendimento acima da inflação no mesmo prazo das duas taxas."""
    _conferir(inflacao)
    if nominal <= -1:
        raise ValueError("A taxa precisa ser maior que -100%.")
    return (1 + nominal) / (1 + inflacao) - 1


def taxa_nominal(real: float, inflacao: float) -> float:
    """A taxa que rende `real` acima de uma `inflacao` (o caminho inverso do juro real)."""
    _conferir(inflacao)
    if real <= -1:
        raise ValueError("O juro real precisa ser maior que -100%.")
    return (1 + real) * (1 + inflacao) - 1
