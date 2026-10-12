"""Métricas da M2 por ativo e da carteira (as que o critério usa nas seções 5A e 5B).

Convenções:
- retornos diários líquidos de custos, como saem de `trader.backtest`;
- a carteira divide o risco igualmente entre os GRUPOS de classes (critério v0.3, seção 3): em cada
  dia útil, cada grupo é a média dos seus ativos com dado e a carteira é a média dos grupos com dado
  (cada ativo já foi dimensionado para a mesma volatilidade alvo). Até a v0.2 era a média simples
  dos ativos; `pesos_por_grupo` é o único lugar dessa regra;
- cripto negocia no fim de semana: os retornos de sábado e domingo são somados (compostos) na
  segunda-feira antes de entrar na carteira, para todos andarem no mesmo calendário.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trader.universo import grupo_do_simbolo

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
    return pd.concat(
        {nome: para_dias_uteis(r) for nome, r in retornos.items()}, axis=1, sort=True
    )


def pesos_por_grupo(disponivel: np.ndarray, colunas: list[str]) -> np.ndarray:
    """Peso de cada ativo em cada dia: 1 / (grupos com dado no dia × ativos do grupo com dado).

    `disponivel` é (dias × ativos), True quando o ativo tem dado. Cada linha soma 1 (ou 0, num dia
    sem nenhum ativo).
    """
    disponivel = np.asarray(disponivel, dtype=bool)
    grupos = np.array([grupo_do_simbolo(c) for c in colunas])
    pesos = np.zeros(disponivel.shape, dtype=float)
    unicos = np.unique(grupos)
    por_grupo = (
        np.column_stack([disponivel[:, grupos == g].sum(axis=1) for g in unicos])
        if len(unicos)
        else np.zeros((disponivel.shape[0], 0))
    )
    grupos_no_dia = (por_grupo > 0).sum(axis=1)
    for i, g in enumerate(unicos):
        colunas_do_grupo = grupos == g
        n = por_grupo[:, i]
        with np.errstate(divide="ignore", invalid="ignore"):
            peso = np.where(
                (n > 0) & (grupos_no_dia > 0), 1.0 / (n * grupos_no_dia), 0.0
            )
        pesos[:, colunas_do_grupo] = disponivel[:, colunas_do_grupo] * peso[:, None]
    return pesos


def retorno_da_carteira(tabela: pd.DataFrame) -> pd.Series:
    """Risco igual por grupo (ver `pesos_por_grupo`); dias sem nenhum ativo saem."""
    disponivel = tabela.notna().to_numpy()
    pesos = pesos_por_grupo(disponivel, list(tabela.columns))
    valores = tabela.fillna(0.0).to_numpy(dtype=float)
    carteira = pd.Series((valores * pesos).sum(axis=1), index=tabela.index)
    return carteira[disponivel.any(axis=1)]


def participacao_por_ativo(tabela: pd.DataFrame) -> pd.Series:
    """Quanto do resultado da carteira veio de cada ativo (soma = 1 quando o total é positivo)."""
    pesos = pesos_por_grupo(tabela.notna().to_numpy(), list(tabela.columns))
    contribuicao = pd.Series(
        (tabela.fillna(0.0).to_numpy(dtype=float) * pesos).sum(axis=0),
        index=tabela.columns,
    )
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
