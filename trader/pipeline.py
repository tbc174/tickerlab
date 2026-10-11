"""Pipeline da M2: um modelo treinado em cada uma das 45 divisões do CPCV, só no desenvolvimento.

Para cada divisão:
1. treina um modelo único para todos os ativos (painel) nas datas de treino (já sem expurgo e
   embargo), com as linhas que têm rótulo e atributos completos;
2. prevê a probabilidade de alta nas datas de teste; o sinal é (2p − 1) reescalado para que a média
   absoluta do sinal no treino seja 0,5 (como a previsão 10 de 20 da B1), limitado a ±1;
3. transforma o sinal em posição (volatilidade alvo, teto e buffer) e faz o backtest de cada ativo
   com custos ×1 e ×2, guardando só as datas de teste.
Depois junta tudo nos 9 caminhos.

Desempenho: o que não depende da divisão (volatilidade, escala da posição, custos e carry) é
calculado uma vez por ativo (`preparar_ativos`); o buffer roda compilado pelo numba e o backtest
usa o mesmo núcleo numpy de `trader.backtest`; os treinos das 45 divisões rodam em paralelo
(joblib, processos separados).

Variantes (seção 8 do critério): "normal"; "futuro" (atributos de amanhã, para provar que olhar o
futuro infla o resultado); "embaralhado" (rótulos de treino sorteados, para provar que sem relação o
resultado some).

Calendário: os grupos do CPCV são de dias úteis. Uma data de fim de semana (só cripto) pertence ao
grupo do dia útil seguinte; na carteira, o fim de semana é composto na segunda-feira.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from trader import atributos as atr
from trader import avaliacao, modelos
from trader.backtest import calcular_nucleo, dias_corridos
from trader.custos import custos_do_ativo
from trader.posicao import (
    ALVO_PADRAO,
    LARGURA_DO_BUFFER,
    TETO_PADRAO,
    buffer_numpy,
    volatilidade_mista,
)
from trader.validacao import CPCV

MEDIA_ABSOLUTA_DO_SINAL = 0.5
MULTIPLICADORES = (1.0, 2.0)
TRABALHADORES = max(1, min(8, (os.cpu_count() or 2) - 2))


@dataclass(frozen=True)
class Configuracao:
    nome: str
    modelo: str  # "logistica", "floresta" ou "lightgbm"
    ajustes: dict[str, Any] = field(default_factory=dict)
    atributos: tuple[str, ...] = atr.ATRIBUTOS
    horizonte: int = atr.HORIZONTE_DO_ROTULO
    semente: int = 0

    @property
    def familia(self) -> str:
        return modelos.FAMILIA[self.modelo]

    def especificacao(self, extras: dict | None = None) -> dict:
        dados = asdict(self)
        dados["atributos"] = list(self.atributos)
        dados["parametros"] = modelos.parametros(self.modelo, self.ajustes)
        dados["sinal"] = {"media_absoluta": MEDIA_ABSOLUTA_DO_SINAL}
        return {"tipo": "modelo", **dados, **(extras or {})}


@dataclass
class ResultadoDoPipeline:
    caminhos: list[pd.Series]
    caminhos_x2: list[pd.Series]
    por_ativo: list[dict[str, pd.Series]]  # por caminho, retornos de cada ativo (×1)
    posicoes: list[pd.DataFrame]  # por caminho, posição desejada (datas × ativos)
    retornos_dos_ativos: pd.DataFrame  # retornos limpos (datas × ativos)
    custo_por_lado: pd.Series  # por ativo, sem swap (para o teste contra o acaso)


@dataclass(frozen=True)
class PreparoDoAtivo:
    """O que não depende da divisão do CPCV: calculado uma vez por ativo e reaproveitado."""

    simbolo: str
    indice: pd.DatetimeIndex
    retorno: np.ndarray
    escala: (
        np.ndarray
    )  # alvo ÷ volatilidade (vazio quando a volatilidade é desconhecida)
    meia_faixa: np.ndarray  # largura do buffer × posição de sinal cheio
    custo_por_lado: dict[float, np.ndarray]  # por multiplicador de custo (1 e 2)
    swap_comprado: dict[float, np.ndarray]
    swap_vendido: dict[float, np.ndarray]
    dias: np.ndarray

    def posicao(self, sinal: np.ndarray) -> np.ndarray:
        """O mesmo que `posicao.dimensionar`, sem refazer a volatilidade a cada divisão."""
        ideal = np.clip(np.clip(sinal, -1, 1) * self.escala, -TETO_PADRAO, TETO_PADRAO)
        return buffer_numpy(np.nan_to_num(ideal, nan=0.0), self.meia_faixa)

    def retorno_liquido(
        self, posicao_desejada: np.ndarray, multiplicador: float
    ) -> np.ndarray:
        return calcular_nucleo(
            posicao_desejada,
            self.retorno,
            self.custo_por_lado[multiplicador],
            self.swap_comprado[multiplicador],
            self.swap_vendido[multiplicador],
            self.dias,
        )["retorno"]


def preparar_ativos(
    series: list, taxas: pd.DataFrame | None
) -> dict[str, PreparoDoAtivo]:
    preparos = {}
    for s in series:
        indice = s.retorno.index
        vol = volatilidade_mista(s.retorno, dias_por_ano=s.dias_por_ano)
        escala = (ALVO_PADRAO / vol).where(vol > 0).to_numpy(dtype=float)
        cheia = np.nan_to_num(np.clip(escala, -TETO_PADRAO, TETO_PADRAO), nan=0.0)
        custos = {
            m: custos_do_ativo(s.ativo, m, taxas, indice) for m in MULTIPLICADORES
        }
        swaps = {m: custos[m].swaps(indice) for m in MULTIPLICADORES}
        preparos[s.ativo.simbolo] = PreparoDoAtivo(
            simbolo=s.ativo.simbolo,
            indice=indice,
            retorno=s.retorno.fillna(0.0).to_numpy(dtype=float),
            escala=escala,
            meia_faixa=LARGURA_DO_BUFFER * np.abs(cheia),
            custo_por_lado={
                m: custos[m].custo_por_lado(indice).to_numpy(dtype=float)
                for m in MULTIPLICADORES
            },
            swap_comprado={
                m: swaps[m][0].to_numpy(dtype=float) for m in MULTIPLICADORES
            },
            swap_vendido={
                m: swaps[m][1].to_numpy(dtype=float) for m in MULTIPLICADORES
            },
            dias=dias_corridos(indice),
        )
    return preparos


def dias_uteis(painel: pd.DataFrame) -> pd.DatetimeIndex:
    datas = pd.DatetimeIndex(painel["Date"].unique()).sort_values()
    return datas[datas.weekday < 5]


def _dia_util_de(datas: pd.DatetimeIndex, uteis: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Cada data vira ela mesma (se útil) ou o próximo dia útil."""
    posicoes = np.searchsorted(uteis.to_numpy(), datas.to_numpy())
    posicoes = np.clip(posicoes, 0, len(uteis) - 1)
    return uteis[posicoes]


def preparar_variante(painel: pd.DataFrame, variante: str) -> pd.DataFrame:
    if variante not in ("normal", "futuro", "embaralhado"):
        raise ValueError(f"Variante desconhecida: {variante}")
    if variante != "futuro":
        return painel
    deslocado = painel.sort_values(["simbolo", "Date"]).copy()
    colunas = list(atr.ATRIBUTOS_DO_ATIVO) + list(atr.ATRIBUTOS_MACRO)
    deslocado[colunas] = deslocado.groupby("simbolo")[colunas].shift(
        -1
    )  # olha o amanhã
    return deslocado


def _escala_do_sinal(p_treino: np.ndarray) -> float:
    media = float(np.mean(np.abs(2 * p_treino - 1)))
    return media / MEDIA_ABSOLUTA_DO_SINAL if media > 0 else 1.0


def _treinar_e_prever(
    tipo: str,
    ajustes: dict[str, Any],
    semente: int,
    x: np.ndarray,
    y: np.ndarray,
    treino: np.ndarray,
    teste: np.ndarray,
    completos: np.ndarray,
    embaralhar_com: int | None,
) -> tuple[np.ndarray, float]:
    """Treina numa divisão e devolve (probabilidade nas linhas de teste, escala do sinal).

    Função de módulo para o joblib conseguir mandá-la a outro processo. `x` e `y` são o painel
    inteiro (o joblib grava uma vez em disco e os processos leem sem copiar).
    """
    y_treino = y[treino]
    if embaralhar_com is not None:
        y_treino = np.random.default_rng(embaralhar_com).permutation(y_treino)
    modelo = modelos.criar(tipo, ajustes, semente)
    modelo.fit(x[treino], y_treino)
    escala = _escala_do_sinal(modelo.predict_proba(x[treino])[:, 1])
    p = np.full(teste.shape[0], 0.5)
    prever = completos[teste]
    if prever.any():
        p[prever] = modelo.predict_proba(x[teste[prever]])[:, 1]
    return p, escala


def rodar(
    config: Configuracao,
    painel: pd.DataFrame,
    series: list,
    taxas: pd.DataFrame | None,
    variante: str = "normal",
    cpcv: CPCV | None = None,
    progresso: bool = False,
    preparos: dict[str, PreparoDoAtivo] | None = None,
    trabalhadores: int = TRABALHADORES,
) -> ResultadoDoPipeline:
    """Roda a configuração nas 45 divisões e monta os 9 caminhos.

    `preparos` (de `preparar_ativos`) pode ser reaproveitado entre variantes. `trabalhadores`:
    processos em paralelo para treinar as divisões (1 = sem paralelismo).
    """
    cpcv = cpcv or CPCV()
    preparos = preparos or preparar_ativos(series, taxas)
    dados = preparar_variante(painel, variante).reset_index(drop=True)
    colunas = list(config.atributos)
    uteis = dias_uteis(dados)
    dia_util = _dia_util_de(pd.DatetimeIndex(dados["Date"]), uteis)
    x = dados[colunas].to_numpy(dtype=float)
    y = dados["y"].to_numpy(dtype=float)
    completos = ~np.isnan(x).any(axis=1)
    tem_rotulo = ~np.isnan(y)
    divisoes = cpcv.divisoes(uteis)
    indices = []
    for d in divisoes:
        treino = np.flatnonzero(dia_util.isin(d.treino) & completos & tem_rotulo)
        teste = np.flatnonzero(dia_util.isin(d.teste))
        indices.append((treino, teste))
    tarefas = [
        delayed(_treinar_e_prever)(
            config.modelo,
            config.ajustes,
            config.semente,
            x,
            y,
            treino,
            teste,
            completos,
            config.semente * 1000 + d.numero if variante == "embaralhado" else None,
        )
        for d, (treino, teste) in zip(divisoes, indices, strict=True)
    ]
    if progresso:
        print(
            f"  treinando {len(tarefas)} divisões em {trabalhadores} processos...",
            flush=True,
        )
    saidas = Parallel(n_jobs=trabalhadores, backend="loky")(tarefas)

    datas = pd.DatetimeIndex(dados["Date"])
    simbolos = dados["simbolo"].to_numpy()
    retornos_por_divisao: dict[int, pd.Series] = {}
    retornos_por_divisao_x2: dict[int, pd.Series] = {}
    ativos_por_divisao: dict[int, dict[str, pd.Series]] = {}
    posicoes_por_divisao: dict[int, dict[str, pd.Series]] = {}
    for d, (_, teste), (p, escala) in zip(divisoes, indices, saidas, strict=True):
        sinal_do_teste = np.clip((2 * p - 1) / escala, -1, 1)
        simbolos_do_teste = simbolos[teste]
        retornos_x1, retornos_x2, posicoes = {}, {}, {}
        for simbolo in np.unique(simbolos_do_teste):
            prep = preparos[simbolo]
            deste = simbolos_do_teste == simbolo
            datas_de_teste = datas[teste[deste]]
            sinal = (
                pd.Series(sinal_do_teste[deste], index=datas_de_teste)
                .reindex(prep.indice)
                .fillna(0.0)
                .to_numpy()
            )
            posicao = prep.posicao(sinal)
            onde = prep.indice.get_indexer(datas_de_teste)
            retornos_x1[simbolo] = pd.Series(
                prep.retorno_liquido(posicao, 1.0)[onde], index=datas_de_teste
            )
            retornos_x2[simbolo] = pd.Series(
                prep.retorno_liquido(posicao, 2.0)[onde], index=datas_de_teste
            )
            posicoes[simbolo] = pd.Series(posicao[onde], index=datas_de_teste)
        n = d.numero
        retornos_por_divisao[n] = avaliacao.retorno_da_carteira(
            avaliacao.montar_carteira(retornos_x1)
        )
        retornos_por_divisao_x2[n] = avaliacao.retorno_da_carteira(
            avaliacao.montar_carteira(retornos_x2)
        )
        ativos_por_divisao[n] = retornos_x1
        posicoes_por_divisao[n] = posicoes

    caminhos = cpcv.montar_caminhos(uteis, retornos_por_divisao)
    caminhos_x2 = cpcv.montar_caminhos(uteis, retornos_por_divisao_x2)
    grupos = cpcv.grupos(uteis)
    fronteiras = [g[-1] for g in grupos]

    def _no_grupo(serie: pd.Series, g: int) -> pd.Series:
        inicio = fronteiras[g - 1] if g > 0 else pd.Timestamp.min
        return serie[(serie.index > inicio) & (serie.index <= fronteiras[g])]

    por_ativo, posicoes_por_caminho = [], []
    for mapa in cpcv.caminhos():
        ativos: dict[str, list[pd.Series]] = {}
        pos: dict[str, list[pd.Series]] = {}
        for g, n in mapa.items():
            for simbolo, r in ativos_por_divisao[n].items():
                ativos.setdefault(simbolo, []).append(_no_grupo(r, g))
                pos.setdefault(simbolo, []).append(
                    _no_grupo(posicoes_por_divisao[n][simbolo], g)
                )
        por_ativo.append({k: pd.concat(v).sort_index() for k, v in ativos.items()})
        posicoes_por_caminho.append(
            pd.concat(
                {k: pd.concat(v).sort_index() for k, v in pos.items()},
                axis=1,
                sort=True,
            )
        )

    retornos_dos_ativos = pd.concat(
        {s.ativo.simbolo: s.retorno for s in series}, axis=1, sort=True
    ).reindex(posicoes_por_caminho[0].index)
    custo_por_lado = pd.Series(
        {
            simbolo: float(prep.custo_por_lado[1.0][0])
            for simbolo, prep in preparos.items()
        }
    )
    return ResultadoDoPipeline(
        caminhos,
        caminhos_x2,
        por_ativo,
        posicoes_por_caminho,
        retornos_dos_ativos[posicoes_por_caminho[0].columns],
        custo_por_lado,
    )


def dados_do_acaso(
    resultado: ResultadoDoPipeline, caminho: int
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """Posições do caminho e retornos dos ativos nas mesmas datas e colunas (para o A10)."""
    posicoes = resultado.posicoes[caminho].sort_index().sort_index(axis=1)
    retornos = resultado.retornos_dos_ativos.reindex(
        index=posicoes.index, columns=posicoes.columns
    )
    return posicoes, retornos, resultado.custo_por_lado.reindex(posicoes.columns)
