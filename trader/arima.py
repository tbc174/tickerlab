"""H5: séries temporais clássicas (critério v0.2, seção 1). Um ARIMA por ativo, sem atributos.

Em cada divisão do CPCV e para cada ativo:
1. a série é o retorno diário dividido pela volatilidade (`retorno_1d` do painel, conhecido no
   fechamento do dia);
2. ajusta-se ARMA(p, q) com constante para p e q de 0 a 2 (d = 0) **só com os dias de treino**: os
   outros dias entram vazios, e o filtro de Kalman do `statsmodels` sabe lidar com dias faltando;
3. fica a ordem de menor AIC;
4. com os parâmetros fixos, o filtro passa pela série inteira (em cada dia ele só usa o que já
   aconteceu até aquele dia) e prevê a soma dos próximos `horizonte` pregões;
5. a previsão vira a probabilidade de "sobe": Φ(previsão ÷ √(horizonte × variância do erro)).
Daí em diante é o mesmo pipeline dos outros modelos (sinal, posição, custos, CPCV, avaliador).
"""

from __future__ import annotations

import warnings

import numpy as np
from scipy.stats import norm
from statsmodels.tsa.statespace.sarimax import SARIMAX

ORDENS = tuple(
    (p, q) for p in range(3) for q in range(3)
)  # (0,0) a (2,2): as 9 do critério
MINIMO_DE_TREINO = (
    250  # dias de treino com dado para ajustar o ativo; menos que isso, fica neutro
)
PARAMETROS = {
    "p_max": 2,
    "q_max": 2,
    "d": 0,
    "constante": True,
    "escolha": "AIC so no treino",
    "entrada": "retorno_1d",
}


def ajustar(serie_de_treino: np.ndarray) -> object | None:
    """O ARMA de menor AIC entre as 9 ordens (dias fora do treino = NaN). None se nenhum ajustar."""
    melhor, menor_aic = None, np.inf
    with warnings.catch_warnings():
        warnings.simplefilter(
            "ignore"
        )  # avisos de convergência são comuns e não mudam a escolha
        for p, q in ORDENS:
            try:
                res = SARIMAX(serie_de_treino, order=(p, 0, q), trend="c").fit(
                    disp=False
                )
            except (ValueError, np.linalg.LinAlgError):
                continue
            if np.isfinite(res.aic) and res.aic < menor_aic:
                melhor, menor_aic = res, res.aic
    return melhor


def soma_prevista(ajustado: object, serie: np.ndarray, horizonte: int) -> np.ndarray:
    """Em cada dia t, a previsão da soma dos `horizonte` dias seguintes, só com dados até t.

    Usa o estado filtrado a(t|t) do filtro de Kalman: a(t+h|t) = T·a(t+h−1|t) + c e
    y(t+h|t) = d + Z·a(t+h|t).
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        filtrado = ajustado.apply(serie)
    f = filtrado.filter_results
    transicao = f.transition[:, :, 0]
    intercepto = f.state_intercept[:, 0]
    desenho = f.design[0, :, 0]
    constante = float(f.obs_intercept[0, 0])
    estado = np.asarray(f.filtered_state)  # (estados × dias)
    soma = np.zeros(estado.shape[1])
    for _ in range(horizonte):
        estado = transicao @ estado + intercepto[:, None]
        soma += constante + desenho @ estado
    return soma


def probabilidade_de_subir(
    ajustado: object, serie: np.ndarray, horizonte: int
) -> np.ndarray:
    variancia = float(ajustado.params[-1])  # sigma2 é o último parâmetro do SARIMAX
    desvio = np.sqrt(max(variancia, 1e-12) * horizonte)
    return norm.cdf(soma_prevista(ajustado, serie, horizonte) / desvio)


def prever_divisao(
    serie: np.ndarray,
    linhas_por_ativo: list[np.ndarray],
    treino: np.ndarray,
    teste: np.ndarray,
    horizonte: int,
    embaralhar_com: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Probabilidades nas linhas de treino e de teste do painel (0,5 onde o ativo não ajustou).

    `serie` é o `retorno_1d` de todas as linhas do painel; `linhas_por_ativo`, as linhas de cada
    ativo em ordem de data. Com `embaralhar_com`, os valores de treino de cada ativo são sorteados
    entre si (sem ordem no tempo não há o que um ARIMA aprender): a variante "embaralhado".
    """
    n = serie.shape[0]
    p = np.full(n, 0.5)
    em_treino = np.zeros(n, dtype=bool)
    em_treino[treino] = True
    rng = np.random.default_rng(embaralhar_com) if embaralhar_com is not None else None
    for linhas in linhas_por_ativo:
        valores = serie[linhas]
        de_treino = em_treino[linhas] & ~np.isnan(valores)
        if de_treino.sum() < MINIMO_DE_TREINO:
            continue
        para_ajustar = np.where(de_treino, valores, np.nan)
        if rng is not None:
            para_ajustar[de_treino] = rng.permutation(para_ajustar[de_treino])
        ajustado = ajustar(para_ajustar)
        if ajustado is None:
            continue
        p[linhas] = probabilidade_de_subir(ajustado, valores, horizonte)
    return p[treino], p[teste]
