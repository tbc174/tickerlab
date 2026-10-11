"""Atributos e rótulo da M2, num painel único (uma linha por ativo e dia).

Tudo o que está na linha do dia t usa só informação até o fechamento de t (do próprio ativo) ou
até a véspera (macro, de bolsas com outro horário). O rótulo olha para a frente de propósito: é o
que o modelo tenta prever, e o CPCV expurga as datas em que ele vazaria para o teste.

Atributos do ativo (todos divididos pela volatilidade, para comparar ativos diferentes):
- retornos de 1, 5, 21, 63, 126 e 252 pregões, em desvios-padrão;
- volatilidade anual e a razão volatilidade de 21 dias / de 252 dias;
- a previsão de tendência da B1 (−1 a +1);
- carry anual dividido pela volatilidade (juros reais do BIS);
- distância da máxima e da mínima de 252 pregões, em volatilidades anuais;
- a classe do ativo (forex, ações da B3...), como colunas 0/1.
Macro (iguais para todos os ativos no dia, sempre da véspera): VIX (nível padronizado e variação de
5 dias), juro de 10 anos americano (variação de 21 dias), índice do dólar, petróleo e cobre
(retorno de 21 dias em desvios-padrão).

Rótulo: 1 se a soma dos retornos dos próximos 5 pregões for positiva, 0 se não.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trader import baselines, juros
from trader.holdout import carregar_desenvolvimento
from trader.universo import UNIVERSO

HORIZONTE_DO_ROTULO = 5
HORIZONTES = (1, 5, 21, 63, 126, 252)
CLASSES = ("acoes_b3", "cambio", "cripto", "etfs", "forex", "indices", "metais")
MACRO = {  # nome do atributo: (arquivo da série, transformação)
    "vix": "IDX_VIX",
    "juro_10a": "IDX_TNX",
    "dolar": "DX_Y.NYB",
    "petroleo": "CL_F",
    "cobre": "HG_F",
}
ATRIBUTOS_DO_ATIVO = (
    *(f"retorno_{h}d" for h in HORIZONTES),
    "volatilidade_anual",
    "razao_de_volatilidade",
    "tendencia",
    "carry",
    "distancia_da_maxima",
    "distancia_da_minima",
)
ATRIBUTOS_MACRO = (
    "vix_nivel",
    "vix_5d",
    "juro_10a_21d",
    "dolar_21d",
    "petroleo_21d",
    "cobre_21d",
)
ATRIBUTOS = (*ATRIBUTOS_DO_ATIVO, *ATRIBUTOS_MACRO, *(f"classe_{c}" for c in CLASSES))


def _desvio_diario(retorno: pd.Series) -> pd.Series:
    return retorno.ewm(span=35, min_periods=20).std()


def atributos_do_ativo(
    retorno: pd.Series,
    dias_por_ano: int,
    carry_anual: pd.Series | None = None,
) -> pd.DataFrame:
    """Atributos de um ativo a partir dos retornos diários (só passado e presente)."""
    desvio = _desvio_diario(retorno).where(lambda d: d > 0)
    tabela = pd.DataFrame(index=retorno.index)
    for h in HORIZONTES:
        tabela[f"retorno_{h}d"] = retorno.rolling(h).sum() / (desvio * np.sqrt(h))
    vol_anual = desvio * np.sqrt(dias_por_ano)
    tabela["volatilidade_anual"] = vol_anual
    tabela["razao_de_volatilidade"] = (
        retorno.rolling(21).std() / retorno.rolling(252, min_periods=126).std()
    )
    tabela["tendencia"] = baselines.previsao_b1(retorno) / baselines.TETO_DA_PREVISAO
    tabela["carry"] = (
        carry_anual.reindex(retorno.index) / vol_anual
        if carry_anual is not None
        else 0.0
    )
    preco = baselines.preco_sintetico(retorno)
    tabela["distancia_da_maxima"] = (
        preco / preco.rolling(252, min_periods=126).max() - 1
    ) / vol_anual
    tabela["distancia_da_minima"] = (
        preco / preco.rolling(252, min_periods=126).min() - 1
    ) / vol_anual
    return tabela


def _da_vespera(serie: pd.DataFrame, datas: pd.DatetimeIndex) -> pd.DataFrame:
    """Valor conhecido até a véspera de cada data (macro de bolsas com outro horário)."""
    deslocada = serie.copy()
    deslocada.index = deslocada.index + pd.Timedelta(days=1)
    uniao = deslocada.index.union(datas)
    return deslocada.reindex(uniao).ffill().reindex(datas)


def atributos_macro(
    fechamentos: dict[str, pd.Series], datas: pd.DatetimeIndex
) -> pd.DataFrame:
    """`fechamentos` com as chaves de `MACRO`. Devolve as colunas de `ATRIBUTOS_MACRO`, da véspera."""
    tabela = pd.DataFrame(index=fechamentos["vix"].index)
    vix = fechamentos["vix"]
    tabela["vix_nivel"] = (
        vix - vix.rolling(252, min_periods=126).mean()
    ) / vix.rolling(252, min_periods=126).std()
    tabela["vix_5d"] = np.log(vix / vix.shift(5))
    tabela = tabela.join(
        (fechamentos["juro_10a"] - fechamentos["juro_10a"].shift(21)).rename(
            "juro_10a_21d"
        ),
        how="outer",
    )
    for nome in ("dolar", "petroleo", "cobre"):
        preco = fechamentos[nome].where(fechamentos[nome] > 0)
        retorno = preco.pct_change(fill_method=None)
        normalizado = retorno.rolling(21).sum() / (
            _desvio_diario(retorno) * np.sqrt(21)
        )
        tabela = tabela.join(normalizado.rename(f"{nome}_21d"), how="outer")
    return _da_vespera(tabela[list(ATRIBUTOS_MACRO)], datas)


def rotulo(retorno: pd.Series, horizonte: int = HORIZONTE_DO_ROTULO) -> pd.Series:
    """1 se a soma dos próximos `horizonte` retornos for positiva; vazio no fim da série."""
    futuro = retorno[::-1].rolling(horizonte).sum()[::-1].shift(-1)
    return (futuro > 0).astype(float).where(futuro.notna())


def carregar_macro() -> dict[str, pd.Series]:
    return {
        nome: carregar_desenvolvimento(arquivo)["Close"]
        for nome, arquivo in MACRO.items()
    }


def montar_painel(
    series: list,
    taxas: pd.DataFrame | None,
    macro: dict[str, pd.Series],
    inicio: pd.Timestamp,
    fim: pd.Timestamp,
) -> pd.DataFrame:
    """Painel com `Date`, `simbolo`, `classe`, os ATRIBUTOS, `y` e `retorno_futuro`.

    `series` são os `SerieDoAtivo` de `trader.rodar_baselines.carregar_series` (retornos já limpos).
    """
    partes = []
    for s in series:
        carry = (
            juros.carry_anual(s.ativo, s.retorno.index, taxas)
            if taxas is not None
            else None
        )
        tabela = atributos_do_ativo(s.retorno, s.dias_por_ano, carry)
        tabela["y"] = rotulo(s.retorno)
        tabela["retorno_futuro"] = (
            s.retorno[::-1].rolling(HORIZONTE_DO_ROTULO).sum()[::-1].shift(-1)
        )
        tabela = tabela.loc[(tabela.index >= inicio) & (tabela.index <= fim)]
        tabela = tabela.join(atributos_macro(macro, tabela.index))
        for c in CLASSES:
            tabela[f"classe_{c}"] = float(s.ativo.classe == c)
        tabela.insert(0, "simbolo", s.ativo.simbolo)
        tabela.insert(1, "classe", s.ativo.classe)
        partes.append(tabela)
    painel = pd.concat(partes).rename_axis("Date").reset_index()
    return painel.replace([np.inf, -np.inf], np.nan)


def ativos_operaveis() -> list:
    return [a for a in UNIVERSO if a.papel == "operar"]
