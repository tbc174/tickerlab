"""Juros curtos diários de cada moeda, para o carry e o financiamento dos CFDs (pré-registro, seção 3).

Ordem de preferência em cada dia, sempre só com o que já era conhecido:
1. juro de 3 meses da OCDE (mensal, via FRED): o valor do mês m vale a partir do dia 1 do mês m+1;
2. taxa básica do banco central (BIS, diária): o valor de um dia vale a partir do dia seguinte;
3. trocas declaradas: euro antes de existir = juro de 3 meses da Alemanha; dólar de Hong Kong
   (atrelado ao dólar americano desde 1983) sem dado = juro do dólar.

Tudo em fração ao ano (0,05 = 5% ao ano).
"""

from __future__ import annotations

import pandas as pd

from trader.juros import taxa as taxa_do_bis

MOEDA_SUBSTITUTA = {"EUR": "DEM", "HKD": "USD"}


def mensal_para_diario(mensal_em_pct: pd.Series, indice: pd.DatetimeIndex) -> pd.Series:
    """Série mensal (% ao ano) em cada data do índice, valendo só a partir do mês seguinte."""
    serie = mensal_em_pct.dropna().sort_index()
    serie.index = (
        serie.index.to_period("M") + 1
    ).to_timestamp()  # publicado: vale no mês seguinte
    serie = serie[~serie.index.duplicated(keep="last")]
    alinhada = serie.reindex(serie.index.union(indice)).ffill().reindex(indice)
    return alinhada / 100.0


def juro_da_moeda(
    moeda: str,
    indice: pd.DatetimeIndex,
    ocde: dict[str, pd.Series],
    bis: pd.DataFrame | None = None,
) -> pd.Series:
    """Juro curto da moeda em cada data do índice (NaN onde nenhuma fonte cobre)."""
    juro = pd.Series(float("nan"), index=indice)
    if moeda in ocde:
        juro = mensal_para_diario(ocde[moeda], indice)
    if bis is not None and moeda in bis.columns:
        juro = juro.fillna(taxa_do_bis(bis, moeda, indice))
    substituta = MOEDA_SUBSTITUTA.get(moeda)
    if substituta and juro.isna().any():
        juro = juro.fillna(juro_da_moeda(substituta, indice, ocde, bis))
    return juro.rename(moeda)
