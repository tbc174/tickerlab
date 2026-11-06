"""Aportes e metas: quanto um valor inicial mais aportes mensais vira, e o caminho inverso.

Três perguntas: "quanto vou ter?" (`valor_futuro`), "quanto preciso guardar por mês?"
(`aporte_para_meta`) e "em quantos meses chego lá?" (`meses_ate_meta`). A taxa é ao mês, composta;
o aporte entra no fim do mês (padrão) ou no começo (`no_inicio`, rende um mês a mais).

Com `reajuste_anual`, o aporte sobe essa fração a cada 12 meses (do 13º mês em diante, o do 2º ano;
e assim por diante), como quem reajusta o quanto guarda junto com o salário.
"""

import math
from dataclasses import dataclass
from itertools import pairwise

from src.ferramentas.juros import PRAZO_MAXIMO

__all__ = [
    "PRAZO_MAXIMO",
    "Linha",
    "aporte_para_meta",
    "evolucao",
    "mes_da_virada",
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


def aporte_do_mes(aporte: float, mes: int, reajuste_anual: float) -> float:
    """O aporte do `mes` (1, 2, ...): o primeiro, reajustado uma vez a cada 12 meses."""
    return aporte * (1 + reajuste_anual) ** ((mes - 1) // 12)


def _conferir_reajuste(reajuste_anual: float) -> None:
    if reajuste_anual <= -1:
        raise ValueError("O reajuste precisa ser maior que -100%.")


def valor_futuro(
    inicial: float,
    aporte: float,
    taxa: float,
    meses: int,
    no_inicio: bool = False,
    reajuste_anual: float = 0.0,
) -> float:
    """O saldo depois de `meses` meses."""
    _conferir(inicial, aporte, taxa, meses)
    _conferir_reajuste(reajuste_anual)
    if reajuste_anual == 0:
        return inicial * (1 + taxa) ** meses + aporte * _fator_dos_aportes(
            taxa, meses, no_inicio
        )
    saldo = inicial
    for mes in range(1, meses + 1):
        saldo = _proximo_saldo(
            saldo, aporte_do_mes(aporte, mes, reajuste_anual), taxa, no_inicio
        )
    return saldo


def aporte_para_meta(
    meta: float,
    inicial: float,
    taxa: float,
    meses: int,
    no_inicio: bool = False,
    reajuste_anual: float = 0.0,
) -> float:
    """O primeiro aporte mensal para chegar a `meta` em `meses` meses (0 se o valor inicial já
    basta). O saldo cresce em linha reta com o aporte, então basta dividir pelo que R$ 1 vira."""
    _conferir(inicial, 0, taxa, meses)
    if meta < 0:
        raise ValueError("A meta não pode ser negativa.")
    if meses == 0:
        raise ValueError("O prazo precisa ser de pelo menos 1 mês.")
    falta = meta - inicial * (1 + taxa) ** meses
    um_real_por_mes = valor_futuro(0, 1, taxa, meses, no_inicio, reajuste_anual)
    return max(falta / um_real_por_mes, 0.0)


def _proximo_saldo(saldo: float, aporte: float, taxa: float, no_inicio: bool) -> float:
    if no_inicio:
        return (saldo + aporte) * (1 + taxa)
    return saldo * (1 + taxa) + aporte


def meses_ate_meta(
    meta: float,
    inicial: float,
    aporte: float,
    taxa: float,
    no_inicio: bool = False,
    reajuste_anual: float = 0.0,
) -> int | None:
    """Quantos meses até o saldo chegar a `meta`; None se não chega em `PRAZO_MAXIMO` meses."""
    _conferir(inicial, aporte, taxa, 0)
    _conferir_reajuste(reajuste_anual)
    saldo = inicial
    for mes in range(PRAZO_MAXIMO + 1):
        if saldo >= meta:
            return mes
        saldo = _proximo_saldo(
            saldo, aporte_do_mes(aporte, mes + 1, reajuste_anual), taxa, no_inicio
        )
    return None


def evolucao(
    inicial: float,
    aporte: float,
    taxa: float,
    meses: int,
    no_inicio: bool = False,
    reajuste_anual: float = 0.0,
) -> list[Linha]:
    """A tabela mês a mês, do mês 0 (só o valor inicial) ao último."""
    _conferir(inicial, aporte, taxa, meses)
    _conferir_reajuste(reajuste_anual)
    linhas = [Linha(mes=0, aportado=inicial, juros=0, saldo=inicial)]
    for mes in range(1, meses + 1):
        do_mes = aporte_do_mes(aporte, mes, reajuste_anual)
        saldo = _proximo_saldo(linhas[-1].saldo, do_mes, taxa, no_inicio)
        aportado = linhas[-1].aportado + do_mes
        linhas.append(
            Linha(mes=mes, aportado=aportado, juros=saldo - aportado, saldo=saldo)
        )
    return linhas


def mes_da_virada(
    inicial: float,
    aporte: float,
    taxa: float,
    meses: int,
    no_inicio: bool = False,
    reajuste_anual: float = 0.0,
) -> int | None:
    """O primeiro mês em que os juros do mês rendem pelo menos o aporte daquele mês ("a partir
    daqui, o dinheiro trabalha mais que você"); None se não acontece no prazo."""
    linhas = evolucao(inicial, aporte, taxa, meses, no_inicio, reajuste_anual)
    for antes, linha in pairwise(linhas):
        do_mes = linha.aportado - antes.aportado
        juros_do_mes = linha.juros - antes.juros
        if do_mes > 0 and juros_do_mes >= do_mes:
            return linha.mes
    return None
