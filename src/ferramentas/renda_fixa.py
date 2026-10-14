"""Renda fixa com IR: CDB, LCI/LCA, Tesouro Selic e poupança lado a lado, pelo mesmo prazo.

- CDB: um percentual do CDI, sobre a taxa de cada dia útil; IR pela tabela regressiva.
- LCI ou LCA: um percentual do CDI, isento de IR para pessoa física.
- Tesouro Selic: a Selic de cada dia, que na prática anda junto com o CDI; IR pela tabela.
- Poupança: rende só no aniversário (a cada 30 dias), isenta.

As regras de imposto vêm de `src/regras_de_imposto.py`. Os dias corridos viram dias úteis pela
proporção 252/365 (sem o calendário de feriados). Fica de fora: a taxa de custódia da B3 no Tesouro,
o IOF dos primeiros 30 dias, o risco de cada emissor e o FGC.
"""

from dataclasses import dataclass

from src.regras_de_imposto import aliquota_da_renda_fixa

DIAS_UTEIS_POR_ANO = 252
DIAS_POR_ANO = 365
DIAS_DO_ANIVERSARIO = 30  # a poupança rende a cada aniversário mensal
DIAS_MAXIMOS = 3650  # 10 anos


@dataclass(frozen=True)
class Opcao:
    nome: str
    bruto: float  # o valor no fim, antes do IR
    aliquota: float
    imposto: float
    liquido: float


def _dias_uteis(dias: int) -> float:
    return dias * DIAS_UTEIS_POR_ANO / DIAS_POR_ANO


def _pelo_cdi(valor: float, dias: int, cdi_ao_ano: float, percentual: float) -> float:
    diaria = ((1 + cdi_ao_ano) ** (1 / DIAS_UTEIS_POR_ANO) - 1) * percentual
    return valor * (1 + diaria) ** _dias_uteis(dias)


def _com_ir(nome: str, valor: float, bruto: float, dias: int) -> Opcao:
    aliquota = aliquota_da_renda_fixa(dias)
    imposto = max(bruto - valor, 0) * aliquota
    return Opcao(nome, bruto, aliquota, imposto, bruto - imposto)


def _isento(nome: str, bruto: float) -> Opcao:
    return Opcao(nome, bruto, 0.0, 0.0, bruto)


def comparar(
    valor: float,
    dias: int,
    cdi_ao_ano: float,
    percentual_do_cdb: float,
    percentual_da_lci: float,
    poupanca_ao_mes: float,
) -> list[Opcao]:
    """As quatro opções pelo mesmo `valor` e `dias` corridos (percentuais: 1,1 = 110% do CDI)."""
    if valor < 0:
        raise ValueError("O valor aplicado não pode ser negativo.")
    if dias < 1 or dias > DIAS_MAXIMOS:
        raise ValueError(f"O prazo precisa estar entre 1 e {DIAS_MAXIMOS} dias.")
    if percentual_do_cdb < 0 or percentual_da_lci < 0:
        raise ValueError("O percentual do CDI não pode ser negativo.")
    aniversarios = dias // DIAS_DO_ANIVERSARIO
    return [
        _com_ir(
            "CDB", valor, _pelo_cdi(valor, dias, cdi_ao_ano, percentual_do_cdb), dias
        ),
        _isento("LCI ou LCA", _pelo_cdi(valor, dias, cdi_ao_ano, percentual_da_lci)),
        _com_ir("Tesouro Selic", valor, _pelo_cdi(valor, dias, cdi_ao_ano, 1.0), dias),
        _isento("Poupança", valor * (1 + poupanca_ao_mes) ** aniversarios),
    ]
