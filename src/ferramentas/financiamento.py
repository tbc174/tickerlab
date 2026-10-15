"""Financiamento pelos sistemas SAC e Price, mês a mês, com uma amortização extra opcional.

- SAC: a amortização é a mesma todo mês (o valor ÷ o prazo); o juro cai com o saldo, e a parcela
  cai junto.
- Price: a parcela é a mesma todo mês; no começo quase tudo é juro, no fim quase tudo é amortização.
- Amortização extra num mês: reduz o prazo (mantém a parcela da Price ou a amortização do SAC e
  termina antes) ou reduz a parcela (recalcula para o prazo que falta).

A taxa é ao mês (a página converte a anual pela taxa equivalente). Ficam de fora os seguros, a taxa
de administração do banco e a correção do saldo (TR, IPCA): a página diz isso.
"""

import math
from dataclasses import dataclass

SISTEMAS = ("sac", "price")
MODOS_DA_EXTRA = ("prazo", "parcela")
PRAZO_MAXIMO = 600  # meses: 50 anos
_QUASE_ZERO = 1e-6


@dataclass(frozen=True)
class Linha:
    mes: int
    parcela: float
    juros: float
    amortizacao: float
    extra: float  # a amortização extra deste mês (fora da parcela)
    saldo: float  # depois da parcela e da extra


def parcela_price(valor: float, taxa: float, meses: int) -> float:
    """A parcela fixa que paga `valor` em `meses` meses à `taxa` ao mês."""
    if taxa == 0:
        return valor / meses
    # 1 − (1 + taxa)^−meses sem perder os dígitos quando a taxa é quase zero
    return valor * taxa / -math.expm1(-meses * math.log1p(taxa))


def _conferir(sistema: str, valor: float, taxa: float, meses: int, modo: str) -> None:
    if sistema not in SISTEMAS:
        raise ValueError(f"Use um destes sistemas: {SISTEMAS}.")
    if valor <= 0:
        raise ValueError("O valor financiado precisa ser maior que zero.")
    if taxa < 0 or taxa >= 1:
        raise ValueError("A taxa ao mês precisa estar entre 0% e 100%.")
    if meses < 1 or meses > PRAZO_MAXIMO:
        raise ValueError(f"O prazo precisa estar entre 1 e {PRAZO_MAXIMO} meses.")
    if modo not in MODOS_DA_EXTRA:
        raise ValueError(
            f"A amortização extra reduz o {MODOS_DA_EXTRA[0]} ou a parcela."
        )


def tabela(
    sistema: str,
    valor: float,
    taxa: float,
    meses: int,
    extra_mes: int = 0,
    extra_valor: float = 0.0,
    extra_modo: str = "prazo",
) -> list[Linha]:
    """O financiamento mês a mês, até o saldo zerar."""
    _conferir(sistema, valor, taxa, meses, extra_modo)
    saldo = valor
    amortizacao_do_sac = valor / meses
    parcela_fixa = parcela_price(valor, taxa, meses)
    linhas: list[Linha] = []
    for mes in range(1, meses + 1):
        juros = saldo * taxa
        if sistema == "sac":
            amortizacao = min(amortizacao_do_sac, saldo)
            parcela = amortizacao + juros
        else:
            parcela = min(parcela_fixa, saldo + juros)
            amortizacao = parcela - juros
        saldo -= amortizacao
        extra = 0.0
        if mes == extra_mes and extra_valor > 0 and saldo > _QUASE_ZERO:
            extra = min(extra_valor, saldo)
            saldo -= extra
            restantes = meses - mes
            if extra_modo == "parcela" and restantes > 0:
                amortizacao_do_sac = saldo / restantes
                parcela_fixa = parcela_price(saldo, taxa, restantes)
        if saldo <= _QUASE_ZERO:
            saldo = 0.0
        linhas.append(Linha(mes, parcela, juros, amortizacao, extra, saldo))
        if saldo == 0:
            break
    return linhas
