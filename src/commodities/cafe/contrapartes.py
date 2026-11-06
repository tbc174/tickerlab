"""Simulação do risco de travar o preço do café: uma conta só, sem nota (PR 12 do plano do café).

(preço de hoje − preço da trava) × sacas. Positivo: quanto quem vendeu travado deixa de ganhar (e a
tentação de não entregar); negativo: quanto quem comprou travado paga acima do mercado (e o risco de
não pagar). Não é nota, semáforo, previsão nem conselho; o texto que explica os dois lados está em
`conteudo/commodities/cafe.md` ("Os dois lados do risco de travar"). A ficha da contraparte, só com
fatos datados e fonte, fica em `base/contrapartes/cafe.py`.

Rota que exporia: `GET /v1/commodities/cafe/simular-trava?preco_na_data=&preco_hoje=&sacas=`.
"""

from dataclasses import dataclass

from src.dividendos_e_custo import formatar_reais

PRODUTOR = "produtor"  # quem vendeu travado
COMPRADOR = "comprador"  # cooperativa ou trading que comprou travado


@dataclass(frozen=True)
class SimulacaoDaTrava:
    preco_na_data: float  # R$ por saca de 60 kg, no dia da trava
    preco_hoje: float  # R$ por saca de 60 kg
    sacas: float
    diferenca_por_saca: float  # hoje − na data
    diferenca_total: float  # diferença por saca × sacas
    quem_deixa_de_ganhar: str | None  # PRODUTOR, COMPRADOR ou None (preço igual)
    texto: str


def _sacas_br(sacas: float) -> str:
    return f"{sacas:,.0f}".replace(",", ".")


def _texto(diferenca_por_saca: float, diferenca_total: float, sacas: float) -> str:
    por_saca, total = (
        formatar_reais(abs(diferenca_por_saca)),
        formatar_reais(abs(diferenca_total)),
    )
    if diferenca_por_saca > 0:
        return (
            f"O preço subiu {por_saca} por saca desde a trava. Quem vendeu travado deixa de ganhar "
            f"{total} nas {_sacas_br(sacas)} sacas, comparado a vender hoje: quanto maior essa "
            "diferença, maior a tentação de não entregar, e quem fica exposto é o comprador."
        )
    if diferenca_por_saca < 0:
        return (
            f"O preço caiu {por_saca} por saca desde a trava. Quem comprou travado paga {total} "
            f"acima do mercado nas {_sacas_br(sacas)} sacas: quanto maior essa diferença, maior o "
            "peso no caixa do comprador, e quem fica exposto a ele não pagar é o produtor."
        )
    return "O preço não mudou desde a trava: nenhum dos lados deixa de ganhar com o contrato."


def simular_risco_de_travar(
    preco_na_data: float, preco_hoje: float, sacas: float
) -> SimulacaoDaTrava:
    """A diferença entre o preço de hoje e o da trava, por saca e no total, e quem deixa de ganhar."""
    if preco_na_data <= 0 or preco_hoje <= 0:
        raise ValueError("os preços são em R$ por saca e precisam ser positivos")
    if sacas <= 0:
        raise ValueError("o número de sacas precisa ser positivo")
    por_saca = preco_hoje - preco_na_data
    total = por_saca * sacas
    quem = PRODUTOR if por_saca > 0 else COMPRADOR if por_saca < 0 else None
    return SimulacaoDaTrava(
        preco_na_data=preco_na_data,
        preco_hoje=preco_hoje,
        sacas=sacas,
        diferenca_por_saca=por_saca,
        diferenca_total=total,
        quem_deixa_de_ganhar=quem,
        texto=_texto(por_saca, total, sacas),
    )
