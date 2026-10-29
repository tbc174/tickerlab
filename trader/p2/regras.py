"""As regras da Pesquisa 2: previsões de −20 a +20 (média absoluta ~10), sem parâmetro ajustado.

Pré-registro, seção 5. Todas usam só dados até o fechamento do dia (a posição vale no dia seguinte,
o que a carteira garante).

- **T1, tendência lenta:** cruzamentos de médias exponenciais 16/64, 32/128 e 64/256 com as escalas
  publicadas por Carver; média dos três × 1,1; limite ±20.
- **C1, carry:** carry anual ÷ volatilidade anual, média de 90 dias, × 30 (Carver, *Advanced
  Futures Trading Strategies*, p. 216); limite ±20; zero em metais e energia.
- **K2 (candidato):** 60% T1 + 40% C1 × 1,2 onde há carry; T1 puro nos demais. Interpretação
  declarada antes de rodar (11/10/2026): o multiplicador 1,2 compensa a **combinação** de duas
  regras, então não se aplica onde só existe T1.
- **K1:** só T1. **B1:** a tendência de 6 velocidades da M2. **B0:** sempre comprado (+10) em
  índices, energia e título; zero em moedas e metais (como na M2).

As médias móveis usam o **preço acumulado em retornos** (soma dos retornos diários do preço), e a
distância entre as médias é dividida pelo desvio diário dos retornos. É a fórmula de Carver escrita
em retornos, o que funciona também com preço negativo (WTI em 2020) e com o título reconstruído.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trader import baselines
from trader.p2.mercados import Mercado

LIMITE = 20.0
PREVISAO_MEDIA = 10.0
VELOCIDADES_T1 = ((16, 64), (32, 128), (64, 256))
ESCALAS_T1 = {(16, 64): 3.75, (32, 128): 2.65, (64, 256): 1.87}
MULTIPLICADOR_T1 = 1.1
ESCALA_C1 = 30.0
JANELA_DO_CARRY = 90
PESO_T1, PESO_C1 = 0.6, 0.4
MULTIPLICADOR_K2 = 1.2
SPAN_DA_VOLATILIDADE = 35
DIAS_UTEIS_DO_ANO = 256
GRUPOS_COM_CARRY = {"moedas", "indices", "titulos"}
GRUPOS_COMPRADOS_NO_B0 = {"indices", "energia", "titulos"}


def _limitar(previsao: pd.Series) -> pd.Series:
    return previsao.clip(-LIMITE, LIMITE)


def desvio_diario(retorno_do_preco: pd.Series) -> pd.Series:
    return retorno_do_preco.ewm(span=SPAN_DA_VOLATILIDADE, min_periods=10).std()


def ewmac(retorno_do_preco: pd.Series, rapida: int, lenta: int) -> pd.Series:
    """Um cruzamento de médias, na escala de Carver (sem limite)."""
    preco_acumulado = retorno_do_preco.cumsum()
    distancia = (
        preco_acumulado.ewm(span=rapida, min_periods=lenta).mean()
        - preco_acumulado.ewm(span=lenta, min_periods=lenta).mean()
    )
    desvio = desvio_diario(retorno_do_preco).where(lambda d: d > 0)
    return distancia / desvio * ESCALAS_T1[(rapida, lenta)]


def t1(retorno_do_preco: pd.Series) -> pd.Series:
    sinais = [_limitar(ewmac(retorno_do_preco, r, l)) for r, l in VELOCIDADES_T1]
    media = pd.concat(sinais, axis=1).mean(axis=1, skipna=False)
    return _limitar(media * MULTIPLICADOR_T1)


def c1(retorno_do_preco: pd.Series, carry_anual: pd.Series) -> pd.Series:
    volatilidade_anual = desvio_diario(retorno_do_preco) * np.sqrt(DIAS_UTEIS_DO_ANO)
    razao = carry_anual / volatilidade_anual.where(lambda v: v > 0)
    suavizada = razao.rolling(JANELA_DO_CARRY, min_periods=JANELA_DO_CARRY).mean()
    return _limitar(suavizada * ESCALA_C1)


def k2(
    mercado: Mercado, retorno_do_preco: pd.Series, carry_anual: pd.Series
) -> pd.Series:
    tendencia = t1(retorno_do_preco)
    if mercado.grupo not in GRUPOS_COM_CARRY:
        return tendencia
    combinada = PESO_T1 * tendencia + PESO_C1 * c1(retorno_do_preco, carry_anual)
    return _limitar(combinada * MULTIPLICADOR_K2)


def b1(retorno_do_preco: pd.Series) -> pd.Series:
    """A régua: a tendência de 6 velocidades da M2 (−20 a +20)."""
    return baselines.previsao_b1(retorno_do_preco)


def b0(mercado: Mercado, indice: pd.Index) -> pd.Series:
    valor = PREVISAO_MEDIA if mercado.grupo in GRUPOS_COMPRADOS_NO_B0 else 0.0
    return pd.Series(valor, index=indice)


CONFIGURACOES = ("K1", "K2", "B0", "B1")


def previsao(configuracao: str, mercado: Mercado, tabela: pd.DataFrame) -> pd.Series:
    """Previsão de uma configuração para um mercado (`tabela` de `retornos.montar`)."""
    preco, carry = tabela["preco"], tabela["carry_anual"]
    if configuracao == "K1":
        return t1(preco)
    if configuracao == "K2":
        return k2(mercado, preco, carry)
    if configuracao == "B1":
        return b1(preco)
    if configuracao == "B0":
        return b0(mercado, tabela.index)
    raise ValueError(
        f"Configuração desconhecida: {configuracao}. Use uma de {CONFIGURACOES}."
    )
