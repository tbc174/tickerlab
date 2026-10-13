"""As três réguas que o modelo C-1 tem de vencer (pré-registro v2, seção 5).

Todas recebem o "quadro" do dia (as entradas, os limites das faixas e, só no treino, o `alvo`
contínuo) e devolvem P(calmo), P(normal), P(agitado).

- **R0, frequência:** a proporção de cada faixa nos últimos 1.095 dias do treino.
- **R1, persistência:** a faixa dos próximos 30 dias é a dos últimos 30 (probabilidade 1 nela).
- **R2, HAR** (Corsi, 2009), **a régua principal:** regressão do log da volatilidade dos próximos
  30 dias sobre o log das volatilidades de 1, 7 e 30 dias (só o preço), convertida nas três faixas
  por uma logística ordinal sobre a previsão medida contra os limites do dia.
"""

import numpy as np
import pandas as pd

from base.cripto.c1.ordinal import LogisticaOrdinal

DIAS_DA_FREQUENCIA = 1_095
FAIXAS = 3
COLUNAS_DO_HAR = ["vol_1", "vol_7", "vol_30"]
# a volatilidade de 1 dia é o retorno absoluto, que pode ser zero: um piso para o log
PISO_DA_VOLATILIDADE = 1e-6
# a conversão em faixas não precisa de regularização
SEM_REGULARIZACAO = 1e6


class Frequencia:
    """R0: a proporção de cada faixa nos últimos 1.095 dias do treino."""

    def __init__(self) -> None:
        self.proporcoes = np.full(FAIXAS, 1 / FAIXAS)

    def ajustar(self, quadro: pd.DataFrame, classes: pd.Series) -> "Frequencia":
        contagem = np.bincount(
            np.asarray(classes.tail(DIAS_DA_FREQUENCIA), dtype=int), minlength=FAIXAS
        )
        self.proporcoes = contagem / contagem.sum()
        return self

    def probabilidades(self, quadro: pd.DataFrame) -> np.ndarray:
        return np.tile(self.proporcoes, (len(quadro), 1))


class Persistencia:
    """R1: a faixa dos últimos 30 dias, pelos limites do dia; não aprende nada."""

    def ajustar(self, quadro: pd.DataFrame, classes: pd.Series) -> "Persistencia":
        return self

    def probabilidades(self, quadro: pd.DataFrame) -> np.ndarray:
        faixa = np.where(
            quadro["vol_30"] < quadro["limite_inferior"],
            0,
            np.where(quadro["vol_30"] < quadro["limite_superior"], 1, 2),
        )
        return np.eye(FAIXAS)[faixa]


class Har:
    """R2: HAR só com o preço, convertido nas faixas por uma logística ordinal."""

    def __init__(self) -> None:
        self.coeficientes = np.zeros(len(COLUNAS_DO_HAR) + 1)
        self.conversao = LogisticaOrdinal(c=SEM_REGULARIZACAO)

    def ajustar(self, quadro: pd.DataFrame, classes: pd.Series) -> "Har":
        x = _com_constante(_log_das_volatilidades(quadro))
        self.coeficientes, *_ = np.linalg.lstsq(
            x, np.log(quadro["alvo"].to_numpy()), rcond=None
        )
        self.conversao.ajustar(self._contra_os_limites(quadro), classes.to_numpy())
        return self

    def probabilidades(self, quadro: pd.DataFrame) -> np.ndarray:
        return self.conversao.probabilidades(self._contra_os_limites(quadro))

    def _contra_os_limites(self, quadro: pd.DataFrame) -> np.ndarray:
        previsao = _com_constante(_log_das_volatilidades(quadro)) @ self.coeficientes
        return np.column_stack(
            [
                previsao - np.log(quadro["limite_inferior"]),
                previsao - np.log(quadro["limite_superior"]),
            ]
        )


def _log_das_volatilidades(quadro: pd.DataFrame) -> np.ndarray:
    return np.log(
        np.maximum(quadro[COLUNAS_DO_HAR].to_numpy(dtype=float), PISO_DA_VOLATILIDADE)
    )


def _com_constante(x: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(len(x)), x])
