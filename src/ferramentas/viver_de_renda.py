"""Viver de renda: quanto juntar para tirar um valor por mês, e quanto tempo o dinheiro dura.

Tudo em dinheiro de hoje: a taxa é o rendimento **acima da inflação** (real) e a retirada mensal
fica no mesmo poder de compra o tempo todo. A retirada sai no começo de cada mês e o resto rende.

Duas formas de viver de renda: só com os juros (o patrimônio nunca acaba; `anos=None`) ou gastando
também o principal em `anos` anos (precisa de menos dinheiro). E o risco que a média esconde: a
mesma média de retorno com um ano ruim logo no começo faz o dinheiro acabar antes (risco de
sequência). A "regra dos 4%" aparece como um caso, não como verdade.
"""

import math

from src.ferramentas.juros import taxa_equivalente

ANOS_MAXIMOS = 100
MESES_MAXIMOS = ANOS_MAXIMOS * 12
RETIRADA_DA_REGRA_DOS_4 = 0.04  # ao ano, sobre o patrimônio do começo
FOLGA = (
    1e-9  # o último mês fecha com o arredondamento da conta, não com um centavo a menos
)


def _conferir(renda_mensal: float, taxa_real: float) -> None:
    if renda_mensal < 0:
        raise ValueError("A renda mensal não pode ser negativa.")
    if taxa_real <= -1:
        raise ValueError("O rendimento precisa ser maior que -100% ao ano.")


def patrimonio_necessario(
    renda_mensal: float, taxa_real: float, anos: int | None
) -> float:
    """O patrimônio que paga `renda_mensal` para sempre (`anos=None`) ou por `anos` anos."""
    _conferir(renda_mensal, taxa_real)
    i = taxa_equivalente(taxa_real, 12, 1)
    if anos is None:
        if i <= 0:
            raise ValueError(
                "Só com os juros não dá: sem rendimento, o dinheiro acaba."
            )
        return renda_mensal * (1 + i) / i
    if anos < 1 or anos > ANOS_MAXIMOS:
        raise ValueError(f"O prazo precisa estar entre 1 e {ANOS_MAXIMOS} anos.")
    meses = anos * 12
    if i == 0:
        return renda_mensal * meses
    # anuidade com a retirada no começo do mês: renda × (1 − (1 + i)^−n) / i × (1 + i)
    return renda_mensal * -_expm1_neg(meses, i) / i * (1 + i)


def _expm1_neg(meses: int, i: float) -> float:
    """(1 + i)^−meses − 1, sem perder dígitos com taxa quase zero."""
    return math.expm1(-meses * math.log1p(i))


def duracao_em_meses(
    patrimonio: float, renda_mensal: float, retornos_anuais: list[float]
) -> int | None:
    """Quantos meses de retirada o patrimônio paga; None se passa de 100 anos.

    O ano k usa `retornos_anuais[k]` (o último vale para os anos seguintes), em termos reais.
    """
    if not retornos_anuais:
        raise ValueError("Informe pelo menos um retorno anual.")
    if renda_mensal <= 0:
        raise ValueError("A retirada mensal precisa ser maior que zero.")
    saldo = patrimonio
    for mes in range(MESES_MAXIMOS):
        if saldo < renda_mensal * (1 - FOLGA):
            return mes
        ano = min(mes // 12, len(retornos_anuais) - 1)
        i = taxa_equivalente(retornos_anuais[ano], 12, 1)
        saldo = (saldo - renda_mensal) * (1 + i)
    return None


def renda_da_regra_dos_4(patrimonio: float) -> float:
    """A renda mensal da "regra dos 4%": 4% do patrimônio do começo por ano, dividido em 12."""
    return patrimonio * RETIRADA_DA_REGRA_DOS_4 / 12


def trajetoria(
    patrimonio: float, renda_mensal: float, retornos_anuais: list[float], horizonte: int
) -> list[float]:
    """O saldo no começo de cada mês, do mês 0 até o mês em que não dá mais para tirar a renda
    inteira (o último saldo é o que sobrou) ou até `horizonte` meses. A mesma conta de
    `duracao_em_meses`: o ano k usa `retornos_anuais[k]` (o último vale para os seguintes)."""
    if horizonte < 1 or horizonte > MESES_MAXIMOS:
        raise ValueError(f"O horizonte precisa estar entre 1 e {MESES_MAXIMOS} meses.")
    if not retornos_anuais:
        raise ValueError("Informe pelo menos um retorno anual.")
    if renda_mensal <= 0:
        raise ValueError("A retirada mensal precisa ser maior que zero.")
    saldos = [patrimonio]
    for mes in range(horizonte):
        if saldos[-1] < renda_mensal * (1 - FOLGA):
            break
        ano = min(mes // 12, len(retornos_anuais) - 1)
        i = taxa_equivalente(retornos_anuais[ano], 12, 1)
        saldos.append((saldos[-1] - renda_mensal) * (1 + i))
    return saldos
