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

import numpy as np
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


PRECOS = ["Open", "High", "Low", "Close"]
JANELA_DE_LIMPEZA = 252  # um ano de pregões
TAXA_MAXIMA_DE_INCOERENCIA = 0.01  # até 1% dos candles do último ano


def marcar_incoerentes(candles: pd.DataFrame) -> pd.Series:
    """True nos candles em que máxima/mínima não contêm abertura e fechamento."""
    return (
        (candles["High"] < candles["Low"])
        | (candles["Close"] > candles["High"])
        | (candles["Close"] < candles["Low"])
        | (candles["Open"] > candles["High"])
        | (candles["Open"] < candles["Low"])
    )


def reparar_candles(candles: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Conserta os defeitos de OHLC que não mudam o fechamento. Devolve (candles, quantos).

    - abertura zerada (ou negativa) com fechamento positivo: usa o fechamento;
    - máxima e mínima passam a ser o maior e o menor entre os quatro preços.

    Preço de fechamento nunca é alterado. Preços negativos (o petróleo WTI fechou em -37,63 em
    20/04/2020) ficam como estão: são reais e precisam de tratamento à parte.
    """
    reparado = candles.copy()
    abertura_ruim = (reparado["Open"] <= 0) & (reparado["Close"] > 0)
    reparado.loc[abertura_ruim, "Open"] = reparado.loc[abertura_ruim, "Close"]
    positivos = (reparado[PRECOS] > 0).all(axis=1)
    reparado.loc[positivos, "High"] = reparado.loc[positivos, PRECOS].max(axis=1)
    reparado.loc[positivos, "Low"] = reparado.loc[positivos, PRECOS].min(axis=1)
    mudou = (reparado[PRECOS] != candles[PRECOS]).any(axis=1)
    return reparado, int(mudou.sum())


def limpo_desde(candles: pd.DataFrame) -> pd.Timestamp | None:
    """Primeira data a partir da qual a série bruta é coerente (até 1% de defeitos por ano).

    Devolve None se nem o fim da série atende. Use para decidir a partir de quando confiar em
    máxima e mínima (o fechamento costuma ser confiável antes disso).
    """
    if candles.empty:
        return None
    taxa = (
        marcar_incoerentes(candles)
        .astype(float)
        .rolling(JANELA_DE_LIMPEZA, min_periods=JANELA_DE_LIMPEZA)
        .mean()
    )
    ruins = taxa[taxa > TAXA_MAXIMA_DE_INCOERENCIA]
    if ruins.empty:
        return candles.index[0]
    ultima_ruim = ruins.index[-1]
    if ultima_ruim == candles.index[-1]:
        return None
    posterior = candles.index[candles.index > ultima_ruim]
    return posterior[0]


def detectar_saltos(
    fechamento: pd.Series, janela: int = 60, limite: float = 6.0
) -> pd.Series:
    """Retornos diários muito maiores que o normal da série (em múltiplos do desvio robusto).

    Em futuros contínuos sem ajuste, a troca de contrato cria saltos falsos. Mas choques reais
    (covid, guerra) também aparecem aqui: o resultado é uma lista de SUSPEITOS para conferir,
    não uma prova. A escala usa só os `janela` dias anteriores (não olha o futuro).
    """
    positivo = fechamento.where(fechamento > 0)
    retorno = np.log(positivo).diff()
    desvio = (
        retorno.rolling(janela, min_periods=janela // 2)
        .apply(lambda x: np.nanmedian(np.abs(x - np.nanmedian(x))) * 1.4826, raw=True)
        .shift(1)
    )
    marcados = retorno.abs() > limite * desvio
    return retorno[marcados.fillna(False)]


def verificar_qualidade(candles: pd.DataFrame, timeframe: str = "D1") -> Qualidade:
    """Procura os defeitos comuns de uma série de candles."""
    if candles.empty:
        return Qualidade(0, None, None, 0, False, 0, 0, 0, [])
    preco = candles[PRECOS]
    incoerentes = marcar_incoerentes(candles)
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
