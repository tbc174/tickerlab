"""Motor de backtest para a pesquisa de ML: posição de -1 (vendido) a +1 (comprado) e custos reais.

Difere do motor do app público (`src/backtest.py`) em três pontos:

- a posição pode ser negativa (venda a descoberto), necessária em forex, metais e cripto;
- os custos são separados: spread (cobrado pela metade em cada lado), comissão, deslizamento e
  swap (o juro de carregar a posição de um dia para o outro, em dias corridos, que pode ser
  pago ou recebido e é diferente para comprado e vendido);
- a posição pode passar de 1 em módulo se o `limite` for aumentado de propósito (alavancagem).

A regra de ouro é a mesma: a posição que rende no dia t foi decidida no fechamento do dia t-1
(`shift(1)`), e a troca de posição acontece nesse fechamento. Com uma posição só dos dois lados,
virar de +1 para -1 move 2 unidades e paga o custo em dobro.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src import metricas

DIAS_DO_ANO = 365  # o swap corre em dias corridos
COLUNAS_DAS_OPERACOES = ["entrada", "saida", "dias", "lado", "retorno", "aberta"]


def _no_tempo(valor: float | pd.Series, indice: pd.Index) -> pd.Series:
    if isinstance(valor, pd.Series):
        return valor.reindex(indice).ffill().bfill().fillna(0.0)
    return pd.Series(float(valor), index=indice)


@dataclass(frozen=True, eq=False)
class Custos:
    """Custos de operar, todos em fração do valor negociado (0,0001 = 0,01% = 1 ponto-base).

    - `spread`: diferença entre compra e venda, como fração do preço. Número fixo ou série por
      dia (veja `spread_relativo`). Entrar e sair custam metade cada, então ida e volta custam
      o spread inteiro.
    - `comissao` e `deslizamento`: por lado (entrada ou saída).
    - `swap_comprado_anual` e `swap_vendido_anual`: retorno por ano, sobre o valor da posição,
      de ficar comprado ou vendido. Negativo = você paga; positivo = você recebe.
    """

    spread: float | pd.Series = 0.0
    comissao: float = 0.0
    deslizamento: float = 0.0
    swap_comprado_anual: float | pd.Series = 0.0
    swap_vendido_anual: float | pd.Series = 0.0

    def __post_init__(self) -> None:
        spread = (
            self.spread.min() if isinstance(self.spread, pd.Series) else self.spread
        )
        if spread < 0 or self.comissao < 0 or self.deslizamento < 0:
            raise ValueError("Spread, comissão e deslizamento não podem ser negativos.")

    def swaps(self, indice: pd.Index) -> tuple[pd.Series, pd.Series]:
        """Swap anual de comprado e de vendido em cada dia (número fixo ou série no tempo)."""
        return _no_tempo(self.swap_comprado_anual, indice), _no_tempo(
            self.swap_vendido_anual, indice
        )

    def custo_por_lado(self, indice: pd.Index) -> pd.Series:
        """Quanto custa mover uma unidade de posição, em cada dia."""
        if isinstance(self.spread, pd.Series):
            spread = self.spread.reindex(indice).ffill().bfill().fillna(0.0)
        else:
            spread = pd.Series(float(self.spread), index=indice)
        return spread / 2 + self.comissao + self.deslizamento


@dataclass(frozen=True)
class ResultadoBacktest:
    """Tudo o que sai de um backtest, pronto para métricas."""

    posicao: pd.Series  # fração do capital em cada dia, de -limite a +limite
    retorno: pd.Series  # retorno diário já descontados custos e somado o swap
    retorno_bruto: pd.Series  # só o movimento do preço
    custos: (
        pd.Series
    )  # custo de negociação de cada dia (spread, comissão, deslizamento)
    swap: pd.Series  # swap de cada dia (positivo = recebeu)
    curva_de_capital: pd.Series  # 1 no começo
    operacoes: pd.DataFrame  # entrada, saida, dias, lado (+1/-1), retorno, aberta
    giro: float  # soma das mudanças de posição (comprar 1 e vender 1 = 2)


def spread_relativo(candles: pd.DataFrame, tamanho_do_ponto: float) -> pd.Series:
    """Spread de cada candle como fração do preço.

    O MT5 guarda o spread em pontos (coluna `Spread`). Para forex, o ponto é o tamanho do tick
    do símbolo (`info_do_simbolo(...)["tamanho_do_tick"]`).
    """
    if tamanho_do_ponto <= 0:
        raise ValueError("O tamanho do ponto precisa ser positivo.")
    return candles["Spread"] * tamanho_do_ponto / candles["Close"]


def _extrair_operacoes(
    posicao: pd.Series, retorno: pd.Series, custo_do_dia: pd.Series
) -> pd.DataFrame:
    """Uma operação é um trecho seguido de dias com o mesmo lado (comprado ou vendido).

    O custo da saída para o caixa cai no primeiro dia sem posição e entra na operação que
    acabou. Quando a posição vira de um lado para o outro no mesmo dia, o custo desse dia é
    dividido ao meio entre a operação que fechou e a que abriu.
    """
    lado = np.sign(posicao).astype(int)
    em_posicao = lado != 0
    mudou = (lado != lado.shift(fill_value=0)).cumsum()
    linhas = []
    n = len(posicao)
    for _, trecho in posicao[em_posicao].groupby(mudou[em_posicao]):
        primeira, ultima = trecho.index[0], trecho.index[-1]
        posicao_da_ultima = posicao.index.get_loc(ultima)
        aberta = posicao_da_ultima == n - 1
        dias = retorno.loc[primeira:ultima].copy()
        if primeira != posicao.index[0]:
            anterior = lado.iloc[posicao.index.get_loc(primeira) - 1]
            if (
                anterior != 0
            ):  # virou de lado: metade do custo do dia é da operação anterior
                dias.loc[primeira] += custo_do_dia.loc[primeira] / 2
        resultado = (1 + dias).prod()
        if not aberta:
            seguinte = posicao.index[posicao_da_ultima + 1]
            if lado.loc[seguinte] == 0:
                resultado *= 1 + retorno.loc[seguinte]  # saída para o caixa
            else:
                resultado *= 1 - custo_do_dia.loc[seguinte] / 2  # virada de lado
        linhas.append(
            {
                "entrada": primeira,
                "saida": ultima,
                "dias": len(trecho),
                "lado": int(lado.loc[primeira]),
                "retorno": float(resultado - 1),
                "aberta": bool(aberta),
            }
        )
    return pd.DataFrame(linhas, columns=COLUNAS_DAS_OPERACOES)


def executar_backtest(
    fechamento: pd.Series,
    posicao_desejada: pd.Series,
    custos: Custos | None = None,
    limite: float = 1.0,
    retorno_do_ativo: pd.Series | None = None,
    com_operacoes: bool = True,
) -> ResultadoBacktest:
    """Simula a estratégia.

    `posicao_desejada` é a decisão tomada no FIM de cada dia: de -`limite` (vendido) a
    +`limite` (comprado), 0 = caixa. A posição que de fato rende em um dia é a de ontem.
    `retorno_do_ativo`, se dado, substitui a variação do fechamento (ex.: `retornos_seguros`,
    que não explode com preço negativo). `com_operacoes=False` pula a lista de operações (lenta
    com milhares de trocas); o retorno é o mesmo.
    """
    custos = custos or Custos()
    if limite <= 0:
        raise ValueError("O limite de posição precisa ser positivo.")
    if fechamento.empty:
        raise ValueError("Não há preços para simular.")
    if not fechamento.index.equals(posicao_desejada.index):
        raise ValueError("Preços e posição precisam ter as mesmas datas.")
    if posicao_desejada.isna().any() or (posicao_desejada.abs() > limite + 1e-12).any():
        raise ValueError(
            f"A posição desejada deve ficar entre -{limite:g} e {limite:g}, sem valores vazios."
        )

    if retorno_do_ativo is None:
        retorno_do_ativo = fechamento.pct_change().fillna(0.0)
    elif not retorno_do_ativo.index.equals(fechamento.index):
        raise ValueError("O retorno do ativo precisa ter as mesmas datas dos preços.")
    else:
        retorno_do_ativo = retorno_do_ativo.fillna(0.0)
    posicao = posicao_desejada.shift(1, fill_value=0.0)  # NÃO olha o futuro
    mudanca = posicao.diff().abs().fillna(posicao.abs())  # entrar também custa
    custo_do_dia = mudanca * custos.custo_por_lado(fechamento.index)

    swap_comprado, swap_vendido = custos.swaps(fechamento.index)
    dias_corridos = (
        pd.Series(fechamento.index, index=fechamento.index)
        .diff()
        .dt.days.fillna(0)
        .astype(float)
    )
    swap = (
        (posicao.clip(lower=0) * swap_comprado - posicao.clip(upper=0) * swap_vendido)
        * dias_corridos
        / DIAS_DO_ANO
    )
    retorno_bruto = posicao * retorno_do_ativo
    retorno = (retorno_bruto - custo_do_dia + swap).clip(
        lower=-1.0
    )  # perda máxima: tudo
    return ResultadoBacktest(
        posicao=posicao,
        retorno=retorno,
        retorno_bruto=retorno_bruto,
        custos=custo_do_dia,
        swap=swap,
        curva_de_capital=(1 + retorno).cumprod(),
        operacoes=(
            _extrair_operacoes(posicao, retorno, custo_do_dia)
            if com_operacoes
            else pd.DataFrame(columns=COLUNAS_DAS_OPERACOES)
        ),
        giro=float(mudanca.sum()),
    )


def resumir(
    resultado: ResultadoBacktest, taxa_livre_de_risco: float = 0.0
) -> dict[str, float]:
    """As métricas do app (Sharpe, queda máxima, operações...) mais o que importa aqui:
    exposição em módulo, giro por ano e quanto os custos comeram."""
    resumo = metricas.resumir_desempenho(
        resultado.retorno,
        posicao=resultado.posicao.abs(),
        operacoes=resultado.operacoes,
        taxa_livre_de_risco=taxa_livre_de_risco,
    )
    anos = max(len(resultado.retorno) / 252, 1e-9)
    resumo["Giro por ano"] = resultado.giro / anos
    resumo["Custos por ano"] = float(resultado.custos.sum() / anos)
    resumo["Swap por ano"] = float(resultado.swap.sum() / anos)
    return resumo
