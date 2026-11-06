"""Spread arábica–robusta desde 1960, a partir dos preços de referência mensais do Pink Sheet.

O spread é a diferença entre o preço do arábica e o do robusta (o conilon, no Brasil), em centavos de
dólar por libra-peso, a unidade em que o mercado fala de café. Quando ele aperta, a indústria de solúvel
troca robusta por arábica; quando alarga, faz o contrário. É um retrato do passado, não uma previsão.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd
import sqlalchemy as sa

from src import precos_de_referencia as precos
from src.banco import series as acervo_de_series

SERIE_ARABICA = "bm-pink-cafe-arabica"
SERIE_ROBUSTA = "bm-pink-cafe-robusta"
DOLARES_POR_KG_EM_CENTAVOS_POR_LIBRA = 100 * precos.LIBRA_EM_KG


@dataclass(frozen=True)
class PontoDoSpread:
    mes: date  # sempre o dia 1
    arabica: float  # centavos de dólar por libra-peso
    robusta: float
    spread: float  # arábica − robusta (negativo quando o robusta passa o arábica)
    razao: float  # arábica ÷ robusta


@dataclass(frozen=True)
class Marco:
    """Um acontecimento que ajuda a ler o gráfico do spread."""

    data: date
    texto: str
    fonte: str


MARCOS = (
    Marco(
        date(2014, 2, 1),
        "Seca de janeiro e fevereiro em Minas Gerais: a safra de arábica 2014 cai e a de conilon sobe, "
        "e o arábica se afasta do robusta.",
        "CONAB, 3º levantamento da safra 2014 (16/09/2014): arábica −16,82%, conilon +21,18%",
    ),
    Marco(
        date(2021, 7, 20),
        "Geadas de 30/06, 20/07 e 30/07 em áreas de arábica no Brasil; o dano em folhas e galhos pesou "
        "na safra seguinte.",
        "USDA, Coffee: World Markets and Trade (dez/2021); USDA GAIN BR2022-0060 (nov/2022)",
    ),
    Marco(
        date(2024, 4, 16),
        "Robusta em Londres passa de US$ 4.000 por tonelada, o que aproxima o preço dele do arábica.",
        "StoneX, relatório de mercado (23/03/2026)",
    ),
    Marco(
        date(2025, 2, 1),
        "Robusta chega perto de US$ 5.800 por tonelada, o recorde da série; o pico exato varia por fonte. "
        "Desde 2023 há reformulações de blends que ficaram.",
        "StoneX, relatório de mercado (23/03/2026); imprensa de mercado",
    ),
)


def spread_arabica_robusta(
    arabica: pd.Series, robusta: pd.Series
) -> list[PontoDoSpread]:
    """O spread mês a mês. As séries chegam em US$/kg com índice de datas; mês sem os dois preços
    fica de fora (nunca vira zero)."""
    juntas = pd.concat([arabica, robusta], axis=1, keys=["a", "r"], join="inner")
    juntas = juntas.dropna().sort_index()
    fator = DOLARES_POR_KG_EM_CENTAVOS_POR_LIBRA
    return [
        PontoDoSpread(
            mes=mes.date(),
            arabica=linha.a * fator,
            robusta=linha.r * fator,
            spread=(linha.a - linha.r) * fator,
            razao=linha.a / linha.r,
        )
        for mes, linha in juntas.iterrows()
    ]


def marcos_ate(dia: date) -> list[Marco]:
    """Os marcos já acontecidos em `dia` (inclusive): quem olha o passado não vê o futuro."""
    return [marco for marco in MARCOS if marco.data <= dia]


def spread_como_estava_em(conexao: sa.Connection, dia: date) -> list[PontoDoSpread]:
    """O spread com os preços como o Pink Sheet os tinha divulgado até `dia`."""
    arabica = acervo_de_series.como_estava_em(conexao, SERIE_ARABICA, dia)
    robusta = acervo_de_series.como_estava_em(conexao, SERIE_ROBUSTA, dia)
    return spread_arabica_robusta(arabica, robusta)
