"""Medidas do modelo C-1 (pré-registro v2, seção 7)."""

import numpy as np

FAIXAS = 3


def brier_por_linha(probabilidades: np.ndarray, classes: np.ndarray) -> np.ndarray:
    """Erro de cada previsão: soma, nas 3 faixas, de (probabilidade − 1 se foi a faixa, 0 se não)²."""
    certo = np.eye(FAIXAS)[np.asarray(classes, dtype=int)]
    return ((np.asarray(probabilidades) - certo) ** 2).sum(axis=1)


def brier(probabilidades: np.ndarray, classes: np.ndarray) -> float:
    """Brier médio: 0 é perfeito; chutar 1/3 em cada faixa dá 2/3."""
    return float(brier_por_linha(probabilidades, classes).mean())
