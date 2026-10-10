"""Pairs trading: comprar um ativo e vender outro quando a distância entre eles foge do normal.

A ideia: dois ativos parecidos costumam andar juntos. Se a diferença entre eles (o "spread")
se afasta da sua média, aposta-se que volta: compra-se o que ficou barato e vende-se o que ficou
caro, ao mesmo tempo. O ganho não depende do mercado subir ou cair, só de a relação voltar.

Como o app evita enganar:
- a relação (o `beta` do spread = log A − beta × log B) é estimada SÓ no período de treino;
- o sinal usa a média e o desvio móveis do próprio spread, só com o passado;
- o teste de cointegração do treino é conferido de novo no período de teste: muitos pares
  parecem ligados no treino e se desfazem depois;
- ao varrer vários pares, o app avisa que testar muitos pares gera falsos positivos;
- vender a descoberto exige aluguel de ações e tem custo de empréstimo, que não entra aqui.

Aproximações: o retorno diário do par é (retorno de A − beta × retorno de B) ÷ (1 + |beta|), isto
é, os pesos de cada perna são reajustados todo dia; o custo por operação incide nas duas pernas.
"""

from dataclasses import dataclass
from itertools import combinations

import numpy as np
import pandas as pd

from src.backtest import (
    CUSTO_PADRAO_POR_OPERACAO,
    ResultadoBacktest,
    _extrair_operacoes,
)

# Valores críticos aproximados do teste de Engle-Granger (2 séries, com constante), MacKinnon.
VALORES_CRITICOS_ENGLE_GRANGER = {0.01: -3.90, 0.05: -3.34, 0.10: -3.04}
MAX_ATIVOS_PARA_PARES = 8


# --- estatística do spread ----------------------------------------------------------------


def estimar_relacao(log_a: pd.Series, log_b: pd.Series) -> tuple[float, float]:
    """Mínimos quadrados de log A em log B: devolve (alfa, beta)."""
    if len(log_a) < 30 or len(log_a) != len(log_b):
        raise ValueError(
            "São necessários pelo menos 30 dias em comum para estimar o par."
        )
    matriz = np.column_stack([np.ones(len(log_b)), log_b.to_numpy(dtype=float)])
    (alfa, beta), *_ = np.linalg.lstsq(matriz, log_a.to_numpy(dtype=float), rcond=None)
    return float(alfa), float(beta)


def calcular_adf(serie: pd.Series, defasagens: int = 1) -> float:
    """Estatística t do teste de Dickey-Fuller aumentado (com constante).

    Regressão: Δs_t = c + γ·s_(t-1) + soma de φ_i·Δs_(t-i) + erro. Quanto mais NEGATIVA a
    estatística, mais evidência de que a série volta para a média (é estacionária).
    """
    if defasagens < 0:
        raise ValueError("As defasagens não podem ser negativas.")
    s = serie.to_numpy(dtype=float)
    if len(s) < 40 + defasagens:
        raise ValueError("Poucos dias para o teste de estacionariedade.")
    delta = np.diff(s)
    n = len(delta) - defasagens
    y = delta[defasagens:]
    colunas = [np.ones(n), s[defasagens:-1]]
    for i in range(1, defasagens + 1):
        colunas.append(delta[defasagens - i : len(delta) - i])
    X = np.column_stack(colunas)
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    residuo = y - X @ coef
    sigma2 = residuo @ residuo / (n - X.shape[1])
    erro_padrao = np.sqrt(sigma2 * np.linalg.inv(X.T @ X)[1, 1])
    if erro_padrao == 0:
        return float("nan")
    return float(coef[1] / erro_padrao)


def calcular_meia_vida(spread: pd.Series) -> float:
    """Dias que o spread leva para voltar metade do caminho até a média (infinito se não volta)."""
    s = spread.to_numpy(dtype=float)
    if len(s) < 30:
        raise ValueError("Poucos dias para estimar a meia-vida.")
    X = np.column_stack([np.ones(len(s) - 1), s[:-1]])
    (_, gama), *_ = np.linalg.lstsq(X, np.diff(s), rcond=None)
    persistencia = 1.0 + gama
    if not 0 < persistencia < 1:
        return float("inf")
    return float(-np.log(2) / np.log(persistencia))


@dataclass(frozen=True)
class AnaliseDoPar:
    alfa: float
    beta: float
    correlacao: float  # dos retornos diários
    adf: float  # estatística de Dickey-Fuller do spread
    meia_vida: float
    cointegrado: bool  # ADF abaixo do valor crítico de 5%


def analisar_par(
    log_a: pd.Series, log_b: pd.Series, relacao: tuple[float, float] | None = None
) -> AnaliseDoPar:
    """Estima (ou usa uma relação dada) e mede o spread do par."""
    alfa, beta = relacao if relacao is not None else estimar_relacao(log_a, log_b)
    spread = log_a - beta * log_b - alfa
    adf = calcular_adf(spread)
    return AnaliseDoPar(
        alfa=alfa,
        beta=beta,
        correlacao=float(log_a.diff().corr(log_b.diff())),
        adf=adf,
        meia_vida=calcular_meia_vida(spread),
        cointegrado=bool(adf < VALORES_CRITICOS_ENGLE_GRANGER[0.05]),
    )


def procurar_pares(
    fechamentos: pd.DataFrame, fracao_de_treino: float = 0.5
) -> pd.DataFrame:
    """Todos os pares da lista, estimados no treino e conferidos no teste."""
    n_ativos = fechamentos.shape[1]
    if not 2 <= n_ativos <= MAX_ATIVOS_PARA_PARES:
        raise ValueError(
            f"Use de 2 a {MAX_ATIVOS_PARA_PARES} ativos para procurar pares."
        )
    if not 0.3 <= fracao_de_treino <= 0.8:
        raise ValueError("A fração de treino deve ficar entre 0,3 e 0,8.")
    logs = np.log(fechamentos.dropna())
    corte = int(len(logs) * fracao_de_treino)
    treino, teste = logs.iloc[:corte], logs.iloc[corte:]
    linhas = []
    for a, b in combinations(logs.columns, 2):
        no_treino = analisar_par(treino[a], treino[b])
        no_teste = analisar_par(teste[a], teste[b], (no_treino.alfa, no_treino.beta))
        linhas.append(
            {
                "Par": f"{a} × {b}",
                "Correlação": no_treino.correlacao,
                "Beta": no_treino.beta,
                "ADF no treino": no_treino.adf,
                "Meia-vida (dias)": no_treino.meia_vida,
                "Cointegrado no treino": no_treino.cointegrado,
                "ADF no teste": no_teste.adf,
                "Continuou no teste": no_teste.cointegrado,
            }
        )
    return pd.DataFrame(linhas).set_index("Par").sort_values("ADF no treino")


# --- sinal e backtest ---------------------------------------------------------------------


def calcular_z_do_spread(spread: pd.Series, janela: int = 60) -> pd.Series:
    """Quantos desvios o spread está acima da sua média móvel (só com o passado)."""
    if janela < 10:
        raise ValueError("A janela do z-score precisa ter pelo menos 10 dias.")
    media = spread.rolling(janela).mean()
    desvio = spread.rolling(janela).std().replace(0, np.nan)
    return (spread - media) / desvio


def gerar_lado_do_par(
    z: pd.Series, entrada: float = 2.0, saida: float = 0.5, stop: float = 4.0
) -> pd.Series:
    """+1 = comprado em A e vendido em B (spread baixo); −1 = o contrário; 0 = fora.

    Entra com |z| acima de `entrada`, sai quando |z| volta abaixo de `saida` e corta a perda
    se |z| passa de `stop` (e só volta a entrar depois de |z| cair abaixo da entrada).
    """
    if not 0 <= saida < entrada < stop:
        raise ValueError(
            "É preciso ter saída < entrada < stop (por exemplo, 0,5 < 2 < 4)."
        )
    valores = z.to_numpy(dtype=float)
    lado = np.zeros(len(valores))
    atual = 0.0
    cortado = False  # depois de um stop, só volta quando |z| voltar abaixo da entrada
    for i, v in enumerate(valores):
        if np.isnan(v):
            atual, cortado = 0.0, False
        elif atual == 0.0:
            if cortado:
                cortado = abs(v) >= entrada
            elif v < -entrada:
                atual = 1.0
            elif v > entrada:
                atual = -1.0
            if abs(v) >= stop:
                atual, cortado = 0.0, True
        elif abs(v) <= saida:
            atual = 0.0
        elif abs(v) >= stop:
            atual, cortado = 0.0, True
        lado[i] = atual
    return pd.Series(lado, index=z.index)


def executar_backtest_do_par(
    fechamento_a: pd.Series,
    fechamento_b: pd.Series,
    lado_desejado: pd.Series,
    beta: float,
    custo_por_operacao: float = CUSTO_PADRAO_POR_OPERACAO,
) -> ResultadoBacktest:
    """O lado decidido no fim do dia vale no dia seguinte (como em todo o motor)."""
    if custo_por_operacao < 0:
        raise ValueError("O custo por operação não pode ser negativo.")
    if not (
        fechamento_a.index.equals(fechamento_b.index)
        and fechamento_a.index.equals(lado_desejado.index)
    ):
        raise ValueError("Os dois ativos e o sinal precisam ter as mesmas datas.")
    lado = lado_desejado.shift(1, fill_value=0.0)
    retorno_do_par = (
        fechamento_a.pct_change().fillna(0.0)
        - beta * fechamento_b.pct_change().fillna(0.0)
    ) / (1.0 + abs(beta))
    mudanca = lado.diff().abs().fillna(lado.abs())
    # o custo incide em cada perna; ponderado pelos pesos das pernas, vale `custo` por unidade
    retorno = lado * retorno_do_par - mudanca * custo_por_operacao
    posicao = lado.abs()
    return ResultadoBacktest(
        posicao=posicao,
        retorno=retorno,
        curva_de_capital=(1 + retorno).cumprod(),
        operacoes=_extrair_operacoes(posicao, retorno),
        giro=float(mudanca.sum()),
    )


@dataclass(frozen=True)
class ResultadoDoPar:
    backtest: ResultadoBacktest  # só o período de teste
    lado: pd.Series
    spread: pd.Series  # no período todo, com a relação do treino
    z: pd.Series
    treino: AnaliseDoPar
    teste: AnaliseDoPar
    inicio_do_teste: pd.Timestamp


def simular_par(
    fechamento_a: pd.Series,
    fechamento_b: pd.Series,
    fracao_de_treino: float = 0.5,
    entrada: float = 2.0,
    saida: float = 0.5,
    stop: float = 4.0,
    janela: int = 60,
    custo_por_operacao: float = CUSTO_PADRAO_POR_OPERACAO,
) -> ResultadoDoPar:
    """Estima a relação no treino e opera o par só no período de teste."""
    if not 0.3 <= fracao_de_treino <= 0.8:
        raise ValueError("A fração de treino deve ficar entre 0,3 e 0,8.")
    juntos = pd.concat([fechamento_a, fechamento_b], axis=1, join="inner").dropna()
    if len(juntos) < 250:
        raise ValueError(
            "Poucos dias em comum para testar o par. Use um período maior."
        )
    log_a, log_b = np.log(juntos.iloc[:, 0]), np.log(juntos.iloc[:, 1])
    corte = int(len(juntos) * fracao_de_treino)
    treino = analisar_par(log_a.iloc[:corte], log_b.iloc[:corte])
    teste = analisar_par(
        log_a.iloc[corte:], log_b.iloc[corte:], (treino.alfa, treino.beta)
    )
    spread = log_a - treino.beta * log_b - treino.alfa
    z = calcular_z_do_spread(spread, janela)
    lado = gerar_lado_do_par(z, entrada, saida, stop)
    lado.iloc[:corte] = 0.0  # no treino não se opera
    fim = slice(corte, None)
    backtest = executar_backtest_do_par(
        juntos.iloc[fim, 0],
        juntos.iloc[fim, 1],
        lado.iloc[fim],
        treino.beta,
        custo_por_operacao,
    )
    return ResultadoDoPar(
        backtest=backtest,
        lado=lado,
        spread=spread,
        z=z,
        treino=treino,
        teste=teste,
        inicio_do_teste=juntos.index[corte],
    )
