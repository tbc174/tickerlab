"""Curva de juros dos títulos do Tesouro dos EUA (Daily Treasury Par Yield Curve Rates).

Primeira parte da proposta de dados novos (macro dos EUA). Aqui só se **busca e lê**; guardar com
histórico de versões é outro passo.

Fonte: `home.treasury.gov` (Departamento do Tesouro dos EUA), um CSV por ano com uma coluna por
prazo (1 mês a 30 anos), em % ao ano. Dados do governo americano: domínio público.
"""

import io
import logging
import re
from collections.abc import Callable

import pandas as pd
import requests

from src import rede

URL_DA_CURVA = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{ano}/all"
)
TEMPO_LIMITE = 30  # segundos
MESES_POR_ANO = 12
# "1 Mo", "1.5 Month", "10 Yr": o número e a unidade do prazo
PRAZO = re.compile(r"^\s*(?P<numero>\d+(?:\.\d+)?)\s*(?P<unidade>Mo|Month|Yr)\s*$")

log = logging.getLogger(__name__)

Buscar = Callable[..., requests.Response]


class TesouroIndisponivelError(Exception):
    """O site do Tesouro dos EUA não respondeu ou respondeu algo inesperado."""


def prazo_em_anos(coluna: str) -> float | None:
    """O prazo de uma coluna do CSV em anos ("6 Mo" vira 0,5); None se não for um prazo."""
    achado = PRAZO.match(coluna)
    if achado is None:
        return None
    numero = float(achado["numero"])
    return numero if achado["unidade"] == "Yr" else numero / MESES_POR_ANO


def montar_curva(texto_csv: str) -> pd.DataFrame:
    """A curva por dia: colunas = prazo em anos, valores = taxa em fração (0,0425 = 4,25%)."""
    try:
        tabela = pd.read_csv(io.StringIO(texto_csv))
        datas = pd.to_datetime(tabela.pop("Date"), format="%m/%d/%Y")
    except (KeyError, ValueError, pd.errors.ParserError) as erro:
        raise TesouroIndisponivelError("CSV inesperado do Tesouro dos EUA.") from erro
    prazos = {coluna: prazo_em_anos(coluna) for coluna in tabela.columns}
    validos = {coluna: anos for coluna, anos in prazos.items() if anos is not None}
    if not validos:
        raise TesouroIndisponivelError("O CSV do Tesouro dos EUA não tem prazos.")
    curva = tabela[list(validos)].apply(pd.to_numeric, errors="coerce") / 100
    curva.columns = list(validos.values())
    curva.index = datas
    curva = curva.sort_index(axis=0).sort_index(axis=1)
    return curva[~curva.index.duplicated(keep="last")]


def baixar_curva(ano: int, buscar: Buscar = rede.get_com_agente) -> pd.DataFrame:
    """A curva diária de um ano inteiro (o ano corrente vem até o último dia útil publicado)."""
    params = {
        "type": "daily_treasury_yield_curve",
        "field_tdr_date_value": str(ano),
        "_format": "csv",
    }
    try:
        resposta = buscar(
            URL_DA_CURVA.format(ano=ano),
            params=params,
            timeout=TEMPO_LIMITE,
        )
        resposta.raise_for_status()
    except requests.RequestException as erro:
        log.warning("Falha ao consultar o Tesouro dos EUA: %s", erro)
        raise TesouroIndisponivelError(
            "Não consegui consultar o Tesouro dos EUA agora."
        ) from erro
    return montar_curva(resposta.text)
