"""Verificações de vazamento da seção 8 do critério (antes de aceitar qualquer número).

O pipeline de um candidato precisa saber rodar em três variantes e devolver a carteira:
- "normal": como será avaliado;
- "futuro": os atributos deslocados um dia PARA A FRENTE (olhando o futuro de propósito). Isso tem
  de **inflar** o resultado; se não inflar, o teste não está enxergando nada e não vale;
- "embaralhado": os rótulos de treino embaralhados. Sem relação entre atributo e rótulo, o Sharpe
  tem de ficar perto de zero (dentro de 2 erros-padrão).
Além disso, rodar "normal" duas vezes com a mesma semente tem de dar o mesmo resultado.

`verificar(rodar)` devolve o dicionário que entra em `EvidenciaDoDesenvolvimento.vazamento`.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from trader import avaliacao

VARIANTES = ("normal", "futuro", "embaralhado")
FOLGA_MINIMA_DO_FUTURO = (
    0.5  # o "futuro" precisa render pelo menos 0,5 de Sharpe a mais
)
ERROS_PADRAO = 2.0


def erro_padrao_do_sharpe(retorno: pd.Series, dias_por_ano: int = 252) -> float:
    """Erro-padrão aproximado do Sharpe anual (Lo, 2002): √((1 + SR²/2) / anos)."""
    r = retorno.dropna()
    anos = len(r) / dias_por_ano
    if anos <= 0:
        return float("nan")
    sr = avaliacao.sharpe(r, dias_por_ano)
    return float(np.sqrt((1 + 0.5 * sr**2) / anos))


def verificar(rodar: Callable[[str], pd.Series]) -> tuple[dict[str, bool], dict]:
    """Roda as variantes e devolve (aprovações, detalhes com os números)."""
    normal = rodar("normal")
    de_novo = rodar("normal")
    futuro = rodar("futuro")
    embaralhado = rodar("embaralhado")
    s_normal = avaliacao.sharpe(normal)
    s_futuro = avaliacao.sharpe(futuro)
    s_embaralhado = avaliacao.sharpe(embaralhado)
    limite = ERROS_PADRAO * erro_padrao_do_sharpe(embaralhado)
    reprodutivel = normal.equals(de_novo)
    aprovacoes = {
        "futuro_inflou": bool(s_futuro >= s_normal + FOLGA_MINIMA_DO_FUTURO),
        "rotulos_embaralhados_zero": bool(abs(s_embaralhado) <= limite),
        "reprodutivel": bool(reprodutivel),
    }
    detalhes = {
        "sharpe_normal": s_normal,
        "sharpe_futuro": s_futuro,
        "sharpe_embaralhado": s_embaralhado,
        "limite_do_embaralhado": limite,
    }
    return aprovacoes, detalhes
