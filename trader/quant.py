"""Funções quantitativas que faltavam ao trader (comparação com a `quantlib` do Vibe-Trading).

O que já existe e não se repete aqui: Sharpe, t e maior queda (`trader/avaliacao.py`); Sharpe
probabilístico, comprimento mínimo, Sharpe máximo esperado, Sharpe deflacionado, PBO e Monte Carlo
(`src/acaso.py`); índice de úlcera, duração da queda, Sortino, Calmar e Omega (`src/metricas.py`);
CPCV, bootstrap em blocos e teste do acaso (`trader/validacao.py`, `trader/criterio.py`). A tabela
inteira está em `docs/trader-conferencia-custos-e-validacao.md`.

Aqui ficam só as lacunas úteis para a próxima pesquisa, escritas do zero:

- **VaR e CVaR históricos**: a perda de um dia ruim e a média das perdas além dela (o "quanto se perde
  quando dá errado"), sem supor distribuição normal;
- **Benjamini-Hochberg**: quando muitas hipóteses são testadas de uma vez (um catálogo de fatores),
  controla a fração esperada de falsos achados entre os aprovados, menos conservador que Bonferroni.

Nenhuma delas entra no critério vigente da M2 (selado em `trader/holdout.py`): servem ao próximo
pré-registro, que diz antes de ver resultado se e como usa cada uma.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import pandas as pd

NIVEL_PADRAO = 0.95  # o dia ruim que acontece 1 vez em 20
FDR_PADRAO = 0.05  # fração de falsos achados tolerada entre os aprovados


def _piores(retorno: pd.Series | Sequence[float], nivel: float) -> np.ndarray:
    """Os k piores retornos, k = ceil(n·(1 - nivel)): a cauda que o VaR e o CVaR olham."""
    if not 0 < nivel < 1:
        raise ValueError("O nível precisa ficar entre 0 e 1 (ex.: 0,95).")
    valores = np.asarray(retorno, dtype=float)
    valores = valores[~np.isnan(valores)]
    if valores.size == 0:
        raise ValueError("Não há retornos para medir a cauda.")
    # arredonda antes do teto: 10 · (1 - 0,8) dá 2,0000000000000004 em ponto flutuante
    k = max(1, math.ceil(round(valores.size * (1 - nivel), 9)))
    return np.sort(valores)[:k]


def var_historico(
    retorno: pd.Series | Sequence[float], nivel: float = NIVEL_PADRAO
) -> float:
    """Perda do k-ésimo pior dia, k = ceil(n·(1 - nivel)), como número positivo (0,03 = perder 3%).

    Negativo quando até o k-ésimo pior dia foi de ganho. Retornos vazios (NaN) são ignorados.
    """
    return float(-_piores(retorno, nivel)[-1])


def cvar_historico(
    retorno: pd.Series | Sequence[float], nivel: float = NIVEL_PADRAO
) -> float:
    """Média das perdas dos k piores dias (expected shortfall), como número positivo.

    Sempre maior ou igual ao `var_historico` do mesmo nível: olha a cauda inteira, não só a borda.
    """
    return float(-_piores(retorno, nivel).mean())


def _p_valores(p_valores: Sequence[float]) -> np.ndarray:
    p = np.asarray(p_valores, dtype=float)
    if p.ndim != 1 or p.size == 0:
        raise ValueError("Passe uma lista de p-valores, um por hipótese.")
    if np.isnan(p).any() or (p < 0).any() or (p > 1).any():
        raise ValueError("Os p-valores precisam ficar entre 0 e 1, sem vazios.")
    return p


def p_ajustados_bh(p_valores: Sequence[float]) -> np.ndarray:
    """P-valores ajustados de Benjamini-Hochberg, na ordem de entrada.

    O ajustado da i-ésima menor é min(1, min_{j>=i} p_(j)·m/j): rejeitar quem tem ajustado <= q é o
    mesmo que o procedimento BH com taxa de falsos achados q.
    """
    p = _p_valores(p_valores)
    m = p.size
    ordem = np.argsort(p, kind="stable")
    escalados = p[ordem] * m / np.arange(1, m + 1)
    ajustados_em_ordem = np.minimum.accumulate(escalados[::-1])[::-1]
    ajustados = np.empty(m)
    ajustados[ordem] = np.minimum(ajustados_em_ordem, 1.0)
    return ajustados


def benjamini_hochberg(
    p_valores: Sequence[float], fdr: float = FDR_PADRAO
) -> np.ndarray:
    """Quais hipóteses o BH aprova (True) com taxa de falsos achados `fdr`, na ordem de entrada.

    Vale para testes independentes ou positivamente dependentes (o caso comum de fatores parecidos).
    """
    if not 0 < fdr < 1:
        raise ValueError(
            "A taxa de falsos achados precisa ficar entre 0 e 1 (ex.: 0,05)."
        )
    return p_ajustados_bh(p_valores) <= fdr
