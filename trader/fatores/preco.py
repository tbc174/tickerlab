"""Fatores de preço de um ativo, dia a dia, só com o passado (o valor do dia t usa preços até t).

Cada função recebe o fechamento diário (e, no beta, o do mercado) e devolve a característica bruta;
o ranking entre ativos e o lado (comprar o maior ou o menor) ficam para quem monta a carteira, como
diz o `catalogo.py`. Janelas em pregões: 21 ≈ um mês, 252 ≈ um ano.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MES = 21
ANO = 252
# o beta e a volatilidade só saem com pelo menos meio ano de pregões na janela
MINIMO_NA_JANELA = ANO // 2


def _retornos(fechamento: pd.Series) -> pd.Series:
    return fechamento.pct_change(fill_method=None)


def momento_12_1(fechamento: pd.Series) -> pd.Series:
    """Retorno de 12 meses pulando o último: P(t-21) / P(t-252) - 1."""
    return fechamento.shift(MES) / fechamento.shift(ANO) - 1


def retorno_de_1_mes(fechamento: pd.Series) -> pd.Series:
    """Retorno do último mês, P(t) / P(t-21) - 1 (a reversão compra os que mais caíram)."""
    return fechamento / fechamento.shift(MES) - 1


def volatilidade_de_12_meses(fechamento: pd.Series) -> pd.Series:
    """Desvio-padrão anualizado dos retornos diários do último ano."""
    return _retornos(fechamento).rolling(
        ANO, min_periods=MINIMO_NA_JANELA
    ).std() * np.sqrt(ANO)


def beta_de_mercado(fechamento: pd.Series, mercado: pd.Series) -> pd.Series:
    """Beta dos retornos diários contra o mercado no último ano: cov(r, m) / var(m).

    Versão simples (janela única de um ano); a de Frazzini e Pedersen separa correlação (5 anos) e
    volatilidade (1 ano). `mercado` é alinhado às datas do ativo, sem preencher buracos.
    """
    r = _retornos(fechamento)
    m = _retornos(mercado.reindex(fechamento.index))
    ambos = r.notna() & m.notna()
    r, m = r.where(ambos), m.where(ambos)
    covariancia = r.rolling(ANO, min_periods=MINIMO_NA_JANELA).cov(m)
    return covariancia / m.rolling(ANO, min_periods=MINIMO_NA_JANELA).var()


def distancia_da_maxima_de_52_semanas(fechamento: pd.Series) -> pd.Series:
    """Quanto o preço está abaixo da máxima do último ano: P(t) / max(P) - 1 (0 = na máxima)."""
    return fechamento / fechamento.rolling(ANO, min_periods=ANO).max() - 1
