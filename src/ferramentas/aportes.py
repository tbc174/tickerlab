"""Aportes e metas: quanto um valor inicial mais aportes mensais vira, e o caminho inverso.

Três perguntas: "quanto vou ter?" (`valor_futuro`), "quanto preciso guardar por mês?"
(`aporte_para_meta`) e "em quantos meses chego lá?" (`meses_ate_meta`). A taxa é ao mês, composta;
o aporte entra no fim do mês (padrão) ou no começo (`no_inicio`, rende um mês a mais).
"""

import math
from dataclasses import dataclass

from src.ferramentas.juros import PRAZO_MAXIMO

__all__ = [
    "PRAZO_MAXIMO",
    "Linha",
    "aporte_para_meta",
    "evolucao",
    "meses_ate_meta",
    "valor_futuro",
]


@dataclass(frozen=True)
class Linha:
    """Um mês: quanto saiu do bolso até ele (com o valor inicial), os juros e o saldo."""

    mes: int
    aportado: float
    juros: float
    saldo: float


def _conferir(inicial: float, aporte: float, taxa: float, meses: int) -> None:
    if inicial < 0:
        raise ValueError("O valor inicial não pode ser negativo.")
    if aporte < 0:
        raise ValueError("O aporte mensal não pode ser negativo.")
    if taxa <= -1:
        raise ValueError("A taxa precisa ser maior que -100%.")
    if meses < 0 or meses > PRAZO_MAXIMO:
        raise ValueError(f"O prazo precisa estar entre 0 e {PRAZO_MAXIMO} meses.")


def _fator_dos_aportes(taxa: float, meses: int, no_inicio: bool) -> float:
    """Quanto R$ 1 aportado por mês vira em `meses` meses."""
    if taxa == 0:
        return float(meses)
    # ((1 + taxa) ** meses - 1) / taxa, sem perder os dígitos quando a taxa é quase zero
    fator = math.expm1(meses * math.log1p(taxa)) / taxa
    return fator * (1 + taxa) if no_inicio else fator


def valor_futuro(
    inicial: float, aporte: float, taxa: float, meses: int, no_inicio: bool = False
) -> float:
    """O saldo depois de `meses` meses."""
    _conferir(inicial, aporte, taxa, meses)
    return inicial * (1 + taxa) ** meses + aporte * _fator_dos_aportes(
        taxa, meses, no_inicio
    )


def aporte_para_meta(
    meta: float, inicial: float, taxa: float, meses: int, no_inicio: bool = False
) -> float:
    """O aporte mensal para chegar a `meta` em `meses` meses (0 se o valor inicial já basta)."""
    _conferir(inicial, 0, taxa, meses)
    if meta < 0:
        raise ValueError("A meta não pode ser negativa.")
    if meses == 0:
        raise ValueError("O prazo precisa ser de pelo menos 1 mês.")
    falta = meta - inicial * (1 + taxa) ** meses
    return max(falta / _fator_dos_aportes(taxa, meses, no_inicio), 0.0)


def _proximo_saldo(saldo: float, aporte: float, taxa: float, no_inicio: bool) -> float:
    if no_inicio:
        return (saldo + aporte) * (1 + taxa)
    return saldo * (1 + taxa) + aporte


def meses_ate_meta(
    meta: float, inicial: float, aporte: float, taxa: float, no_inicio: bool = False
) -> int | None:
    """Quantos meses até o saldo chegar a `meta`; None se não chega em `PRAZO_MAXIMO` meses."""
    _conferir(inicial, aporte, taxa, 0)
    saldo = inicial
    for mes in range(PRAZO_MAXIMO + 1):
        if saldo >= meta:
            return mes
        saldo = _proximo_saldo(saldo, aporte, taxa, no_inicio)
    return None


def evolucao(
    inicial: float, aporte: float, taxa: float, meses: int, no_inicio: bool = False
) -> list[Linha]:
    """A tabela mês a mês, do mês 0 (só o valor inicial) ao último."""
    _conferir(inicial, aporte, taxa, meses)
    linhas = [Linha(mes=0, aportado=inicial, juros=0, saldo=inicial)]
    for mes in range(1, meses + 1):
        saldo = _proximo_saldo(linhas[-1].saldo, aporte, taxa, no_inicio)
        aportado = inicial + aporte * mes
        linhas.append(
            Linha(mes=mes, aportado=aportado, juros=saldo - aportado, saldo=saldo)
        )
    return linhas
