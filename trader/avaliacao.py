"""Métricas da M2 por ativo e da carteira (as que o critério v0.1 usa nas seções 5A e 5B).

Convenções:
- retornos diários líquidos de custos, como saem de `trader.backtest`;
- a carteira é a média, em cada dia útil, dos ativos que têm dado naquele dia (risco igual, porque
  cada ativo já foi dimensionado para a mesma volatilidade alvo);
- cripto negocia no fim de semana: os retornos de sábado e domingo são somados (compostos) na
  segunda-feira antes de entrar na carteira, para todos andarem no mesmo calendário.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DIAS_POR_ANO = 252
NAN = float("nan")


def para_dias_uteis(retorno: pd.Series) -> pd.Series:
    """Compõe sábados e domingos na segunda-feira seguinte (série que só tem dias úteis)."""
    retorno = retorno.dropna()  # dia sem dado fica de fora (não vira retorno zero)
    if retorno.empty:
        return retorno
    datas = retorno.index
    destino = datas + pd.to_timedelta(
        (7 - datas.weekday) % 7 * (datas.weekday >= 5), unit="D"
    )
    return (1 + retorno).groupby(destino).prod() - 1


def sharpe(retorno: pd.Series, dias_por_ano: int = DIAS_POR_ANO) -> float:
    r = retorno.dropna()
    if len(r) < 2 or r.std() == 0:
        return NAN
    return float(r.mean() / r.std() * np.sqrt(dias_por_ano))


def t_estatistica(retorno: pd.Series) -> float:
    r = retorno.dropna()
    if len(r) < 2 or r.std() == 0:
        return NAN
    return float(r.mean() / r.std() * np.sqrt(len(r)))


def maior_queda(retorno: pd.Series) -> float:
    curva = (1 + retorno.fillna(0)).cumprod()
    return float((curva / curva.cummax() - 1).min()) if len(curva) else NAN


def fracao_de_anos_positivos(retorno: pd.Series) -> float:
    """Anos civis com retorno composto positivo, dividido pelos anos com dados."""
    if retorno.empty:
        return NAN
    por_ano = (1 + retorno).groupby(retorno.index.year).prod() - 1
    return float((por_ano > 0).mean())


def resumir_serie(retorno: pd.Series, dias_por_ano: int = DIAS_POR_ANO) -> dict:
    r = retorno.dropna()
    return {
        "sharpe": sharpe(r, dias_por_ano),
        "t": t_estatistica(r),
        "retorno_anual": float(r.mean() * dias_por_ano) if len(r) else NAN,
        "volatilidade_anual": float(r.std() * np.sqrt(dias_por_ano))
        if len(r) > 1
        else NAN,
        "maior_queda": maior_queda(r),
        "anos_positivos": fracao_de_anos_positivos(r),
        "dias": len(r),
        "inicio": r.index.min().date().isoformat() if len(r) else None,
        "fim": r.index.max().date().isoformat() if len(r) else None,
    }


def montar_carteira(retornos: dict[str, pd.Series]) -> pd.DataFrame:
    """Uma coluna por ativo, em dias úteis (cripto com o fim de semana composto na segunda)."""
    if not retornos:
        return pd.DataFrame()
    return pd.concat({nome: para_dias_uteis(r) for nome, r in retornos.items()}, axis=1)


def retorno_da_carteira(tabela: pd.DataFrame) -> pd.Series:
    """Média dos ativos disponíveis em cada dia; dias sem nenhum ativo saem."""
    return tabela.mean(axis=1, skipna=True).dropna()


def participacao_por_ativo(tabela: pd.DataFrame) -> pd.Series:
    """Quanto do resultado da carteira veio de cada ativo (soma = 1 quando o total é positivo)."""
    ativos_por_dia = tabela.notna().sum(axis=1).replace(0, np.nan)
    contribuicao = tabela.div(ativos_por_dia, axis=0).sum()
    total = contribuicao.sum()
    if not total > 0:
        return contribuicao * NAN
    return contribuicao / total


def resumir_carteira(retornos: dict[str, pd.Series]) -> dict:
    """Critérios de carteira da seção 5A: Sharpe, t, anos positivos, ativos positivos e concentração."""
    tabela = montar_carteira(retornos)
    carteira = retorno_da_carteira(tabela)
    sharpes = pd.Series({nome: sharpe(r.dropna()) for nome, r in retornos.items()})
    participacao = participacao_por_ativo(tabela)
    return {
        **resumir_serie(carteira),
        "ativos": len(retornos),
        "fracao_de_ativos_positivos": float((sharpes > 0).mean())
        if len(sharpes)
        else NAN,
        "maior_participacao": float(participacao.max())
        if participacao.notna().any()
        else NAN,
        "ativo_de_maior_participacao": (
            str(participacao.idxmax()) if participacao.notna().any() else None
        ),
    }
