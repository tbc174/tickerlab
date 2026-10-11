"""Pipeline da M2: um modelo treinado em cada uma das 45 divisões do CPCV, só no desenvolvimento.

Para cada divisão:
1. treina um modelo único para todos os ativos (painel) nas datas de treino (já sem expurgo e
   embargo), com as linhas que têm rótulo e atributos completos;
2. prevê a probabilidade de alta nas datas de teste; o sinal é (2p − 1) reescalado para que a média
   absoluta do sinal no treino seja 0,5 (como a previsão 10 de 20 da B1), limitado a ±1;
3. transforma o sinal em posição (volatilidade alvo, teto e buffer) e faz o backtest de cada ativo
   com custos ×1 e ×2, guardando só as datas de teste.
Depois junta tudo nos 9 caminhos.

Variantes (seção 8 do critério): "normal"; "futuro" (atributos de amanhã, para provar que olhar o
futuro infla o resultado); "embaralhado" (rótulos de treino sorteados, para provar que sem relação o
resultado some).

Calendário: os grupos do CPCV são de dias úteis. Uma data de fim de semana (só cripto) pertence ao
grupo do dia útil seguinte; na carteira, o fim de semana é composto na segunda-feira.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from trader import atributos as atr
from trader import avaliacao, modelos
from trader.backtest import executar_backtest
from trader.baselines import preco_sintetico
from trader.custos import custos_do_ativo
from trader.posicao import TETO_PADRAO, dimensionar
from trader.validacao import CPCV

MEDIA_ABSOLUTA_DO_SINAL = 0.5


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


def rodar(
    config: Configuracao,
    painel: pd.DataFrame,
    series: list,
    taxas: pd.DataFrame | None,
    variante: str = "normal",
    cpcv: CPCV | None = None,
    progresso: bool = False,
) -> ResultadoDoPipeline:
    """Roda a configuração nas 45 divisões e monta os 9 caminhos."""
    cpcv = cpcv or CPCV()
    dados = preparar_variante(painel, variante)
    colunas = list(config.atributos)
    uteis = dias_uteis(dados)
    dia_util = _dia_util_de(pd.DatetimeIndex(dados["Date"]), uteis)
    completos = dados[colunas].notna().all(axis=1).to_numpy()
    tem_rotulo = dados["y"].notna().to_numpy()
    por_simbolo = {s.ativo.simbolo: s for s in series}
    gerador = np.random.default_rng(config.semente)

    retornos_por_divisao: dict[int, pd.Series] = {}
    retornos_por_divisao_x2: dict[int, pd.Series] = {}
    ativos_por_divisao: dict[int, dict[str, pd.Series]] = {}
    posicoes_por_divisao: dict[int, dict[str, pd.Series]] = {}

    for divisao in cpcv.divisoes(uteis):
        no_treino = dia_util.isin(divisao.treino) & completos & tem_rotulo
        no_teste = dia_util.isin(divisao.teste)
        y = dados.loc[no_treino, "y"].to_numpy()
        if variante == "embaralhado":
            y = gerador.permutation(y)
        modelo = modelos.criar(config.modelo, config.ajustes, config.semente)
        x_treino = dados.loc[no_treino, colunas].to_numpy(dtype=float)
        modelo.fit(x_treino, y)
        escala = _escala_do_sinal(modelo.predict_proba(x_treino)[:, 1])

        teste = dados.loc[no_teste, ["Date", "simbolo"]].copy()
        p = np.full(len(teste), 0.5)
        prever = completos[no_teste]
        if prever.any():
            p[prever] = modelo.predict_proba(
                dados.loc[no_teste, colunas].to_numpy(dtype=float)[prever]
            )[:, 1]
        teste["sinal"] = np.clip((2 * p - 1) / escala, -1, 1)

        retornos_x1, retornos_x2, posicoes = {}, {}, {}
        for simbolo, linhas in teste.groupby("simbolo"):
            serie = por_simbolo[simbolo]
            sinal = (
                pd.Series(
                    linhas["sinal"].to_numpy(), index=pd.DatetimeIndex(linhas["Date"])
                )
                .reindex(serie.retorno.index)
                .fillna(0.0)
            )
            posicao = dimensionar(sinal, serie.retorno, dias_por_ano=serie.dias_por_ano)
            datas_de_teste = pd.DatetimeIndex(linhas["Date"])
            for mult, destino in ((1.0, retornos_x1), (2.0, retornos_x2)):
                resultado = executar_backtest(
                    preco_sintetico(serie.retorno),
                    posicao,
                    custos_do_ativo(serie.ativo, mult, taxas, serie.retorno.index),
                    limite=TETO_PADRAO,
                    retorno_do_ativo=serie.retorno,
                    com_operacoes=False,
                )
                destino[simbolo] = resultado.retorno.reindex(datas_de_teste)
            posicoes[simbolo] = posicao.reindex(datas_de_teste)
        n = divisao.numero
        retornos_por_divisao[n] = avaliacao.retorno_da_carteira(
            avaliacao.montar_carteira(retornos_x1)
        )
        retornos_por_divisao_x2[n] = avaliacao.retorno_da_carteira(
            avaliacao.montar_carteira(retornos_x2)
        )
        ativos_por_divisao[n] = retornos_x1
        posicoes_por_divisao[n] = posicoes
        if progresso:
            print(f"  divisão {n + 1}/{cpcv.n_divisoes}", flush=True)

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
            s.ativo.simbolo: float(
                custos_do_ativo(s.ativo).custo_por_lado(s.retorno.index[:1]).iloc[0]
            )
            for s in series
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
