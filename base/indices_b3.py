"""Fechamento diário dos índices da B3 pelas estatísticas do índice (o Ibovespa do pregão do dia).

A B3 publica um ano por pedido em `indexStatisticsProxy/IndexCall/GetPortfolioDay/<pedido>`, com o
pedido em JSON codificado em base64 no próprio endereço (`{"index":"IBOV","language":"pt-br",
"year":"2026"}`). O arquivista guarda cada ano como fonte `b3-ibov-diario` (só pesquisa, sem licença
da B3: ADR 0008, Emenda 6); este módulo monta os endereços e lê os arquivos guardados.

Formato medido em 26/10/2026: `results` traz uma linha por dia do mês (`day` de 1 a 31) e uma coluna
por mês (`rateValue1` a `rateValue12`), com o fechamento em texto brasileiro ("175.710,05"); dia sem
pregão vem `null` ou vazio. `min` e `max` (o menor e o maior fechamento de cada mês) não são lidos.
"""

import base64
import json
from collections.abc import Mapping
from datetime import date

import pandas as pd

ESTATISTICAS_DO_INDICE = "https://sistemaswebb3-listados.b3.com.br/indexStatisticsProxy/IndexCall/GetPortfolioDay/{pedido}"
IBOVESPA = "IBOV"
# o pregão do dia compara a variação com a de cada pregão desde 2000 (`src/pregao_do_dia.py`)
PRIMEIRO_ANO = 2000
MESES = range(1, 13)


def endereco_do_ano(ano: int, indice: str = IBOVESPA) -> str:
    """O endereço das estatísticas de `indice` no ano `ano`."""
    pedido = json.dumps(
        {"index": indice, "language": "pt-br", "year": str(ano)}, separators=(",", ":")
    )
    return ESTATISTICAS_DO_INDICE.format(
        pedido=base64.b64encode(pedido.encode()).decode()
    )


def ano_do_endereco(endereco: str) -> int:
    """O ano pedido num endereço de `endereco_do_ano` (o arquivo da B3 não diz o ano)."""
    pedido = base64.b64decode(endereco.rsplit("/", 1)[1])
    return int(json.loads(pedido)["year"])


def _numero(texto: str) -> float:
    return float(texto.replace(".", "").replace(",", "."))


def ler_ano(conteudo: bytes, ano: int) -> pd.Series:
    """O fechamento de cada pregão do ano (data → pontos), em ordem de data.

    Dia que não existe no calendário (31/11) levanta `ValueError`: é a B3 mudando o formato.
    """
    fechamentos = {
        pd.Timestamp(date(ano, mes, linha["day"])): _numero(texto)
        for linha in json.loads(conteudo)["results"]
        for mes in MESES
        if (texto := linha.get(f"rateValue{mes}"))
    }
    return pd.Series(fechamentos, name="ibovespa", dtype="float64").sort_index()


def serie_dos_anos(anos: Mapping[int, bytes]) -> pd.Series:
    """A série inteira a partir dos arquivos de cada ano (ano → conteúdo), em ordem de data."""
    partes = [ler_ano(conteudo, ano) for ano, conteudo in anos.items()]
    return pd.concat(partes).sort_index().rename("ibovespa")
