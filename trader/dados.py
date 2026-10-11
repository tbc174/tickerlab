"""Guardar e conferir o histórico de preços baixado do MetaTrader 5.

Os candles ficam em Parquet (`dados_mt5/SIMBOLO_TIMEFRAME.parquet`, fora do Git). Antes de usar
qualquer série numa pesquisa, `verificar_qualidade` procura os defeitos que mais enganam um
backtest: linhas repetidas, buracos, preços impossíveis e candles incoerentes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from trader.mt5 import ConexaoMT5

PASTA_PADRAO = Path(__file__).resolve().parent.parent / "dados_mt5"
PADRAO_DO_SIMBOLO = re.compile(r"[A-Za-z0-9._#&\-]{1,30}")
DIAS_DO_ANO = 365
LACUNA_MAXIMA_DIARIA = pd.Timedelta(
    days=7
)  # feriados prolongados passam; semanas inteiras não


@dataclass(frozen=True)
class Qualidade:
    linhas: int
    inicio: pd.Timestamp | None
    fim: pd.Timestamp | None
    indice_repetido: int
    fora_de_ordem: bool
    valores_vazios: int
    precos_nao_positivos: int
    candles_incoerentes: int  # máxima abaixo da mínima, ou fechamento fora do intervalo
    maiores_lacunas: list[tuple[pd.Timestamp, pd.Timedelta]]

    @property
    def aprovada(self) -> bool:
        return (
            self.linhas > 0
            and self.indice_repetido == 0
            and not self.fora_de_ordem
            and self.valores_vazios == 0
            and self.precos_nao_positivos == 0
            and self.candles_incoerentes == 0
        )


def verificar_qualidade(candles: pd.DataFrame, timeframe: str = "D1") -> Qualidade:
    """Procura os defeitos comuns de uma série de candles."""
    if candles.empty:
        return Qualidade(0, None, None, 0, False, 0, 0, 0, [])
    preco = candles[["Open", "High", "Low", "Close"]]
    incoerentes = (
        (candles["High"] < candles["Low"])
        | (candles["Close"] > candles["High"])
        | (candles["Close"] < candles["Low"])
        | (candles["Open"] > candles["High"])
        | (candles["Open"] < candles["Low"])
    )
    passos = candles.index.to_series().diff().dropna()
    lacunas: list[tuple[pd.Timestamp, pd.Timedelta]] = []
    if timeframe == "D1":
        grandes = passos[passos > LACUNA_MAXIMA_DIARIA].nlargest(5)
        lacunas = [(momento, passo) for momento, passo in grandes.items()]
    return Qualidade(
        linhas=len(candles),
        inicio=candles.index[0],
        fim=candles.index[-1],
        indice_repetido=int(candles.index.duplicated().sum()),
        fora_de_ordem=not candles.index.is_monotonic_increasing,
        valores_vazios=int(preco.isna().sum().sum()),
        precos_nao_positivos=int((preco <= 0).sum().sum()),
        candles_incoerentes=int(incoerentes.sum()),
        maiores_lacunas=lacunas,
    )


def _caminho(simbolo: str, timeframe: str, pasta: Path) -> Path:
    if not PADRAO_DO_SIMBOLO.fullmatch(simbolo):
        raise ValueError(f"Nome de símbolo inválido: {simbolo!r}")
    return pasta / f"{simbolo}_{timeframe}.parquet"


def salvar(
    candles: pd.DataFrame, simbolo: str, timeframe: str, pasta: Path = PASTA_PADRAO
) -> Path:
    caminho = _caminho(simbolo, timeframe, pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    candles.to_parquet(caminho)
    return caminho


def carregar(
    simbolo: str, timeframe: str, pasta: Path = PASTA_PADRAO
) -> pd.DataFrame | None:
    """Os candles guardados, ou None se ainda não foram baixados."""
    caminho = _caminho(simbolo, timeframe, pasta)
    return pd.read_parquet(caminho) if caminho.exists() else None


def baixar_para_disco(
    conexao: ConexaoMT5,
    simbolos: list[str],
    timeframe: str = "D1",
    anos: int = 10,
    pasta: Path = PASTA_PADRAO,
    agora: datetime | None = None,
) -> dict[str, Qualidade | str]:
    """Baixa o histórico de cada símbolo e guarda. Devolve a qualidade (ou o motivo da falha)."""
    fim = agora or datetime.now(UTC)
    inicio = fim - timedelta(days=DIAS_DO_ANO * anos)
    resultado: dict[str, Qualidade | str] = {}
    for simbolo in simbolos:
        try:
            candles = conexao.candles(simbolo, timeframe, inicio, fim)
        except Exception as erro:  # noqa: BLE001 (um símbolo ruim não pode derrubar os outros)
            resultado[simbolo] = f"falhou: {erro}"
            continue
        salvar(candles, simbolo, timeframe, pasta)
        resultado[simbolo] = verificar_qualidade(candles, timeframe)
    return resultado
