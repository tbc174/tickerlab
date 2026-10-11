"""Do sinal à posição: volatilidade alvo, teto e buffer (critério v0.1, seção 3).

- O sinal de uma estratégia vai de -1 (vendido cheio) a +1 (comprado cheio).
- A posição é `sinal × alvo ÷ volatilidade anual` do ativo, limitada a ±`teto` (2× por padrão).
  Um ativo calmo (forex, ~7% ao ano) recebe mais capital que um agitado (cripto, ~70%), e assim
  cada ativo contribui com risco parecido.
- A volatilidade mistura a recente (35 dias, média exponencial) com 30% da lenta (média da
  recente nos últimos 10 anos), como no `pysystemtrade`: reage a crises sem pular a cada dia.
- O buffer só mexe na posição quando a ideal sai de uma faixa em volta da atual (±10% da posição
  de sinal cheio) e, quando sai, vai só até a borda: corta custo sem perder o sinal.

Tudo usa só dados até o dia da decisão.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DIAS_POR_ANO = 252
ALVO_PADRAO = 0.10  # 10% ao ano por ativo
TETO_PADRAO = 2.0
LARGURA_DO_BUFFER = 0.10


def retornos_seguros(fechamento: pd.Series) -> pd.Series:
    """Retorno diário que não explode com preço zero ou negativo (WTI em 20/04/2020).

    Nos dias em que o preço de hoje ou de ontem não é positivo, o retorno vira 0 (o dia fica fora
    da conta). O primeiro dia também é 0.
    """
    anterior = fechamento.shift(1)
    valido = (fechamento > 0) & (anterior > 0)
    retorno = fechamento / anterior - 1
    return retorno.where(valido, 0.0).fillna(0.0)


LIMITE_DE_ERRO_DE_AJUSTE = 0.40


def zerar_erros_de_ajuste(
    retorno: pd.Series, limite: float = LIMITE_DE_ERRO_DE_AJUSTE
) -> tuple[pd.Series, int]:
    """Zera retornos diários acima de `limite` em módulo e diz quantos foram zerados.

    Para as ações da B3 do Yahoo: entre 2000 e 2009 há trocas de cotação "por lote de mil" e
    grupamentos mal ajustados (LREN3 +100% e -99,7% em 2005; SUZB3 -86% e +1.900% em 2007).
    Não use em cripto, onde movimentos de 40% num dia acontecem de verdade.
    """
    erro = retorno.abs() > limite
    return retorno.where(~erro, 0.0), int(erro.sum())


def volatilidade_mista(
    retorno: pd.Series,
    dias: int = 35,
    anos_lentos: int = 10,
    proporcao_lenta: float = 0.3,
    dias_por_ano: int = DIAS_POR_ANO,
) -> pd.Series:
    """Volatilidade anual estimada em cada dia, só com o passado (inclusive o próprio dia).

    `dias_por_ano` = 252 para quem fecha no fim de semana; 365 para cripto.
    """
    rapida = retorno.ewm(span=dias, min_periods=10).std() * np.sqrt(dias_por_ano)
    lenta = rapida.rolling(anos_lentos * dias_por_ano, min_periods=dias_por_ano).mean()
    mista = (1 - proporcao_lenta) * rapida + proporcao_lenta * lenta
    # sem histórico para a lenta, usa só a rápida
    return mista.fillna(rapida)


def posicao_por_volatilidade(
    sinal: pd.Series,
    volatilidade: pd.Series,
    alvo: float = ALVO_PADRAO,
    teto: float = TETO_PADRAO,
) -> pd.Series:
    """Posição = sinal × alvo ÷ volatilidade, com teto. Sem volatilidade conhecida, fica em caixa."""
    if alvo <= 0 or teto <= 0:
        raise ValueError("Alvo e teto precisam ser positivos.")
    escala = (alvo / volatilidade).where(volatilidade > 0)
    posicao = sinal.clip(-1, 1) * escala
    return posicao.clip(-teto, teto).fillna(0.0)


def aplicar_buffer(
    posicao_ideal: pd.Series,
    posicao_cheia: pd.Series,
    largura: float = LARGURA_DO_BUFFER,
) -> pd.Series:
    """Só negocia quando a ideal sai da faixa `±largura × posição de sinal cheio`; vai até a borda.

    `posicao_cheia` é a posição que um sinal de 1 daria naquele dia (alvo ÷ volatilidade, com teto):
    a faixa não encolhe quando o sinal se aproxima de zero.
    """
    if largura < 0:
        raise ValueError("A largura do buffer não pode ser negativa.")
    ideal = posicao_ideal.to_numpy(dtype=float)
    meia_faixa = largura * np.abs(posicao_cheia.to_numpy(dtype=float))
    resultado = np.empty_like(ideal)
    atual = 0.0
    for i, (alvo, faixa) in enumerate(zip(ideal, meia_faixa, strict=True)):
        if np.isnan(alvo):
            alvo = 0.0
        faixa = 0.0 if np.isnan(faixa) else faixa
        if atual < alvo - faixa:
            atual = alvo - faixa
        elif atual > alvo + faixa:
            atual = alvo + faixa
        resultado[i] = atual
    return pd.Series(resultado, index=posicao_ideal.index)


def dimensionar(
    sinal: pd.Series,
    retorno: pd.Series,
    alvo: float = ALVO_PADRAO,
    teto: float = TETO_PADRAO,
    largura: float = LARGURA_DO_BUFFER,
    dias_por_ano: int = DIAS_POR_ANO,
) -> pd.Series:
    """Atalho: volatilidade mista → posição por volatilidade → buffer."""
    vol = volatilidade_mista(retorno, dias_por_ano=dias_por_ano)
    ideal = posicao_por_volatilidade(sinal, vol, alvo, teto)
    cheia = posicao_por_volatilidade(pd.Series(1.0, index=sinal.index), vol, alvo, teto)
    return aplicar_buffer(ideal, cheia, largura)
