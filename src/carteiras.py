"""Estratégias de vários ativos: o sinal é uma tabela de pesos (uma coluna por ativo).

Cada estratégia decide no último pregão de cada mês, usando só o que já aconteceu até aquele
dia, e a decisão vale a partir do dia seguinte. O que não está nos ativos fica em caixa (e pode
render o CDI). Os pesos "derivam" entre uma decisão e outra, como numa carteira de verdade:
quem subiu fica com mais peso até o próximo rebalanceamento.

O primeiro ativo da lista é o "canário" da estratégia de mesmo nome.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src import indicadores as ind
from src.backtest import CUSTO_PADRAO_POR_OPERACAO
from src.estrategias import Parametro, _conferir_parametro
from src.hrp import calcular_pesos_hrp

MAX_ATIVOS_NA_CARTEIRA = 8
MIN_ATIVOS_NA_CARTEIRA = 2
DIAS_MINIMOS_DA_COVARIANCIA = 60


@dataclass(frozen=True)
class EstrategiaDeCarteira:
    nome: str
    funcao: Callable[..., pd.DataFrame]
    parametros: tuple[Parametro, ...] = field(default_factory=tuple)

    def parametros_padrao(self) -> dict[str, int | float | str]:
        return {p.nome: p.padrao for p in self.parametros}


# --- Ajudantes ------------------------------------------------------------------------


def dias_de_decisao(indice: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """O último dia de negociação de cada mês presente no índice."""
    meses = pd.Series(indice.to_period("M"), index=indice)
    return pd.DatetimeIndex(meses.groupby(meses).tail(1).index)


def _pesos_dos_dias_de_decisao(
    pesos: pd.DataFrame, indice: pd.DatetimeIndex
) -> pd.DataFrame:
    """Espalha os pesos decididos no fim do mês pelos dias seguintes; antes da primeira decisão, caixa."""
    return pesos.reindex(indice).ffill().fillna(0.0)


def _momentum(fechamentos: pd.DataFrame, janela: int, pular: int) -> pd.DataFrame:
    """Retorno de `janela` dias, terminando `pular` dias antes de hoje."""
    return fechamentos.shift(pular) / fechamentos.shift(pular + janela) - 1


def _volatilidade(fechamentos: pd.DataFrame, janela: int) -> pd.DataFrame:
    return fechamentos.pct_change().rolling(janela).std() * np.sqrt(ind.DIAS_POR_ANO)


def _melhores_em_partes_iguais(
    nota: pd.DataFrame, quantos: int, elegiveis: pd.DataFrame
) -> pd.DataFrame:
    """Em cada linha, 1/quantos para cada um dos `quantos` maiores entre os elegíveis."""
    nota = nota.where(elegiveis)
    posto = nota.rank(axis=1, ascending=False, method="first")
    escolhidos = (posto <= quantos) & nota.notna()
    return escolhidos.astype(float) / quantos


# --- Estratégias ----------------------------------------------------------------------


def pesos_iguais(fechamentos: pd.DataFrame) -> pd.DataFrame:
    """Referência: partes iguais em todos os ativos, rebalanceadas todo mês."""
    n = fechamentos.shape[1]
    pesos = pd.DataFrame(1.0 / n, index=fechamentos.index, columns=fechamentos.columns)
    return pesos  # desde o primeiro dia; o rebalanceamento acontece nos dias de decisão


def rotacao_por_momentum(
    fechamentos: pd.DataFrame, melhores: int = 2, janela: int = 252, pular: int = 21
) -> pd.DataFrame:
    """Fica com os `melhores` ativos de maior momentum, em partes iguais."""
    decisao = dias_de_decisao(fechamentos.index)
    momentum = _momentum(fechamentos, janela, pular).loc[decisao]
    pesos = _melhores_em_partes_iguais(momentum, melhores, momentum.notna())
    return _pesos_dos_dias_de_decisao(pesos, fechamentos.index)


def momentum_dual(
    fechamentos: pd.DataFrame, melhores: int = 2, janela: int = 252, pular: int = 21
) -> pd.DataFrame:
    """Rotação por momentum, mas só ativos com momentum positivo; o resto fica em caixa."""
    decisao = dias_de_decisao(fechamentos.index)
    momentum = _momentum(fechamentos, janela, pular).loc[decisao]
    pesos = _melhores_em_partes_iguais(momentum, melhores, momentum > 0)
    return _pesos_dos_dias_de_decisao(pesos, fechamentos.index)


def inverso_da_volatilidade(
    fechamentos: pd.DataFrame, janela: int = 60
) -> pd.DataFrame:
    """Peso proporcional a 1/volatilidade: os ativos calmos pesam mais, os agitados menos."""
    decisao = dias_de_decisao(fechamentos.index)
    inverso = 1 / _volatilidade(fechamentos, janela).loc[decisao].replace(0, np.nan)
    pesos = inverso.div(inverso.sum(axis=1), axis=0).fillna(0.0)
    return _pesos_dos_dias_de_decisao(pesos, fechamentos.index)


def baixa_volatilidade(
    fechamentos: pd.DataFrame, melhores: int = 2, janela: int = 60
) -> pd.DataFrame:
    """Fica com os `melhores` ativos de menor volatilidade recente, em partes iguais."""
    decisao = dias_de_decisao(fechamentos.index)
    volatilidade = _volatilidade(fechamentos, janela).loc[decisao]
    pesos = _melhores_em_partes_iguais(-volatilidade, melhores, volatilidade.notna())
    return _pesos_dos_dias_de_decisao(pesos, fechamentos.index)


def canario(
    fechamentos: pd.DataFrame, janela: int = 252, pular: int = 21
) -> pd.DataFrame:
    """Se o momentum do primeiro ativo (o canário) é positivo, partes iguais em todos; senão, caixa."""
    decisao = dias_de_decisao(fechamentos.index)
    momentum = _momentum(fechamentos, janela, pular).loc[decisao]
    clima_bom = (momentum.iloc[:, 0] > 0).astype(float)
    n = fechamentos.shape[1]
    pesos = pd.DataFrame(
        {coluna: clima_bom / n for coluna in fechamentos.columns}, index=decisao
    )
    return _pesos_dos_dias_de_decisao(pesos, fechamentos.index)


def paridade_hierarquica(fechamentos: pd.DataFrame, janela: int = 252) -> pd.DataFrame:
    """Pesos da paridade hierárquica de risco (HRP), com a covariância dos últimos `janela` dias
    (no início, com os dias que houver, a partir de 60)."""
    decisao = dias_de_decisao(fechamentos.index)
    retorno = fechamentos.pct_change()
    pesos = pd.DataFrame(np.nan, index=decisao, columns=fechamentos.columns)
    for dia in decisao:
        fim = fechamentos.index.get_loc(dia) + 1
        if fim <= DIAS_MINIMOS_DA_COVARIANCIA:
            continue  # sem histórico suficiente: fica em caixa
        # no começo usa o que já existe (pelo menos 60 dias) em vez de ficar parada um ano
        trecho = retorno.iloc[max(1, fim - janela) : fim].dropna(axis=1)
        if trecho.shape[1] < 2:
            continue
        try:
            pesos.loc[dia, trecho.columns] = calcular_pesos_hrp(trecho)
        except ValueError:
            continue  # ex.: ativo parado no período: mantém o caixa
    return _pesos_dos_dias_de_decisao(pesos.fillna(0.0), fechamentos.index)


_MELHORES = Parametro(
    "melhores",
    "Quantos ativos manter",
    2,
    1,
    MAX_ATIVOS_NA_CARTEIRA,
    1,
    ajuda="Quantos dos melhores ativos a carteira segura ao mesmo tempo (em partes iguais).",
)
_JANELA_MOMENTUM = Parametro("janela", "Janela do momentum (dias)", 252, 63, 504, 21)
_PULAR = Parametro(
    "pular",
    "Dias ignorados no fim",
    21,
    0,
    63,
    1,
    ajuda="Pula o último mês, para evitar a reversão de curtíssimo prazo.",
)
_JANELA_COVARIANCIA = Parametro(
    "janela",
    "Janela da covariância (dias)",
    252,
    63,
    504,
    21,
    ajuda="Quantos dias passados entram no cálculo de como os ativos andam juntos.",
)
_JANELA_VOLATILIDADE = Parametro(
    "janela", "Janela da volatilidade (dias)", 60, 20, 252, 5
)

ESTRATEGIAS_DE_CARTEIRA: dict[str, EstrategiaDeCarteira] = {
    e.nome: e
    for e in (
        EstrategiaDeCarteira("Pesos iguais (referência)", pesos_iguais),
        EstrategiaDeCarteira(
            "Rotação por momentum",
            rotacao_por_momentum,
            (_MELHORES, _JANELA_MOMENTUM, _PULAR),
        ),
        EstrategiaDeCarteira(
            "Momentum dual", momentum_dual, (_MELHORES, _JANELA_MOMENTUM, _PULAR)
        ),
        EstrategiaDeCarteira(
            "Pesos pelo inverso da volatilidade",
            inverso_da_volatilidade,
            (_JANELA_VOLATILIDADE,),
        ),
        EstrategiaDeCarteira(
            "Baixa volatilidade", baixa_volatilidade, (_MELHORES, _JANELA_VOLATILIDADE)
        ),
        EstrategiaDeCarteira("Ativo-canário", canario, (_JANELA_MOMENTUM, _PULAR)),
        EstrategiaDeCarteira(
            "Paridade hierárquica de risco (HRP)",
            paridade_hierarquica,
            (_JANELA_COVARIANCIA,),
        ),
    )
}


def gerar_pesos(nome: str, fechamentos: pd.DataFrame, **parametros) -> pd.DataFrame:
    """Aplica a estratégia `nome`, conferindo os parâmetros e os ativos."""
    if nome not in ESTRATEGIAS_DE_CARTEIRA:
        raise ValueError(f"Estratégia de carteira desconhecida: {nome}.")
    if not MIN_ATIVOS_NA_CARTEIRA <= fechamentos.shape[1] <= MAX_ATIVOS_NA_CARTEIRA:
        raise ValueError(
            f"Use de {MIN_ATIVOS_NA_CARTEIRA} a {MAX_ATIVOS_NA_CARTEIRA} ativos."
        )
    estrategia = ESTRATEGIAS_DE_CARTEIRA[nome]
    conhecidos = {p.nome: p for p in estrategia.parametros}
    desconhecidos = set(parametros) - set(conhecidos)
    if desconhecidos:
        raise ValueError(
            f"Parâmetros desconhecidos para {nome}: {sorted(desconhecidos)}."
        )
    valores = {**estrategia.parametros_padrao(), **parametros}
    for nome_do_parametro, valor in valores.items():
        _conferir_parametro(conhecidos[nome_do_parametro], valor)
    if "melhores" in valores and valores["melhores"] > fechamentos.shape[1]:
        raise ValueError("Não dá para manter mais ativos do que os da carteira.")
    return estrategia.funcao(fechamentos, **valores)


# --- Motor ----------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultadoCarteira:
    pesos: (
        pd.DataFrame
    )  # peso de cada ativo durante o dia, já com a deriva (o resto é caixa)
    retorno: pd.Series  # retorno diário da carteira, já descontados os custos
    curva_de_capital: pd.Series
    giro: float  # soma de tudo o que foi comprado e vendido (em frações do capital)

    @property
    def exposicao(self) -> pd.Series:
        """Fração do capital em ativos (o resto está em caixa)."""
        return self.pesos.sum(axis=1)


def executar_backtest_de_carteira(
    fechamentos: pd.DataFrame,
    pesos_desejados: pd.DataFrame,
    custo_por_operacao: float = CUSTO_PADRAO_POR_OPERACAO,
    retorno_do_caixa: pd.Series | None = None,
) -> ResultadoCarteira:
    """Simula a carteira.

    `pesos_desejados` é a decisão do FIM de cada dia; ela só vale no dia seguinte. A carteira é
    rebalanceada para os pesos desejados nos dias de decisão (fim de mês) e sempre que os pesos
    mudam; entre uma e outra, deixa os pesos derivarem. Cada compra e venda custa
    `custo_por_operacao` sobre o valor negociado.
    """
    if custo_por_operacao < 0:
        raise ValueError("O custo por operação não pode ser negativo.")
    if fechamentos.empty:
        raise ValueError("Não há preços para simular.")
    if not (
        fechamentos.index.equals(pesos_desejados.index)
        and list(fechamentos.columns) == list(pesos_desejados.columns)
    ):
        raise ValueError("Preços e pesos precisam ter as mesmas datas e ativos.")
    if (
        pesos_desejados.isna().any().any()
        or (pesos_desejados < -1e-12).any().any()
        or (pesos_desejados.sum(axis=1) > 1 + 1e-9).any()
    ):
        raise ValueError(
            "Os pesos devem ser positivos, sem vazios, e somar no máximo 1."
        )

    retornos = fechamentos.pct_change().fillna(0.0).to_numpy(dtype=float)
    alvo = pesos_desejados.to_numpy(dtype=float)
    n_dias, n_ativos = alvo.shape
    caixa = (
        np.zeros(n_dias)
        if retorno_do_caixa is None
        else retorno_do_caixa.reindex(fechamentos.index).fillna(0.0).to_numpy(float)
    )
    decisao = fechamentos.index.isin(dias_de_decisao(fechamentos.index))

    pesos = np.zeros((n_dias, n_ativos))
    retorno = np.zeros(n_dias)
    atual = np.zeros(n_ativos)  # pesos de hoje
    ultimo_alvo = np.zeros(n_ativos)
    giro = 0.0
    for dia in range(1, n_dias):
        desejado = alvo[dia - 1]  # decidido ontem à noite
        if decisao[dia - 1] or not np.allclose(desejado, ultimo_alvo):
            negociado = np.abs(desejado - atual).sum()
            giro += negociado
            custo = negociado * custo_por_operacao
            atual = desejado.copy()
            ultimo_alvo = desejado
        else:
            custo = 0.0
        pesos[dia] = atual
        fora = 1 - atual.sum()
        crescimento = 1 + atual @ retornos[dia] + fora * caixa[dia]
        retorno[dia] = crescimento - 1 - custo
        atual = atual * (1 + retornos[dia]) / crescimento

    retorno_serie = pd.Series(retorno, index=fechamentos.index)
    return ResultadoCarteira(
        pesos=pd.DataFrame(pesos, index=fechamentos.index, columns=fechamentos.columns),
        retorno=retorno_serie,
        curva_de_capital=(1 + retorno_serie).cumprod(),
        giro=float(giro),
    )


def simular_carteira(
    nome: str,
    fechamentos: pd.DataFrame,
    custo_por_operacao: float = CUSTO_PADRAO_POR_OPERACAO,
    retorno_do_caixa: pd.Series | None = None,
    **parametros,
) -> ResultadoCarteira:
    """Gera os pesos da estratégia `nome` e roda o backtest."""
    pesos = gerar_pesos(nome, fechamentos, **parametros)
    return executar_backtest_de_carteira(
        fechamentos, pesos, custo_por_operacao, retorno_do_caixa
    )
