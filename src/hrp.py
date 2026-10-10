"""Paridade hierárquica de risco (HRP, López de Prado, 2016), escrita à mão.

A ideia: em vez de inverter a matriz de covariância (como em Markowitz, o que amplifica erros de
estimativa), agrupa os ativos por semelhança (correlação) numa árvore e divide o risco entre
os grupos, de cima para baixo. Ativos que andam juntos dividem uma mesma fatia.

Passos:
1. distância entre ativos: d = raiz((1 − correlação) / 2);
2. agrupamento hierárquico (ligação simples), que forma uma árvore de grupos;
3. divisão recursiva da árvore, do topo para baixo: cada grupo se divide em seus dois ramos e
   cada ramo recebe uma parte inversamente proporcional à sua variância (calculada com pesos de
   inverso da variância dentro do ramo).

Variante: o artigo original divide a lista de ativos ao meio, na ordem das folhas; aqui a
divisão segue os ramos da árvore, que respeita melhor os grupos (e não depende da ordem das
colunas). Com 2 ativos as duas coincidem.
"""

import numpy as np
import pandas as pd


def _montar_arvore(distancia: np.ndarray):
    """Agrupamento por ligação simples. Cada nó é um ativo (inteiro) ou um par (ramo, ramo)."""
    grupos = [
        ([i], i) for i in range(len(distancia))
    ]  # (ativos do grupo, nó da árvore)
    while len(grupos) > 1:
        melhor, par = np.inf, (0, 1)
        for i in range(len(grupos)):
            for j in range(i + 1, len(grupos)):
                menor = distancia[np.ix_(grupos[i][0], grupos[j][0])].min()
                if menor < melhor - 1e-12:
                    melhor, par = menor, (i, j)
        i, j = par
        grupos[i] = (grupos[i][0] + grupos[j][0], (grupos[i][1], grupos[j][1]))
        del grupos[j]
    return grupos[0][1]


def _folhas(no) -> list[int]:
    return [no] if isinstance(no, int) else _folhas(no[0]) + _folhas(no[1])


def _variancia_do_grupo(covariancia: np.ndarray, indices: list[int]) -> float:
    sub = covariancia[np.ix_(indices, indices)]
    pesos = 1.0 / np.diag(sub)
    pesos /= pesos.sum()
    return float(pesos @ sub @ pesos)


def calcular_pesos_hrp(retornos: pd.DataFrame) -> pd.Series:
    """Pesos HRP (positivos, somam 1) a partir dos retornos diários dos ativos."""
    if retornos.shape[1] < 2:
        raise ValueError("A paridade hierárquica precisa de pelo menos 2 ativos.")
    if len(retornos) < 30:
        raise ValueError("Poucos dias para estimar a covariância.")
    covariancia = retornos.cov().to_numpy()
    if not np.isfinite(covariancia).all() or (np.diag(covariancia) <= 0).any():
        raise ValueError("Algum ativo não varia ou tem dados faltando no trecho.")
    desvios = np.sqrt(np.diag(covariancia))
    correlacao = np.clip(covariancia / np.outer(desvios, desvios), -1.0, 1.0)
    distancia = np.sqrt((1.0 - correlacao) / 2.0)
    arvore = _montar_arvore(distancia)

    pesos = pd.Series(1.0, index=range(retornos.shape[1]))
    nos = [arvore]
    while nos:
        proximos = []
        for no in nos:
            if isinstance(no, int):
                continue
            esquerda, direita = _folhas(no[0]), _folhas(no[1])
            var_e = _variancia_do_grupo(covariancia, esquerda)
            var_d = _variancia_do_grupo(covariancia, direita)
            alfa = 1.0 - var_e / (var_e + var_d)
            pesos[esquerda] *= alfa
            pesos[direita] *= 1.0 - alfa
            proximos += [no[0], no[1]]
        nos = proximos
    return pd.Series(pesos.to_numpy(), index=retornos.columns)
