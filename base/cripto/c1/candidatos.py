"""Os dois candidatos do modelo C-1 (pré-registro v2, seção 6). Cada um conta como uma tentativa.

1. **Logística ordinal com L2**, com a força da regularização escolhida por validação **dentro** de
   cada janela de treino (os últimos 20% do treino, depois de um intervalo de 30 dias).
2. **Árvores com reforço rasas**, com os parâmetros fixos do pré-registro (sem busca).

Os dois usam só as colunas da lista fechada (`entradas.COLUNAS`), nunca o `alvo` do quadro.
**Esclarecimento de implementação (13/10/2026, antes de qualquer resultado):** as faixas são
relativas (o limite entre calmo e agitado muda com o tempo), então as volatilidades do preço entram
medidas contra o centro das faixas do dia (log da volatilidade sobre a média geométrica dos dois
limites); é a mesma informação, na escala em que a pergunta é feita. Buraco numa entrada vira a
mediana dela no treino.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier

from base.cripto.c1.entradas import COLUNAS
from base.cripto.c1.medidas import brier
from base.cripto.c1.ordinal import LogisticaOrdinal

FAIXAS = 3
COLUNAS_DE_VOLATILIDADE = ["vol_1", "vol_7", "vol_30", "vol_90"]
PISO_DA_VOLATILIDADE = 1e-6
GRADE_DA_REGULARIZACAO = (0.01, 0.1, 1.0, 10.0, 100.0)
FRACAO_DE_VALIDACAO = 0.2
DIAS_DE_INTERVALO = 30


def preparar_entradas(quadro: pd.DataFrame) -> pd.DataFrame:
    """As colunas da lista fechada, com as volatilidades medidas contra o centro das faixas."""
    entradas = quadro[COLUNAS].astype(float)
    centro = np.sqrt(quadro["limite_inferior"] * quadro["limite_superior"])
    for coluna in COLUNAS_DE_VOLATILIDADE:
        entradas[coluna] = np.log(
            np.maximum(entradas[coluna], PISO_DA_VOLATILIDADE) / centro
        )
    return entradas


class _ComMediana:
    """Guarda a mediana de cada entrada no treino e a usa nos buracos."""

    def __init__(self) -> None:
        self.medianas = pd.Series(dtype=float)

    def _treino(self, quadro: pd.DataFrame) -> np.ndarray:
        entradas = preparar_entradas(quadro)
        self.medianas = entradas.median().fillna(0.0)
        return entradas.fillna(self.medianas).to_numpy()

    def _previsao(self, quadro: pd.DataFrame) -> np.ndarray:
        return preparar_entradas(quadro).fillna(self.medianas).to_numpy()


class LogisticaComValidacao(_ComMediana):
    """Candidato 1: logística ordinal com L2; a força escolhida dentro da janela de treino."""

    def __init__(self) -> None:
        super().__init__()
        self.c = GRADE_DA_REGULARIZACAO[0]
        self.modelo = LogisticaOrdinal(self.c)

    def ajustar(
        self, quadro: pd.DataFrame, classes: pd.Series
    ) -> "LogisticaComValidacao":
        x, y = self._treino(quadro), classes.to_numpy(dtype=int)
        self.c = self._escolher_c(x, y)
        self.modelo = LogisticaOrdinal(self.c).ajustar(x, y)
        return self

    def probabilidades(self, quadro: pd.DataFrame) -> np.ndarray:
        return self.modelo.probabilidades(self._previsao(quadro))

    @staticmethod
    def _escolher_c(x: np.ndarray, y: np.ndarray) -> float:
        inicio_da_validacao = int(len(x) * (1 - FRACAO_DE_VALIDACAO))
        fim_do_treino = inicio_da_validacao - DIAS_DE_INTERVALO
        erros = {
            c: brier(
                LogisticaOrdinal(c)
                .ajustar(x[:fim_do_treino], y[:fim_do_treino])
                .probabilidades(x[inicio_da_validacao:]),
                y[inicio_da_validacao:],
            )
            for c in GRADE_DA_REGULARIZACAO
        }
        return min(erros, key=lambda c: erros[c])


class ArvoresComReforco(_ComMediana):
    """Candidato 2: árvores com reforço, parâmetros fixos do pré-registro."""

    def __init__(self) -> None:
        super().__init__()
        self.modelo = GradientBoostingClassifier(
            max_depth=3, n_estimators=200, learning_rate=0.05, random_state=0
        )

    def ajustar(self, quadro: pd.DataFrame, classes: pd.Series) -> "ArvoresComReforco":
        self.modelo.fit(self._treino(quadro), classes.to_numpy(dtype=int))
        return self

    def probabilidades(self, quadro: pd.DataFrame) -> np.ndarray:
        # uma faixa que não apareceu no treino fica com probabilidade 0
        saida = np.zeros((len(quadro), FAIXAS))
        faixas_do_treino = np.asarray(self.modelo.classes_, dtype=int)
        saida[:, faixas_do_treino] = self.modelo.predict_proba(self._previsao(quadro))
        return saida
