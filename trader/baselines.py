"""As três baselines da M2 (critério v0.1, seção 4). Sinais de -1 a +1, só com o passado.

- **B0 comprar e segurar:** +1 sempre, exceto forex, dólar/real e metais (zero: não há "alta de
  longo prazo" a esperar de uma taxa de câmbio).
- **B1 tendência simples (a que importa):** média de seis cruzamentos de médias móveis exponenciais
  (2/8, 4/16, 8/32, 16/64, 32/128 e 64/256 dias), cada um dividido pela volatilidade do preço e
  normalizado para média absoluta 10, combinados, renormalizados e limitados a ±20 (como no
  `pysystemtrade`). O sinal é a previsão ÷ 20. Nenhum parâmetro é ajustado aos dados.
- **B2 previsão ingênua:** o sinal de amanhã é o sinal do retorno de hoje.

As normalizações usam média expansiva (só o passado). Antes de 250 dias de histórico o sinal é 0.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trader.universo import Ativo

VELOCIDADES = ((2, 8), (4, 16), (8, 32), (16, 64), (32, 128), (64, 256))
PREVISAO_MEDIA = 10.0
TETO_DA_PREVISAO = 20.0
MINIMO_DE_DIAS = 250
CLASSES_SEM_TENDENCIA_DE_ALTA = {"forex", "cambio", "metais"}


def preco_sintetico(retorno: pd.Series) -> pd.Series:
    """Índice de preço refeito a partir dos retornos (começa em 1; nunca fica negativo)."""
    return (1 + retorno).cumprod()


def _normalizar(previsao: pd.Series) -> pd.Series:
    """Escala para média absoluta 10 usando só o passado (média expansiva do valor absoluto)."""
    media_abs = previsao.abs().expanding(min_periods=MINIMO_DE_DIAS).mean()
    return (previsao * PREVISAO_MEDIA / media_abs).where(media_abs > 0)


def sinal_b0(ativo: Ativo, indice: pd.Index) -> pd.Series:
    valor = 0.0 if ativo.classe in CLASSES_SEM_TENDENCIA_DE_ALTA else 1.0
    return pd.Series(valor, index=indice)


def previsao_b1(retorno: pd.Series) -> pd.Series:
    """Previsão combinada de tendência, de -20 a +20 (vazia no aquecimento)."""
    preco = preco_sintetico(retorno)
    desvio_do_preco = preco * retorno.ewm(span=35, min_periods=10).std()
    previsoes = []
    for rapida, lenta in VELOCIDADES:
        media_rapida = preco.ewm(span=rapida, min_periods=lenta).mean()
        media_lenta = preco.ewm(span=lenta, min_periods=lenta).mean()
        bruta = (media_rapida - media_lenta) / desvio_do_preco.where(
            desvio_do_preco > 0
        )
        previsoes.append(_normalizar(bruta))
    combinada = pd.concat(previsoes, axis=1).mean(axis=1, skipna=False)
    return _normalizar(combinada).clip(-TETO_DA_PREVISAO, TETO_DA_PREVISAO)


def sinal_b1(retorno: pd.Series) -> pd.Series:
    return (previsao_b1(retorno) / TETO_DA_PREVISAO).fillna(0.0)


def sinal_b2(retorno: pd.Series) -> pd.Series:
    return pd.Series(
        np.sign(retorno.to_numpy(dtype=float)), index=retorno.index
    ).fillna(0.0)
