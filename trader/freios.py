"""Freios da carteira própria (pré-registro quant v0.1, seção 6; ADR 0118, Emenda 1, itens 5 e 6).

- **Por camada:** a camada que cai 40% do próprio pico vai para CDI no pregão seguinte.
- **Global:** a carteira inteira que cai 35% do pico vai toda para CDI no pregão seguinte; ao vivo, só
  volta com revisão escrita do Tiago.
- **No backtest**, a camada (ou a carteira) freada volta no primeiro pregão 12 meses depois do disparo,
  e o pico recomeça do valor daquele dia (senão o freio dispararia de novo na volta).

O freio decide com o fechamento do dia e só sai no pregão seguinte: o dia do disparo ainda rende o
retorno da camada. Nada aqui olha o futuro (há teste de que cortar o futuro não muda o passado).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from trader import criterio_quant

FREIO_POR_CAMADA = criterio_quant.FREIO_POR_CAMADA
FREIO_GLOBAL = criterio_quant.FREIO_GLOBAL
MESES_DE_VOLTA = criterio_quant.MESES_DE_VOLTA_DO_FREIO
TOLERANCIA_DOS_PESOS = 1e-9


@dataclass(frozen=True)
class Freio:
    """Uma camada (ou a carteira) com o freio aplicado."""

    retorno: pd.Series  # o retorno diário depois do freio (CDI nos dias freados)
    em_cdi: pd.Series  # True nos dias em que rendeu CDI
    disparos: tuple[pd.Timestamp, ...]  # dias cujo fechamento cruzou o limite
    saidas: tuple[
        pd.Timestamp, ...
    ]  # primeiros dias em CDI (o pregão seguinte a cada disparo)
    voltas: tuple[
        pd.Timestamp, ...
    ]  # primeiros pregões 12 meses depois de cada disparo
    limite: float


@dataclass(frozen=True)
class CarteiraFreada:
    """A soma das camadas, cada uma com o freio de 40%, e o freio global de 35% por cima."""

    retorno: pd.Series
    sem_freio: pd.Series
    camadas: dict[str, Freio]
    global_: Freio


def _cdi_alinhado(cdi: pd.Series, indice: pd.Index) -> np.ndarray:
    alinhado = cdi.reindex(indice)
    if alinhado.isna().any():
        faltando = alinhado.index[alinhado.isna()][0]
        raise ValueError(f"CDI faltando em {faltando.date()}")
    return alinhado.to_numpy(dtype=float)


def aplicar_freio(
    retorno: pd.Series,
    cdi: pd.Series,
    limite: float = FREIO_POR_CAMADA,
    meses_de_volta: int = MESES_DE_VOLTA,
) -> Freio:
    """Troca por CDI os dias entre o pregão seguinte ao disparo e a véspera da volta."""
    datas = retorno.index
    proprio = retorno.to_numpy(dtype=float)
    cdi_do_dia = _cdi_alinhado(cdi, datas)
    saida = np.empty(len(datas))
    em_cdi = np.zeros(len(datas), dtype=bool)
    disparos: list[pd.Timestamp] = []
    voltas: list[pd.Timestamp] = []
    indice = pico = 1.0
    volta_em: pd.Timestamp | None = None
    for posicao, dia in enumerate(datas):
        if volta_em is not None and dia >= volta_em:
            volta_em = None
            voltas.append(dia)
            pico = indice
        freado = volta_em is not None
        rendimento = cdi_do_dia[posicao] if freado else proprio[posicao]
        indice *= 1 + rendimento
        saida[posicao] = rendimento
        em_cdi[posicao] = freado
        if not freado:
            pico = max(pico, indice)
            if indice / pico - 1 <= -limite:
                disparos.append(dia)
                volta_em = dia + pd.DateOffset(months=meses_de_volta)
    saidas = tuple(
        datas[posicao + 1]
        for posicao in (datas.get_loc(d) for d in disparos)
        if posicao + 1 < len(datas)
    )
    return Freio(
        retorno=pd.Series(saida, index=datas, name=retorno.name),
        em_cdi=pd.Series(em_cdi, index=datas),
        disparos=tuple(disparos),
        saidas=saidas,
        voltas=tuple(voltas),
        limite=limite,
    )


def _conferir_pesos(pesos: Mapping[str, float], camadas: pd.DataFrame) -> None:
    if set(pesos) != set(camadas.columns):
        raise ValueError(
            f"os pesos {sorted(pesos)} não casam com as camadas {sorted(camadas.columns)}"
        )
    if abs(sum(pesos.values()) - 1) > TOLERANCIA_DOS_PESOS:
        raise ValueError("os pesos das camadas precisam somar 1")


def freiar_carteira(
    camadas: pd.DataFrame,
    pesos: Mapping[str, float],
    cdi: pd.Series,
    limite_da_camada: float = FREIO_POR_CAMADA,
    limite_global: float = FREIO_GLOBAL,
    meses_de_volta: int = MESES_DE_VOLTA,
) -> CarteiraFreada:
    """Freio de 40% em cada camada e, sobre a soma com os pesos fixos, o freio global de 35%.

    Os pesos são refeitos todo dia (simplificação declarada: a carteira montada no PR 9 vai
    rebalancear no calendário dela).
    """
    _conferir_pesos(pesos, camadas)
    freios = {
        nome: aplicar_freio(camadas[nome], cdi, limite_da_camada, meses_de_volta)
        for nome in camadas.columns
    }
    sem_freio = sum(camadas[nome] * peso for nome, peso in pesos.items())
    soma = sum(freios[nome].retorno * peso for nome, peso in pesos.items())
    global_ = aplicar_freio(
        pd.Series(soma, index=camadas.index), cdi, limite_global, meses_de_volta
    )
    return CarteiraFreada(
        retorno=global_.retorno,
        sem_freio=pd.Series(sem_freio, index=camadas.index),
        camadas=freios,
        global_=global_,
    )
