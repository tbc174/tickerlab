"""Taxas básicas dos bancos centrais (BIS) e o carry de cada ativo.

Fonte: BIS, "Central bank policy rates" (`WS_CBPOL`), diária, pública, mesmo formato para todos os
países. Guardada em `dados_juros/taxas_basicas.parquet` (fora do Git) por
`python -m trader.atualizar_juros`. Taxa básica não é exatamente a taxa de mercado (o CDI fica um
pouco abaixo da Selic, por exemplo), mas a diferença é pequena perto do carry entre moedas.

**Carry** = quanto se ganha (ou paga) por ano só por manter a posição comprada, sem o preço mudar:
- forex BASE/COTADA (EURUSD = euros cotados em dólar): juro da base menos juro da cotada;
- metais (ouro em dólar): menos o juro do dólar (comprar ouro é tomar dólar emprestado);
- ações, índices, ETFs e cripto à vista: menos o juro da moeda em que são cotados. É o custo de
  financiar a posição; com ele o resultado vira "acima do CDI" (ou do juro americano), o mesmo
  que um futuro de índice entrega. Nas ações da B3 isso pesa: o CDI passou de 10% ao ano em boa
  parte do período.

Para não olhar o futuro, a taxa usada num dia é a do dia útil anterior.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import requests

from trader.universo import Ativo

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_PADRAO = RAIZ / "dados_juros" / "taxas_basicas.parquet"
URL_DO_BIS = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D.{paises}"
PAIS_PARA_MOEDA = {
    "US": "USD",
    "XM": "EUR",
    "GB": "GBP",
    "JP": "JPY",
    "CH": "CHF",
    "AU": "AUD",
    "CA": "CAD",
    "NZ": "NZD",
    "MX": "MXN",
    "ZA": "ZAR",
    "BR": "BRL",
}
METAIS = {"XAU", "XAG", "XPT", "XPD"}
# moeda em que cada ativo à vista é cotado (para o custo de financiar a posição)
MOEDA_POR_CLASSE = {"acoes_b3": "BRL", "cripto": "USD"}
MOEDA_POR_SIMBOLO = {
    "^BVSP": "BRL",
    "^GSPC": "USD",
    "^IXIC": "USD",
    "^DJI": "USD",
    "^N225": "JPY",
    "^GDAXI": "EUR",
    "TLT": "USD",
    "GLD": "USD",
}


def baixar_do_bis(inicio: str = "1995-01-01") -> pd.DataFrame:
    """Taxas em % ao ano, uma coluna por moeda, uma linha por dia (com buracos)."""
    url = URL_DO_BIS.format(paises="+".join(PAIS_PARA_MOEDA))
    resposta = requests.get(
        url,
        params={"startPeriod": inicio, "format": "csv"},
        timeout=180,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    resposta.raise_for_status()
    return ler_csv_do_bis(resposta.text)


def ler_csv_do_bis(texto: str) -> pd.DataFrame:
    bruto = pd.read_csv(
        io.StringIO(texto), usecols=["REF_AREA", "TIME_PERIOD", "OBS_VALUE"]
    )
    desconhecidos = set(bruto["REF_AREA"]) - set(PAIS_PARA_MOEDA)
    if desconhecidos:
        raise ValueError(f"País inesperado no arquivo do BIS: {desconhecidos}")
    bruto["TIME_PERIOD"] = pd.to_datetime(bruto["TIME_PERIOD"])
    tabela = bruto.pivot_table(
        index="TIME_PERIOD", columns="REF_AREA", values="OBS_VALUE", aggfunc="last"
    ).rename(columns=PAIS_PARA_MOEDA)
    tabela.index.name = "Date"
    tabela.columns.name = None
    return tabela.sort_index()


def salvar(tabela: pd.DataFrame, caminho: Path = CAMINHO_PADRAO) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_parquet(caminho)
    return caminho


def carregar(caminho: Path = CAMINHO_PADRAO) -> pd.DataFrame:
    if not caminho.exists():
        raise FileNotFoundError(
            "As taxas de juro ainda não foram baixadas: rode `python -m trader.atualizar_juros`."
        )
    return pd.read_parquet(caminho)


def taxa(tabela: pd.DataFrame, moeda: str, indice: pd.DatetimeIndex) -> pd.Series:
    """Taxa da moeda em fração ao ano, em cada data do índice, usando o valor do dia anterior."""
    if moeda not in tabela.columns:
        raise KeyError(f"Sem taxa de juro para {moeda}.")
    serie = tabela[moeda].dropna().sort_index()
    # valor conhecido até a véspera: desloca um dia e pega o último disponível em cada data
    serie.index = serie.index + pd.Timedelta(days=1)
    alinhada = serie.reindex(serie.index.union(indice)).ffill().reindex(indice)
    return alinhada / 100.0


def moedas_do_par(simbolo: str) -> tuple[str, str]:
    """('EUR', 'USD') para EURUSD; BRL=X do Yahoo é USD/BRL."""
    if simbolo == "BRL=X":
        return "USD", "BRL"
    if len(simbolo) != 6:
        raise ValueError(f"Não é um par de moedas: {simbolo}")
    return simbolo[:3], simbolo[3:]


def carry_anual(
    ativo: Ativo, indice: pd.DatetimeIndex, tabela: pd.DataFrame
) -> pd.Series:
    """Carry de ficar COMPRADO, em fração ao ano (vendido recebe o oposto)."""
    if ativo.classe in {"forex", "cambio", "metais"}:
        base, cotada = moedas_do_par(ativo.simbolo)
        juro_da_cotada = taxa(tabela, cotada, indice)
        if base in METAIS:
            return -juro_da_cotada
        return taxa(tabela, base, indice) - juro_da_cotada
    moeda = MOEDA_POR_SIMBOLO.get(ativo.simbolo) or MOEDA_POR_CLASSE.get(ativo.classe)
    if moeda is None:
        raise KeyError(
            f"Não sei em que moeda {ativo.simbolo} ({ativo.classe}) é financiado."
        )
    return -taxa(tabela, moeda, indice)
