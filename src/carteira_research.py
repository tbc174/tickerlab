"""A carteira no Research (etapa 5, decisão 0020): só a fotografia dos pesos, com consentimento.

A planilha de posição da Área do Investidor (B3) é lida na memória (`src.carteira_b3`). Daqui sai
só o peso de cada ativo na carteira inteira (Tesouro e renda fixa entram no total). Quantidade e
valor em reais nunca são guardados (decisão 0020, item 5: minimização da LGPD).

O uso da carteira pede um consentimento próprio, separado dos termos (PRD, seção 14): o texto e a
versão ficam aqui; dar e revogar ficam registrados na auditoria (só ids, sem dado pessoal).
Revogar apaga a fotografia.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from src.carteira_b3 import ArquivoDaB3Error, CarteiraB3

VERSAO_DO_CONSENTIMENTO = "2026-10-12"
TEXTO_DO_CONSENTIMENTO = (
    "Autorizo o TickerLab a guardar a fotografia da minha carteira (só o código de cada ativo e o "
    "peso dele em %, sem quantidades nem valores em reais) para ordenar o Research pelo tamanho "
    "das minhas posições e montar a Newsletter da carteira. Posso revogar a qualquer momento, e "
    "a fotografia é apagada na hora."
)
CASAS_DO_PESO = (
    4  # 0,1234 = 12,34%: precisão suficiente, sem revelar o valor da posição
)


@dataclass(frozen=True)
class Fotografia:
    pesos: dict[
        str, float
    ]  # ticker → fração da carteira inteira (0 a 1), do maior ao menor
    enviada_em: date


def fotografia(carteira: CarteiraB3, hoje: date) -> Fotografia:
    """Os pesos dos ativos com cotação na carteira inteira (com Tesouro e renda fixa no total)."""
    total = carteira.valor_total
    if total <= 0 or carteira.posicoes.empty:
        raise ArquivoDaB3Error(
            "A planilha não tem ativos com valor (ações, BDRs, ETFs ou fundos): não há o que "
            "guardar."
        )
    por_ativo = (
        carteira.posicoes.groupby("ticker")["valor"].sum().sort_values(ascending=False)
    )
    pesos = {
        str(ticker): round(float(valor) / total, CASAS_DO_PESO)
        for ticker, valor in por_ativo.items()
        if valor > 0
    }
    return Fotografia(pesos, hoje)


def exposicao(pesos: Mapping[str, float]) -> dict[str, float]:
    """O componente "exposição" da relevância: a maior posição vale 1 e as outras, proporcionais.

    Um ativo de 12% numa carteira cuja maior posição é 24% fica com 0,5.
    """
    maior = max(pesos.values(), default=0.0)
    return {ticker: peso / maior for ticker, peso in pesos.items()} if maior else {}
