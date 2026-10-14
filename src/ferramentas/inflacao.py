"""Correção pela inflação (IPCA): quanto um valor de um mês vale em outro, em poder de compra.

O IPCA de cada mês vem do Banco Central (SGS 433) como fração (0,0052 = 0,52%), em
`[["2024-12", 0.0052], ...]`. Corrigir de dez/2024 a fev/2025 multiplica os IPCAs de dezembro,
janeiro e fevereiro (o mês inicial e o final entram), como a Calculadora do Cidadão do BC faz.
"""

from dataclasses import dataclass

MESES_POR_ANO = 12
Meses = list[list]  # [["2024-12", 0.0052], ...], em ordem


@dataclass(frozen=True)
class Correcao:
    valor_corrigido: float
    fator: float
    variacao: float  # fator − 1
    meses: int


def _conferir_mes(mes: str) -> None:
    ano, _, numero = mes.partition("-")
    if not (ano.isdigit() and numero.isdigit() and 1 <= int(numero) <= MESES_POR_ANO):
        raise ValueError(f"Use o mês no formato AAAA-MM, não {mes}.")


def corrigir(valor: float, inicio: str, fim: str, meses: Meses) -> Correcao:
    """`valor` do começo de `inicio` corrigido até o fim de `fim` ("AAAA-MM") pelo IPCA."""
    _conferir_mes(inicio)
    _conferir_mes(fim)
    if fim < inicio:
        raise ValueError("O mês final precisa vir depois do inicial.")
    primeiro, ultimo = meses[0][0], meses[-1][0]
    if inicio < primeiro:
        raise ValueError(f"O IPCA usado aqui começa em {primeiro}.")
    if fim > ultimo:
        raise ValueError(f"O último IPCA divulgado é o de {ultimo}.")
    fator = 1.0
    usados = 0
    for mes, variacao in meses:
        if inicio <= mes <= fim:
            fator *= 1 + variacao
            usados += 1
    return Correcao(
        valor_corrigido=valor * fator, fator=fator, variacao=fator - 1, meses=usados
    )


def em_12_meses(meses: Meses) -> float:
    """O IPCA acumulado nos últimos 12 meses da lista."""
    if len(meses) < MESES_POR_ANO:
        raise ValueError("São precisos pelo menos 12 meses de IPCA.")
    fator = 1.0
    for _, variacao in meses[-MESES_POR_ANO:]:
        fator *= 1 + variacao
    return fator - 1
