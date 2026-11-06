"""O universo candidato da Pesquisa 2: cada CFD da corretora de referência e a série gratuita dele.

A regra de entrada (`entra_no_universo`) foi escrita **antes** de olhar qualquer desempenho
(decisões 0012 e 0013): o mercado precisa ter CFD na conta demo de referência e uma série diária
gratuita que comece cedo o bastante para ter anos de desenvolvimento antes do holdout.

Ficaram de fora, de propósito:
- **cripto:** o custo de manter o CFD é de ~20% ao ano nos dois lados, alto demais para uma
  estratégia que fica posicionada por semanas;
- **agrícolas:** a conta de referência (Admirals, entidade SC) não tem CFDs deles;
- **ações individuais e ETFs de ações:** o risco já está nos índices.
- **gás natural:** o preço à vista gratuito (Henry Hub) tem picos de até +143% num dia nas ondas
  de frio, que o CFD (que segue o futuro) não tem, e buracos de até 24 dias (decisão 0014).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

GRUPOS = ("moedas", "indices", "metais", "energia", "titulos")
FONTES = ("fred", "yahoo", "mt5")

INICIO_DO_HOLDOUT = pd.Timestamp("2023-10-10")
ANOS_MINIMOS_ANTES_DO_HOLDOUT = 15  # com menos, o t-estatístico não tem como chegar a 3
INICIO_MAXIMO = INICIO_DO_HOLDOUT - pd.DateOffset(years=ANOS_MINIMOS_ANTES_DO_HOLDOUT)


@dataclass(frozen=True)
class Mercado:
    """Um mercado operável: o CFD na corretora e de onde vem o histórico gratuito dele."""

    codigo: str  # nome usado na pesquisa (ex.: "EURUSD")
    grupo: str  # um de GRUPOS
    cfd: str  # símbolo na conta demo de referência (ex.: "EURUSD-T")
    fonte: str  # um de FONTES
    serie: str  # identificador na fonte (ex.: "DEXUSEU" no FRED, "^GSPC" no Yahoo)
    moeda: str  # moeda em que o preço é cotado
    rendimento: bool = False  # True: a série é uma taxa de juros (%), não um preço


MERCADOS: tuple[Mercado, ...] = (
    # Moedas: o FRED já cota cada par no mesmo sentido do CFD (ex.: dólares por euro).
    Mercado("EURUSD", "moedas", "EURUSD-T", "fred", "DEXUSEU", "USD"),
    Mercado("GBPUSD", "moedas", "GBPUSD-T", "fred", "DEXUSUK", "USD"),
    Mercado("USDJPY", "moedas", "USDJPY-T", "fred", "DEXJPUS", "JPY"),
    Mercado("AUDUSD", "moedas", "AUDUSD-T", "fred", "DEXUSAL", "USD"),
    Mercado("USDCAD", "moedas", "USDCAD-T", "fred", "DEXCAUS", "CAD"),
    Mercado("USDCHF", "moedas", "USDCHF-T", "fred", "DEXSZUS", "CHF"),
    Mercado("NZDUSD", "moedas", "NZDUSD-T", "fred", "DEXUSNZ", "USD"),
    Mercado("USDNOK", "moedas", "USDNOK-T", "fred", "DEXNOUS", "NOK"),
    Mercado("USDSEK", "moedas", "USDSEK-T", "fred", "DEXSDUS", "SEK"),
    Mercado("USDMXN", "moedas", "USDMXN-T", "fred", "DEXMXUS", "MXN"),
    Mercado("USDBRL", "moedas", "USDBRL-T", "fred", "DEXBZUS", "BRL"),
    # Índices de ações: o Yahoo dá o índice de preço (o dividendo entra à parte, decisão 0013).
    Mercado("USA500", "indices", "[USA500]-T", "yahoo", "^GSPC", "USD"),
    Mercado("US100", "indices", "US100-T", "yahoo", "^NDX", "USD"),
    Mercado("USA30", "indices", "[USA30]-T", "yahoo", "^DJI", "USD"),
    Mercado("GER40", "indices", "[GER40]-T", "yahoo", "^GDAXI", "EUR"),
    Mercado("UK100", "indices", "[UK100]-T", "yahoo", "^FTSE", "GBP"),
    Mercado("FRA40", "indices", "[FRA40]-T", "yahoo", "^FCHI", "EUR"),
    Mercado("SPA35", "indices", "[SPA35]-T", "yahoo", "^IBEX", "EUR"),
    Mercado("STXE50", "indices", "[STXE50]-T", "yahoo", "^STOXX50E", "EUR"),
    Mercado("JP225", "indices", "[JP225]-T", "yahoo", "^N225", "JPY"),
    Mercado("HK50", "indices", "[HK50]-T", "yahoo", "^HSI", "HKD"),
    Mercado("AUS200", "indices", "[AUS200]-T", "yahoo", "^AXJO", "AUD"),
    # Metais (decisão 0014): ouro e prata pelo histórico do próprio CFD (à vista, sem rolagem,
    # desde 1995 e 2002); cobre pelo futuro do Yahoo, porque o CFD só existe desde 2018 (na
    # sobreposição de 2018 a 2023 não houve nenhum dia anômalo).
    Mercado("GOLD", "metais", "GOLD-T", "mt5", "GOLD-T", "USD"),
    Mercado("SILVER", "metais", "SILVER-T", "mt5", "SILVER-T", "USD"),
    Mercado("COPPER", "metais", "COPPER-T", "yahoo", "HG=F", "USD"),
    # Energia: preço à vista do FRED (o CFD embute a rolagem no custo de manter).
    Mercado("BRENT", "energia", "BRENT-T", "fred", "DCOILBRENTEU", "USD"),
    Mercado("WTI", "energia", "US.OIL-T", "fred", "DCOILWTICO", "USD"),
    # Títulos: rendimento de 10 anos dos EUA (o retorno sai da duração); o CFD é o do ETF IEF.
    Mercado("UST10", "titulos", "#IEF-T", "fred", "DGS10", "USD", rendimento=True),
)

# Juros curtos de cada moeda, para o carry das moedas e o custo de manter (OCDE e Tesouro dos EUA).
JUROS_CURTOS: dict[str, str] = {
    "USD": "DTB3",
    "EUR": "IR3TIB01EZM156N",
    "GBP": "IR3TIB01GBM156N",
    "JPY": "IR3TIB01JPM156N",
    "AUD": "IR3TIB01AUM156N",
    "CAD": "IR3TIB01CAM156N",
    "CHF": "IR3TIB01CHM156N",
    "NZD": "IR3TIB01NZM156N",
    "NOK": "IR3TIB01NOM156N",
    "SEK": "IR3TIB01SEM156N",
    "MXN": "IR3TIB01MXM156N",
    "BRL": "INTDSRBRM193N",  # taxa básica do Brasil (mensal, FRED); o CDI diário fica no SGS
    "DEM": "IR3TIB01DEM156N",  # Alemanha, para os anos antes da zona do euro
}


def entra_no_universo(mercado: Mercado, inicio_da_serie: pd.Timestamp | None) -> bool:
    """O mercado entra se tem CFD de referência e a série começa até `INICIO_MAXIMO`."""
    if inicio_da_serie is None or not mercado.cfd:
        return False
    return inicio_da_serie <= INICIO_MAXIMO


def por_codigo(codigo: str) -> Mercado:
    for mercado in MERCADOS:
        if mercado.codigo == codigo:
            return mercado
    raise KeyError(f"Mercado desconhecido: {codigo}")
