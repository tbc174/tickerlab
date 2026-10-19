"""Concentração de um mercado: CR4 e HHI, com a régua do CADE (molde D, plano de 19/10/2026).

A régua é a do Guia para Análise de Atos de Concentração Horizontal do CADE (2016, p. 25): HHI abaixo
de 1.500 pontos, mercado não concentrado; de 1.500 a 2.500, moderadamente concentrado; acima de
2.500, altamente concentrado. O HHI é a soma dos quadrados das participações em %, de 0 a 10.000; a
CR4 é a participação somada das 4 maiores, como a do Banco Central no Relatório de Economia Bancária.
A faixa é a do Guia, não um juízo nosso, e o mercado aqui é o nacional da agência, não o mercado
relevante de uma análise do CADE.
"""

import pandas as pd

HHI_NAO_CONCENTRADO = 1_500  # abaixo disso: não concentrado (Guia H do CADE)
HHI_ALTAMENTE_CONCENTRADO = (
    2_500  # acima disso: altamente concentrado; entre os dois, moderado
)
MAIORES_DA_CR = 4
PONTOS_POR_FRACAO = 100  # participação em %, ao quadrado: monopólio = 100² = 10.000
MESES_NO_ANO = 12

NAO_CONCENTRADO = "não concentrado"
MODERADO = "moderadamente concentrado"
ALTO = "altamente concentrado"


def participacoes(valores: pd.Series) -> pd.Series:
    """A fração de cada participante no total; zero e vazio não participam."""
    positivos = pd.to_numeric(valores, errors="coerce")
    positivos = positivos[positivos > 0]
    return positivos / positivos.sum()


def hhi(valores: pd.Series) -> float | None:
    """Soma dos quadrados das participações em % (None: mercado sem ninguém)."""
    fracoes = participacoes(valores)
    if fracoes.empty:
        return None
    return float(((fracoes * PONTOS_POR_FRACAO) ** 2).sum())


def cr4(valores: pd.Series) -> float | None:
    """Fração do mercado somada pelas 4 maiores (com menos de 4, todas)."""
    fracoes = participacoes(valores)
    if fracoes.empty:
        return None
    return float(fracoes.nlargest(MAIORES_DA_CR).sum())


def faixa_do_cade(valor: float) -> str:
    """A faixa do Guia H: as bordas (1.500 e 2.500) ficam no moderado."""
    if valor < HHI_NAO_CONCENTRADO:
        return NAO_CONCENTRADO
    if valor <= HHI_ALTAMENTE_CONCENTRADO:
        return MODERADO
    return ALTO


def _do_ano(dados: pd.DataFrame) -> pd.Series:
    valores = dados["valor"]
    indice = hhi(valores)
    return pd.Series(
        {
            "participantes": int(participacoes(valores).size),
            "total": float(pd.to_numeric(valores, errors="coerce").sum()),
            "cr4": cr4(valores),
            "hhi": indice,
            "faixa": None if indice is None else faixa_do_cade(indice),
            "meses": int(dados["meses"].iloc[0]),
            "ultimo_mes": dados["ultimo_mes"].iloc[0],
        }
    )


def concentracao_por_ano(dados: pd.DataFrame) -> pd.DataFrame:
    """De (ano, participante, valor, meses, ultimo_mes) para uma linha por ano, o mais novo primeiro.

    `delta_hhi` é a variação contra o ano anterior, só entre dois anos seguidos e completos: o ano
    pela metade (o corrente) mostra o HHI dos meses que há, mas não compara.
    """
    colunas = [
        "ano",
        "participantes",
        "total",
        "cr4",
        "hhi",
        "faixa",
        "delta_hhi",
        "meses",
        "ultimo_mes",
    ]
    if dados.empty:
        return pd.DataFrame(columns=colunas)
    por_ano = (
        dados.groupby("ano")[["valor", "meses", "ultimo_mes"]]
        .apply(_do_ano)
        .reset_index()
        .sort_values("ano")
    )
    anterior = por_ano.shift(1)
    comparavel = (
        (anterior["ano"] == por_ano["ano"] - 1)
        & (anterior["meses"] == MESES_NO_ANO)
        & (por_ano["meses"] == MESES_NO_ANO)
    )
    por_ano["delta_hhi"] = (por_ano["hhi"] - anterior["hhi"]).where(comparavel)
    por_ano["participantes"] = por_ano["participantes"].astype(int)
    por_ano["meses"] = por_ano["meses"].astype(int)
    return por_ano.sort_values("ano", ascending=False)[colunas].reset_index(drop=True)
