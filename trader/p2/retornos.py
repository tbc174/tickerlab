"""Retorno diário de cada CFD, montado com preço + carry (pré-registro, seção 3; decisão 0014).

Para uma posição comprada de 1 unidade de capital, em cada dia com cotação:

    retorno_total = retorno_do_preço + carry_anual × dias_corridos / 365

O carry é o que a posição rende só por ficar aberta, sem o preço mudar:
- moedas BASE/COTAÇÃO: juro da base − juro da cotação;
- índices: dividendo − juro da moeda do índice;
- metais e energia: − juro do dólar;
- título de 10 anos: rendimento do título − juro do dólar.
A margem da corretora (custo de manter) não entra aqui: é custo, aplicado na carteira.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from trader.p2.mercados import Mercado

DIAS_DO_ANO = 365
ANOS_DO_TITULO = 10
CUPONS_POR_ANO = 2

JuroDaMoeda = Callable[[str, pd.DatetimeIndex], pd.Series]
Dividendo = Callable[[str, pd.DatetimeIndex], pd.Series]


def retorno_do_preco(precos: pd.Series) -> pd.Series:
    """Entre duas cotações seguidas, sobre o preço absoluto anterior (dá conta de preço negativo)."""
    precos = precos.dropna()
    anterior = precos.shift(1)
    return ((precos - anterior) / anterior.abs()).iloc[1:]


def duracao_modificada(rendimento: pd.Series | float) -> pd.Series | float:
    """Duração modificada de um título ao par de 10 anos com cupom semestral (rendimento em fração)."""
    y = np.maximum(np.asarray(rendimento, dtype=float), 1e-6)
    periodos = ANOS_DO_TITULO * CUPONS_POR_ANO
    duracao = (1 - (1 + y / CUPONS_POR_ANO) ** (-periodos)) / y
    return (
        pd.Series(duracao, index=rendimento.index)
        if isinstance(rendimento, pd.Series)
        else float(duracao)
    )


def retorno_do_titulo(rendimento_em_pct: pd.Series) -> pd.Series:
    """Variação de preço do título: − duração (com o rendimento da véspera) × variação do rendimento."""
    y = (rendimento_em_pct.dropna() / 100.0).sort_index()
    return (-duracao_modificada(y.shift(1)) * y.diff()).iloc[1:]


def moedas_do_par(codigo: str) -> tuple[str, str]:
    if len(codigo) != 6:
        raise ValueError(f"Não é um par de moedas: {codigo}")
    return codigo[:3], codigo[3:]


def carry_anual(
    mercado: Mercado,
    indice: pd.DatetimeIndex,
    juro: JuroDaMoeda,
    dividendo: Dividendo,
    rendimento_em_pct: pd.Series | None = None,
) -> pd.Series:
    """O que a posição comprada rende por ano só por ficar aberta, em cada data do índice."""
    if mercado.grupo == "moedas":
        base, cotacao = moedas_do_par(mercado.codigo)
        return juro(base, indice) - juro(cotacao, indice)
    if mercado.grupo == "indices":
        return dividendo(mercado.codigo, indice) - juro(mercado.moeda, indice)
    if mercado.grupo == "titulos":
        if rendimento_em_pct is None:
            raise ValueError("O carry do título precisa do rendimento.")
        rendimento = rendimento_em_pct.reindex(indice).ffill().shift(1) / 100.0
        return rendimento - juro("USD", indice)
    return -juro("USD", indice)  # metais e energia


def montar(
    mercado: Mercado,
    serie: pd.Series,
    juro: JuroDaMoeda,
    dividendo: Dividendo,
) -> pd.DataFrame:
    """Colunas `preco`, `carry_anual` e `total` (fração), uma linha por dia com cotação."""
    serie = serie.dropna().sort_index()
    preco = retorno_do_titulo(serie) if mercado.rendimento else retorno_do_preco(serie)
    rendimento = serie if mercado.rendimento else None
    carry = carry_anual(mercado, preco.index, juro, dividendo, rendimento)
    dias = serie.index.to_series().diff().dt.days.reindex(preco.index)
    total = preco + carry * dias / DIAS_DO_ANO
    return pd.DataFrame({"preco": preco, "carry_anual": carry, "total": total})
