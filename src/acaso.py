"""Quanto do resultado pode ser sorte? Monte Carlo, teste contra o acaso, Sharpe deflacionado e PBO.

- Monte Carlo: reamostra as operações da estratégia milhares de vezes. Mostra o quanto o
  resultado depende da ORDEM em que os ganhos e as perdas apareceram.
- Teste contra o acaso: desloca a posição no tempo (mesma exposição, mesmo número de operações,
  mas sem relação com o preço). Se muitas versões "cegas" fazem igual, não há habilidade.
- Sharpe deflacionado (Bailey e López de Prado, 2014): desconta o Sharpe pelo número de
  combinações testadas, porque o melhor de muitas tentativas é bom em parte por sorte.
- PBO (Bailey et al., 2017): com que frequência a melhor combinação do treino fica abaixo da
  mediana fora dele.
"""

from dataclasses import dataclass
from itertools import combinations
from statistics import NormalDist

import numpy as np
import pandas as pd

from src import indicadores as ind

NORMAL = NormalDist()
EULER_MASCHERONI = 0.5772156649015329
NAN = float("nan")
MIN_OPERACOES_PARA_MONTE_CARLO = 5
MIN_DIAS_PARA_SHARPE = 30


# --- Monte Carlo das operações -----------------------------------------------------------


@dataclass(frozen=True)
class ResultadoMonteCarlo:
    retornos_finais: np.ndarray  # retorno total de cada simulação
    quedas_maximas: np.ndarray  # maior queda de cada simulação (negativa)
    percentis_da_curva: pd.DataFrame  # por nº de operações: p5, p25, p50, p75, p95
    curva_observada: np.ndarray  # a ordem real das operações (começa em 1)
    probabilidade_de_prejuizo: float


def simular_monte_carlo(
    retornos_das_operacoes: pd.Series, simulacoes: int = 2000, semente: int = 42
) -> ResultadoMonteCarlo:
    """Sorteia, com reposição, o mesmo número de operações e compõe os retornos em sequência."""
    operacoes = retornos_das_operacoes.dropna().to_numpy(dtype=float)
    if len(operacoes) < MIN_OPERACOES_PARA_MONTE_CARLO:
        raise ValueError(
            f"Com menos de {MIN_OPERACOES_PARA_MONTE_CARLO} operações o Monte Carlo não diz nada."
        )
    if simulacoes < 100:
        raise ValueError("Use pelo menos 100 simulações.")
    sorteio = np.random.default_rng(semente).integers(
        0, len(operacoes), size=(simulacoes, len(operacoes))
    )
    curvas = np.cumprod(1 + operacoes[sorteio], axis=1)
    curvas = np.hstack([np.ones((simulacoes, 1)), curvas])
    quedas = (curvas / np.maximum.accumulate(curvas, axis=1) - 1).min(axis=1)
    finais = curvas[:, -1] - 1
    percentis = pd.DataFrame(
        np.percentile(curvas, [5, 25, 50, 75, 95], axis=0).T,
        columns=["p5", "p25", "p50", "p75", "p95"],
    )
    observada = np.concatenate([[1.0], np.cumprod(1 + operacoes)])
    return ResultadoMonteCarlo(
        retornos_finais=finais,
        quedas_maximas=quedas,
        percentis_da_curva=percentis,
        curva_observada=observada,
        probabilidade_de_prejuizo=float((finais < 0).mean()),
    )


# --- Teste contra o acaso ----------------------------------------------------------------


def _retorno_da_posicao(
    retorno_do_ativo: np.ndarray, desejada: np.ndarray, custo: float
) -> np.ndarray:
    """A mesma conta de `executar_backtest`, em numpy puro (para repetir milhares de vezes)."""
    posicao = np.concatenate([[0.0], desejada[:-1]])
    mudanca = np.abs(np.diff(posicao, prepend=0.0))
    return posicao * retorno_do_ativo - mudanca * custo


@dataclass(frozen=True)
class ResultadoAcaso:
    sharpe_real: float
    sharpes_ao_acaso: np.ndarray
    p_valor: (
        float  # fatia das versões ao acaso que fez igual ou melhor (com a correção +1)
    )


def testar_contra_o_acaso(
    fechamento: pd.Series,
    posicao_desejada: pd.Series,
    custo_por_operacao: float,
    taxa_livre_de_risco: float = 0.0,
    sorteios: int = 1000,
    semente: int = 42,
) -> ResultadoAcaso:
    """Compara o Sharpe real com o de versões da mesma posição deslocadas no tempo.

    Girar a posição (o fim vira o começo) mantém exatamente a exposição e o número de operações,
    e quebra a relação entre o sinal e o preço do dia.
    """
    if sorteios < 100:
        raise ValueError("Use pelo menos 100 sorteios.")
    if not fechamento.index.equals(posicao_desejada.index):
        raise ValueError("Preços e posição precisam ter as mesmas datas.")
    retorno_do_ativo = fechamento.pct_change().fillna(0.0).to_numpy(dtype=float)
    desejada = posicao_desejada.to_numpy(dtype=float)
    n = len(desejada)
    if n < 2 * MIN_DIAS_PARA_SHARPE:
        raise ValueError("Poucos dados para o teste contra o acaso.")

    def sharpe(retorno: np.ndarray) -> float:
        return ind.calcular_indice_sharpe(pd.Series(retorno), taxa_livre_de_risco)

    real = sharpe(_retorno_da_posicao(retorno_do_ativo, desejada, custo_por_operacao))
    if np.isnan(real):
        raise ValueError("A estratégia não operou: não há Sharpe para comparar.")
    folga = max(
        21, n // 10
    )  # deslocamentos muito pequenos quase repetem a posição real
    if n - 2 * folga < 1:
        raise ValueError("Poucos dados para o teste contra o acaso.")
    deslocamentos = np.random.default_rng(semente).integers(
        folga, n - folga, size=sorteios
    )
    ao_acaso = np.array(
        [
            sharpe(
                _retorno_da_posicao(
                    retorno_do_ativo, np.roll(desejada, int(k)), custo_por_operacao
                )
            )
            for k in deslocamentos
        ]
    )
    validos = ao_acaso[~np.isnan(ao_acaso)]
    p_valor = (1 + float((validos >= real).sum())) / (1 + len(validos))
    return ResultadoAcaso(real, validos, p_valor)


# --- Sharpe probabilístico e deflacionado ------------------------------------------------


def _sharpe_diario(retorno: pd.Series, taxa_livre_de_risco: float = 0.0) -> float:
    retorno = retorno.dropna()
    if len(retorno) < MIN_DIAS_PARA_SHARPE:
        return NAN
    excesso = retorno - taxa_livre_de_risco / ind.DIAS_POR_ANO
    desvio = excesso.std()
    if desvio == 0 or np.isnan(desvio):
        return NAN
    return float(excesso.mean() / desvio)


def calcular_sharpe_probabilistico(
    retorno: pd.Series,
    sharpe_diario_de_referencia: float = 0.0,
    taxa_livre_de_risco: float = 0.0,
) -> float:
    """Probabilidade de o Sharpe verdadeiro superar a referência, dados o tamanho da amostra,
    a assimetria e a curtose dos retornos (PSR)."""
    retorno = retorno.dropna()
    sharpe = _sharpe_diario(retorno, taxa_livre_de_risco)
    if np.isnan(sharpe):
        return NAN
    assimetria = float(retorno.skew())
    curtose = float(retorno.kurt()) + 3  # o pandas devolve a curtose em excesso
    termo = 1 - assimetria * sharpe + (curtose - 1) / 4 * sharpe**2
    if termo <= 0:
        return NAN
    z = (
        (sharpe - sharpe_diario_de_referencia)
        * np.sqrt(len(retorno) - 1)
        / np.sqrt(termo)
    )
    return float(NORMAL.cdf(z))


def calcular_sharpe_maximo_esperado(
    variancia_dos_sharpes_diarios: float, tentativas: int
) -> float:
    """Sharpe diário do melhor de `tentativas` combinações que, na verdade, não valem nada."""
    if tentativas < 1:
        raise ValueError("O número de tentativas deve ser pelo menos 1.")
    if tentativas == 1 or variancia_dos_sharpes_diarios <= 0:
        return 0.0
    gama = EULER_MASCHERONI
    return float(
        np.sqrt(variancia_dos_sharpes_diarios)
        * (
            (1 - gama) * NORMAL.inv_cdf(1 - 1 / tentativas)
            + gama * NORMAL.inv_cdf(1 - 1 / (tentativas * np.e))
        )
    )


@dataclass(frozen=True)
class ResultadoDeflacionado:
    sharpe_anual: float  # do candidato avaliado
    sharpe_anual_por_sorte: (
        float  # o que se esperaria do melhor de N tentativas sem habilidade
    )
    probabilidade: float  # DSR: chance de o Sharpe verdadeiro ser maior que o da sorte
    tentativas: int


def calcular_sharpe_deflacionado(
    retorno: pd.Series,
    retornos_dos_candidatos: pd.DataFrame,
    tentativas_extras: int = 0,
    taxa_livre_de_risco: float = 0.0,
) -> ResultadoDeflacionado:
    """DSR do `retorno` escolhido entre os candidatos (mais as tentativas que ficaram de fora)."""
    if tentativas_extras < 0:
        raise ValueError("As tentativas extras não podem ser negativas.")
    sharpes = retornos_dos_candidatos.apply(
        _sharpe_diario, taxa_livre_de_risco=taxa_livre_de_risco
    )
    sharpes = sharpes.dropna()
    tentativas = len(retornos_dos_candidatos.columns) + tentativas_extras
    if len(sharpes) < 2:
        raise ValueError(
            "São necessários pelo menos 2 candidatos com Sharpe para deflacionar."
        )
    sharpe_da_sorte = calcular_sharpe_maximo_esperado(float(sharpes.var()), tentativas)
    probabilidade = calcular_sharpe_probabilistico(
        retorno, sharpe_da_sorte, taxa_livre_de_risco
    )
    anual = np.sqrt(ind.DIAS_POR_ANO)
    return ResultadoDeflacionado(
        sharpe_anual=_sharpe_diario(retorno, taxa_livre_de_risco) * anual,
        sharpe_anual_por_sorte=sharpe_da_sorte * anual,
        probabilidade=probabilidade,
        tentativas=tentativas,
    )


# --- PBO (validação cruzada combinatoriamente simétrica) ----------------------------------


@dataclass(frozen=True)
class ResultadoPBO:
    probabilidade: float  # PBO: acima de 0,5 a escolha pelo treino virou sorte
    logits: (
        np.ndarray
    )  # um por combinação de blocos; negativo = a melhor ficou abaixo da mediana
    combinacoes: int


def calcular_pbo(
    retornos_dos_candidatos: pd.DataFrame, blocos: int = 10
) -> ResultadoPBO:
    """Divide o histórico em `blocos`; em cada metade-treino/metade-teste possível escolhe o
    melhor candidato do treino e vê onde ele cai no teste."""
    if blocos < 4 or blocos % 2:
        raise ValueError("Use um número par de blocos, de pelo menos 4.")
    n_candidatos = retornos_dos_candidatos.shape[1]
    if n_candidatos < 2:
        raise ValueError("O PBO precisa de pelo menos 2 candidatos.")
    dias_por_bloco = len(retornos_dos_candidatos) // blocos
    if dias_por_bloco < 10:
        raise ValueError("Poucos dados para dividir em blocos.")
    dados = retornos_dos_candidatos.to_numpy(dtype=float)[: dias_por_bloco * blocos]
    dados = np.nan_to_num(dados).reshape(blocos, dias_por_bloco, n_candidatos)
    soma = dados.sum(axis=1)  # (blocos, candidatos)
    soma_quadrados = (dados**2).sum(axis=1)

    def sharpes(escolhidos: tuple[int, ...]) -> np.ndarray:
        n = dias_por_bloco * len(escolhidos)
        media = soma[list(escolhidos)].sum(axis=0) / n
        variancia = soma_quadrados[list(escolhidos)].sum(axis=0) / n - media**2
        with np.errstate(divide="ignore", invalid="ignore"):
            resultado = media / np.sqrt(variancia)
        return np.where(
            variancia > 1e-18, resultado, -np.inf
        )  # quem não opera nunca é o melhor

    logits = []
    todos = set(range(blocos))
    for treino in combinations(range(blocos), blocos // 2):
        teste = tuple(sorted(todos - set(treino)))
        melhor = int(np.argmax(sharpes(treino)))
        no_teste = sharpes(teste)
        posto = (
            no_teste < no_teste[melhor]
        ).sum() + 1  # 1 = pior, n_candidatos = melhor
        relativo = posto / (n_candidatos + 1)
        logits.append(np.log(relativo / (1 - relativo)))
    logits_array = np.array(logits)
    return ResultadoPBO(
        probabilidade=float((logits_array <= 0).mean()),
        logits=logits_array,
        combinacoes=len(logits_array),
    )
