"""Conversor de moedas pela PTAX do Banco Central (a cotação oficial de fechamento de um dia útil).

As cotações vêm em reais por unidade da moeda (a PTAX de venda); entre duas moedas estrangeiras, a
conta passa pelo real (cotação cruzada). Não é a cotação "agora" nem a de uma casa de câmbio, que
cobra spread e IOF.
"""

REAL = "BRL"


def _em_reais(moeda: str, cotacoes: dict[str, float]) -> float:
    if moeda == REAL:
        return 1.0
    if moeda not in cotacoes:
        raise ValueError(f"Sem cotação PTAX para {moeda}.")
    return cotacoes[moeda]


def converter(valor: float, de: str, para: str, cotacoes: dict[str, float]) -> float:
    """`valor` na moeda `de` convertido para `para` ("BRL" é o real)."""
    return valor * _em_reais(de, cotacoes) / _em_reais(para, cotacoes)
