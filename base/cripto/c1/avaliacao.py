"""Validação do modelo C-1 (pré-registro v2, seção 7): *walk-forward*, calibração e estabilidade.

- **Walk-forward:** janela de treino que cresce, novo treino a cada mês (ou a cada `meses_entre_treinos`).
  **Intervalo de 30 dias:** o alvo do dia D é a volatilidade de D+1 a D+30; para o teste que começa em
  T, só entram no treino os dias D com D + 31 <= T (o alvo já tinha terminado). Sem isso, o treino veria
  o futuro do teste.
- **Calibração:** erro médio de calibração da faixa mais provável (10 caixas de confiança).
- **Estabilidade:** o ganho médio sobre a régua em cada ano.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Protocol

import numpy as np
import pandas as pd

from base.cripto.c1.alvo import DIAS_DO_ALVO

CAIXAS_DA_CALIBRACAO = 10


class Modelo(Protocol):
    """O que o *walk-forward* precisa de um modelo (réguas e candidatos)."""

    def ajustar(self, quadro: pd.DataFrame, classes: pd.Series) -> "Modelo": ...
    def probabilidades(self, quadro: pd.DataFrame) -> np.ndarray: ...


@dataclass
class ResultadoWalkForward:
    """As faixas reais dos dias de teste e as probabilidades de cada modelo nesses dias."""

    classes: pd.Series
    probabilidades: dict[str, pd.DataFrame] = field(default_factory=dict)
    inicio: date | None = None
    fim: date | None = None
    meses_entre_treinos: int = 1


def walk_forward(
    quadro: pd.DataFrame,
    classes: pd.Series,
    fabricas: dict[str, Callable[[], Modelo]],
    inicio: date,
    fim: date,
    meses_entre_treinos: int = 1,
) -> ResultadoWalkForward:
    """Treina cada modelo no passado (com o intervalo de 30 dias) e prevê cada bloco de meses."""
    indice = pd.Index(quadro.index)
    com_classe = classes.notna()
    previsoes: dict[str, list[pd.DataFrame]] = {nome: [] for nome in fabricas}
    dias_de_teste: list[pd.Series] = []
    for comeco, final in _blocos(inicio, fim, meses_entre_treinos):
        treino = com_classe & (indice <= comeco - timedelta(days=DIAS_DO_ALVO + 1))
        teste = com_classe & (indice >= comeco) & (indice <= final)
        if not treino.any() or not teste.any():
            continue
        dias_de_teste.append(classes[teste].astype(int))
        for nome, fabrica in fabricas.items():
            modelo = fabrica().ajustar(quadro[treino], classes[treino].astype(int))
            previsoes[nome].append(
                pd.DataFrame(
                    modelo.probabilidades(quadro[teste]), index=quadro.index[teste]
                )
            )
    return ResultadoWalkForward(
        classes=pd.concat(dias_de_teste),
        probabilidades={nome: pd.concat(partes) for nome, partes in previsoes.items()},
        inicio=inicio,
        fim=fim,
        meses_entre_treinos=meses_entre_treinos,
    )


def calibracao(probabilidades: np.ndarray, classes: np.ndarray) -> float:
    """Erro médio de calibração da faixa mais provável: em cada caixa de confiança, a distância
    entre a confiança média e a fração de acertos, pesada pelo tamanho da caixa."""
    probabilidades = np.asarray(probabilidades)
    confianca = probabilidades.max(axis=1)
    acerto = probabilidades.argmax(axis=1) == np.asarray(classes)
    caixa = np.minimum(
        (confianca * CAIXAS_DA_CALIBRACAO).astype(int), CAIXAS_DA_CALIBRACAO - 1
    )
    erro = 0.0
    for numero in np.unique(caixa):
        dentro = caixa == numero
        erro += dentro.mean() * abs(acerto[dentro].mean() - confianca[dentro].mean())
    return float(erro)


def estabilidade_por_ano(ganho_por_dia: pd.Series) -> dict[int, float]:
    """O ganho médio sobre a régua em cada ano do período avaliado."""
    anos = pd.Index([dia.year for dia in ganho_por_dia.index])
    return {
        int(ano): float(valor)
        for ano, valor in ganho_por_dia.groupby(anos).mean().items()
    }


def _blocos(inicio: date, fim: date, meses: int) -> list[tuple[date, date]]:
    comecos = pd.date_range(
        pd.Timestamp(inicio).to_period("M").to_timestamp(), fim, freq=f"{meses}MS"
    )
    blocos = []
    for comeco in comecos:
        proximo = (comeco + pd.DateOffset(months=meses)).date()
        blocos.append(
            (max(comeco.date(), inicio), min(proximo - timedelta(days=1), fim))
        )
    return blocos
