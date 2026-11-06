"""Juros simples e compostos: quanto um valor vira depois de um prazo, e mês a mês.

Juros simples: o juro de cada período é sempre sobre o capital inicial.
Juros compostos: o juro de cada período é sobre o montante até ali (juro sobre juro).

As taxas são frações (0,01 = 1%) e valem por período; a página converte "ao ano" em "ao mês"
com `taxa_por_mes`. Nos compostos vale a taxa equivalente (12,68% ao ano = 1% ao mês); nos simples
vale a proporcional (12% ao ano = 1% ao mês), porque o juro simples não capitaliza: com a
equivalente, 10% ao ano por 10 anos dariam R$ 19.568,97 em vez dos R$ 20.000 do livro-texto.
"""

from dataclasses import dataclass

from src.regras_de_imposto import aliquota_da_renda_fixa

PRAZO_MAXIMO = 1200  # períodos: 100 anos em meses; a tabela mês a mês não passa disso
UNIDADES = ("mes", "ano")
DIAS_POR_ANO = 365


@dataclass(frozen=True)
class Linha:
    """Um período da evolução: o juro dele, o acumulado até ele e o montante no fim dele."""

    periodo: int
    juros_no_periodo: float
    juros_acumulados: float
    montante: float


def _conferir(capital: float, taxa: float, periodos: int) -> None:
    if capital < 0:
        raise ValueError("O capital não pode ser negativo.")
    if taxa <= -1:
        raise ValueError("A taxa precisa ser maior que -100%.")
    if periodos < 0 or periodos > PRAZO_MAXIMO:
        raise ValueError(f"O prazo precisa estar entre 0 e {PRAZO_MAXIMO} períodos.")


def montante(
    capital: float, taxa: float, periodos: int, composto: bool = True
) -> float:
    """O valor no fim de `periodos` períodos, com a `taxa` de cada período."""
    _conferir(capital, taxa, periodos)
    if composto:
        return capital * (1 + taxa) ** periodos
    return capital * (1 + taxa * periodos)


def evolucao(
    capital: float, taxa: float, periodos: int, composto: bool = True
) -> list[Linha]:
    """A tabela período a período, do 0 (só o capital) ao último."""
    _conferir(capital, taxa, periodos)
    linhas = [
        Linha(periodo=0, juros_no_periodo=0, juros_acumulados=0, montante=capital)
    ]
    for periodo in range(1, periodos + 1):
        valor = montante(capital, taxa, periodo, composto)
        linhas.append(
            Linha(
                periodo=periodo,
                juros_no_periodo=valor - linhas[-1].montante,
                juros_acumulados=valor - capital,
                montante=valor,
            )
        )
    return linhas


def taxa_equivalente(taxa: float, de_meses: float, para_meses: float) -> float:
    """A taxa composta de um prazo de `para_meses` equivalente a `taxa` em `de_meses`."""
    if taxa <= -1:
        raise ValueError("A taxa precisa ser maior que -100%.")
    if de_meses <= 0 or para_meses <= 0:
        raise ValueError("Os prazos da taxa precisam ser maiores que zero.")
    return (1 + taxa) ** (para_meses / de_meses) - 1


def taxa_por_mes(taxa: float, unidade: str, composto: bool = True) -> float:
    """A taxa ao mês, a partir de uma taxa "ao mês" ou "ao ano" (`unidade`: "mes" ou "ano").

    "Ao ano" vira a taxa equivalente nos juros compostos e a proporcional (taxa ÷ 12) nos simples."""
    if unidade == "mes":
        return taxa
    if unidade == "ano":
        if not composto:
            if taxa <= -1:
                raise ValueError("A taxa precisa ser maior que -100%.")
            return taxa / 12
        return taxa_equivalente(taxa, de_meses=12, para_meses=1)
    raise ValueError(f"A unidade da taxa precisa ser uma de {UNIDADES}.")


def em_reais_de_hoje(valor: float, inflacao_ao_ano: float, meses: int) -> float:
    """Quanto `valor`, recebido daqui a `meses`, compra em dinheiro de hoje (descontada a inflação)."""
    if inflacao_ao_ano <= -1:
        raise ValueError("A inflação precisa ser maior que -100%.")
    return valor / (1 + inflacao_ao_ano) ** (meses / 12)


def liquido_de_ir(capital: float, montante_bruto: float, meses: int) -> float:
    """O montante depois do IR da tabela regressiva da renda fixa, sobre o ganho. Os meses viram
    dias corridos (365/12 por mês): 6 meses são ~183 dias, já na faixa de 20%."""
    ganho = montante_bruto - capital
    if meses < 1 or ganho <= 0:
        return montante_bruto
    dias = int(
        meses * DIAS_POR_ANO / 12 + 0.5
    )  # metade para cima, como o Math.round do site
    return montante_bruto - ganho * aliquota_da_renda_fixa(dias)
