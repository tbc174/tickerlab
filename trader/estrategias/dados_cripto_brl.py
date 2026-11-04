"""Dados da ficha P0-1b: BTCBRL e ETHBRL da Binance, em reais e em dias corridos, com cache fora do Git.

Ficha de dados (a mesma da P0-1, sem o dólar):
- **Preços e volumes:** candles diários de BTCBRL e ETHBRL do Binance Vision (`data.binance.vision`,
  arquivos mensais em zip; fechamento e volume financeiro já em reais). Mesma licença de uso interno da
  P0-1; o download foi aprovado com o pré-registro v0.2 (seção 15, escolha 4).
- **Calendário:** todos os dias corridos entre o primeiro e o último candle. Antes do 1º candle de um
  par, o preço fica vazio (a série dele ainda não existia); depois, dia sem candle repete o preço
  anterior e não negocia (volume zero).
- **Volume para o impacto:** o mesmo da P0-1 (média dos 60 dias anteriores, deslocada um dia).

Os zips ficam numa pasta própria (`binance_brl`), separada dos zips em USDT da P0-1; cada um tem o
SHA-256 anotado em `sha256.json` e só é lido, nunca executado.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from trader.criterio_quant import FIM_DO_DESENVOLVIMENTO
from trader.estrategias import dados_tendencia_cripto as dados_p0_1
from trader.estrategias.tendencia_cripto import ATIVOS

PASTA_DA_PESQUISA = dados_p0_1.PASTA_DA_PESQUISA
PASTA_DA_BINANCE_BRL = PASTA_DA_PESQUISA / "binance_brl"
PARES = {"BTC": "BTCBRL", "ETH": "ETHBRL"}
PRIMEIRO_MES = "2020-10"  # o primeiro arquivo mensal dos dois pares no Binance Vision


def meses_do_desenvolvimento(primeiro: str = PRIMEIRO_MES) -> pd.PeriodIndex:
    """Os meses a baixar: do primeiro arquivo ao mês do fim do desenvolvimento (nada do holdout)."""
    return pd.period_range(primeiro, FIM_DO_DESENVOLVIMENTO.strftime("%Y-%m"), freq="M")


def baixar_pares(
    pasta: Path = PASTA_DA_BINANCE_BRL, baixar: dados_p0_1.Baixar | None = None
) -> dict[str, int]:
    """Baixa os zips dos dois pares em reais; devolve quantos arquivos novos de cada par."""
    extra = {} if baixar is None else {"baixar": baixar}
    return {
        par: dados_p0_1.baixar_par(par, meses_do_desenvolvimento(), pasta, **extra)
        for par in PARES.values()
    }


def montar_precos(
    tabelas: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Preços e volumes em reais, em dias corridos; vazio antes do 1º candle de cada par."""
    inicio = min(t.index.min() for t in tabelas.values())
    fim = max(t.index.max() for t in tabelas.values())
    corridos = pd.date_range(inicio, fim, freq="D")
    precos = pd.DataFrame(index=corridos, columns=list(ATIVOS), dtype=float)
    volumes = pd.DataFrame(index=corridos, columns=list(ATIVOS), dtype=float)
    for ativo in ATIVOS:
        tabela = tabelas[ativo].sort_index()
        precos[ativo] = tabela["fechamento"].reindex(corridos).ffill()
        volumes[ativo] = tabela["volume"].reindex(corridos).fillna(0.0)
    return precos, volumes


def carregar_pares(pasta: Path = PASTA_DA_BINANCE_BRL) -> dict[str, pd.DataFrame]:
    """Os candles baixados de cada ativo (BTC e ETH), no par em reais."""
    return {ativo: dados_p0_1.carregar_par(par, pasta) for ativo, par in PARES.items()}


def primeiro_candle(tabelas: dict[str, pd.DataFrame]) -> dict[str, str]:
    """A data do 1º candle de cada par (o relatório confirma o que a ficha deixou "a confirmar")."""
    return {ativo: t.index.min().date().isoformat() for ativo, t in tabelas.items()}
