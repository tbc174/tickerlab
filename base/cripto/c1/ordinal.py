"""Logística ordinal com regularização L2 (pré-registro v2, seção 6, candidato 1).

Modelo de chances proporcionais para 3 faixas em ordem (calmo < normal < agitado):

    P(faixa <= k | x) = sigmoide(limite_k − x · coeficientes),  k = 0, 1

Os dois limites ficam sempre em ordem (o segundo é o primeiro mais um intervalo positivo). As
entradas são padronizadas com a média e o desvio do treino. A L2 vale só para os coeficientes, não
para os limites, com a mesma convenção do scikit-learn: penalidade = |coeficientes|² / (2·c), e c
menor regulariza mais.

Nenhuma biblioteca instalada tem a ordinal com L2 (o statsmodels tem a ordinal sem L2; o
scikit-learn tem a L2 sem ordem entre as classes): por isso esta, curta, com o gradiente exato
(o embaralhamento em blocos refaz o modelo milhares de vezes).
"""

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, logit

MINIMO = 1e-12
FAIXAS = 3


def _perda_e_gradiente(
    parametros: np.ndarray, x: np.ndarray, y: np.ndarray, c: float
) -> tuple[float, np.ndarray]:
    """Perda (log-verossimilhança negativa + L2) e gradiente. `parametros` = coeficientes, o
    primeiro limite e o log do intervalo entre os limites."""
    coeficientes, limite_0, log_intervalo = (
        parametros[:-2],
        parametros[-2],
        parametros[-1],
    )
    intervalo = np.exp(log_intervalo)
    z = x @ coeficientes
    f0, f1 = expit(limite_0 - z), expit(limite_0 + intervalo - z)
    d0, d1 = f0 * (1 - f0), f1 * (1 - f1)
    meio = np.maximum(f1 - f0, MINIMO)

    eh_0, eh_1, eh_2 = y == 0, y == 1, y == 2
    log_verossimilhanca = (
        np.log(np.maximum(f0[eh_0], MINIMO)).sum()
        + np.log(meio[eh_1]).sum()
        + np.log(np.maximum(1 - f1[eh_2], MINIMO)).sum()
    )
    # derivadas da log-verossimilhança de cada linha em relação a limite_0, limite_1 e z
    por_limite_0 = np.where(eh_0, 1 - f0, 0.0) + np.where(eh_1, -d0 / meio, 0.0)
    por_limite_1 = np.where(eh_1, d1 / meio, 0.0) + np.where(eh_2, -f1, 0.0)
    por_z = (
        np.where(eh_0, -(1 - f0), 0.0)
        + np.where(eh_1, (d0 - d1) / meio, 0.0)
        + np.where(eh_2, f1, 0.0)
    )

    perda = -log_verossimilhanca + coeficientes @ coeficientes / (2 * c)
    gradiente = np.concatenate(
        [
            -(x.T @ por_z) + coeficientes / c,
            [-(por_limite_0.sum() + por_limite_1.sum())],
            [-por_limite_1.sum() * intervalo],
        ]
    )
    return float(perda), gradiente


class LogisticaOrdinal:
    """Logística ordinal com L2; `ajustar` e depois `probabilidades` (n linhas × 3 faixas)."""

    def __init__(self, c: float = 1.0) -> None:
        self.c = c
        self.coeficientes = np.zeros(0)
        self.limites = np.zeros(2)
        self._media = np.zeros(0)
        self._desvio = np.ones(0)

    def ajustar(self, x: np.ndarray, y: np.ndarray) -> "LogisticaOrdinal":
        """Ajusta aos dados (y em 0, 1, 2) e devolve o próprio modelo."""
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=int)
        self._media = x.mean(axis=0)
        self._desvio = np.where(x.std(axis=0) > 0, x.std(axis=0), 1.0)
        padronizado = (x - self._media) / self._desvio
        inicio = np.concatenate([np.zeros(x.shape[1]), _limites_iniciais(y)])
        resultado = minimize(
            _perda_e_gradiente,
            inicio,
            args=(padronizado, y, self.c),
            jac=True,
            method="L-BFGS-B",
        )
        parametros = resultado.x
        self.coeficientes = parametros[:-2]
        self.limites = np.array(
            [parametros[-2], parametros[-2] + np.exp(parametros[-1])]
        )
        return self

    def probabilidades(self, x: np.ndarray) -> np.ndarray:
        """P(calmo), P(normal), P(agitado) para cada linha."""
        z = (
            (np.asarray(x, dtype=float) - self._media) / self._desvio
        ) @ self.coeficientes
        f0, f1 = expit(self.limites[0] - z), expit(self.limites[1] - z)
        return np.clip(np.column_stack([f0, f1 - f0, 1 - f1]), 0.0, 1.0)

    def coeficientes_originais(self) -> np.ndarray:
        """Os coeficientes na escala das entradas originais (sem a padronização)."""
        return self.coeficientes / self._desvio


def _limites_iniciais(y: np.ndarray) -> np.ndarray:
    acumulada = np.clip(np.array([(y <= 0).mean(), (y <= 1).mean()]), 0.01, 0.99)
    limite_0, limite_1 = logit(acumulada)
    return np.array([limite_0, np.log(max(limite_1 - limite_0, 0.1))])
