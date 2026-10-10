"""Correlação entre ativos e beta contra um índice.

- Correlação: se dois ativos andam juntos (de −1 a +1), medida nos retornos diários.
- Beta: quanto o ativo costuma se mexer para cada 1% que o índice se mexe (inclinação da reta de
  regressão do retorno do ativo contra o do índice). Beta 1,5 = amplifica o índice em 50%.
- Alfa: o retorno anual que sobra depois de descontar o que o beta explica.
- Correlação nas quedas: a correlação medida só nos piores dias do índice. Atenção: escolher só
  dias extremos do índice reduz a correlação por construção (menos variação para a reta
  explicar), então ela não deve ser lida como "a diversificação melhorou nas crises".
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src import indicadores as ind

MIN_DIAS = 30
Z_95 = 1.96


@dataclass(frozen=True)
class ResultadoDoBeta:
    beta: float
    beta_minimo: float  # extremos do intervalo de ~95%
    beta_maximo: float
    alfa_anual: float
    correlacao: float
    r_quadrado: float  # fração da variação do ativo que o índice explica


def calcular_retornos(alinhado: pd.DataFrame) -> pd.DataFrame:
    """Retornos diários de cada coluna de preços (a primeira linha, sem retorno, sai)."""
    return alinhado.pct_change().dropna()


def calcular_beta(
    retorno_do_ativo: pd.Series, retorno_do_indice: pd.Series
) -> ResultadoDoBeta:
    """Regressão por mínimos quadrados do ativo contra o índice, nos dias em comum."""
    tabela = pd.concat(
        [retorno_do_ativo, retorno_do_indice], axis=1, join="inner"
    ).dropna()
    if len(tabela) < MIN_DIAS:
        raise ValueError(
            f"São necessários pelo menos {MIN_DIAS} dias em comum para o beta."
        )
    y, x = tabela.iloc[:, 0].to_numpy(), tabela.iloc[:, 1].to_numpy()
    variacao_x = float(((x - x.mean()) ** 2).sum())
    if variacao_x == 0:
        raise ValueError("O índice não variou no período: o beta não existe.")
    beta = float(((x - x.mean()) * (y - y.mean())).sum() / variacao_x)
    alfa_diario = float(y.mean() - beta * x.mean())
    residuo = y - alfa_diario - beta * x
    erro_padrao = float(np.sqrt((residuo**2).sum() / (len(y) - 2) / variacao_x))
    correlacao = float(np.corrcoef(x, y)[0, 1])
    return ResultadoDoBeta(
        beta=beta,
        beta_minimo=beta - Z_95 * erro_padrao,
        beta_maximo=beta + Z_95 * erro_padrao,
        alfa_anual=alfa_diario * ind.DIAS_POR_ANO,
        correlacao=correlacao,
        r_quadrado=correlacao**2,
    )


def resumir_betas(retornos: pd.DataFrame, indice: str) -> pd.DataFrame:
    """Uma linha por ativo (menos o índice) com beta, intervalo, alfa, correlação e R²."""
    if indice not in retornos.columns:
        raise ValueError(f"O índice {indice} não está na tabela de retornos.")
    linhas = {}
    for ativo in retornos.columns.drop(indice):
        r = calcular_beta(retornos[ativo], retornos[indice])
        linhas[ativo] = {
            "Beta": r.beta,
            "Beta (mín. 95%)": r.beta_minimo,
            "Beta (máx. 95%)": r.beta_maximo,
            "Alfa anual": r.alfa_anual,
            "Correlação": r.correlacao,
            "R²": r.r_quadrado,
        }
    if not linhas:
        raise ValueError("Escolha pelo menos um ativo além do índice.")
    return pd.DataFrame(linhas).T


def calcular_beta_movel(
    retorno_do_ativo: pd.Series, retorno_do_indice: pd.Series, janela: int = 126
) -> pd.Series:
    """Beta calculado só com os últimos `janela` dias, para ver como ele muda no tempo."""
    if janela < MIN_DIAS:
        raise ValueError(f"A janela precisa ter pelo menos {MIN_DIAS} dias.")
    tabela = pd.concat(
        [retorno_do_ativo, retorno_do_indice], axis=1, join="inner"
    ).dropna()
    ativo, indice = tabela.iloc[:, 0], tabela.iloc[:, 1]
    covariancia = ativo.rolling(janela).cov(indice)
    variancia = indice.rolling(janela).var().replace(0, np.nan)
    return (covariancia / variancia).dropna()


def calcular_correlacao_movel(
    retorno_a: pd.Series, retorno_b: pd.Series, janela: int = 126
) -> pd.Series:
    if janela < MIN_DIAS:
        raise ValueError(f"A janela precisa ter pelo menos {MIN_DIAS} dias.")
    tabela = pd.concat([retorno_a, retorno_b], axis=1, join="inner").dropna()
    return tabela.iloc[:, 0].rolling(janela).corr(tabela.iloc[:, 1]).dropna()


def calcular_correlacao_nas_quedas(
    retornos: pd.DataFrame, indice: str, fracao: float = 0.1
) -> pd.DataFrame:
    """Correlação de cada ativo com o índice em todos os dias e só nos piores dias do índice."""
    if indice not in retornos.columns:
        raise ValueError(f"O índice {indice} não está na tabela de retornos.")
    if not 0 < fracao < 0.5:
        raise ValueError("A fração dos piores dias deve ficar entre 0 e 0,5.")
    limite = retornos[indice].quantile(fracao)
    piores = retornos[retornos[indice] <= limite]
    if len(piores) < 10:
        raise ValueError("Há poucos dias de queda para calcular a correlação neles.")
    ativos = retornos.columns.drop(indice)
    return pd.DataFrame(
        {
            "Todos os dias": [retornos[a].corr(retornos[indice]) for a in ativos],
            "Piores dias do índice": [piores[a].corr(piores[indice]) for a in ativos],
        },
        index=ativos,
    )
