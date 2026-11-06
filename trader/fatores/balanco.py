"""Fatores de balanço de uma empresa, só com o que era público na véspera de cada decisão.

Tudo passa por `balanco_na_vespera` (`trader/base_local.py`) ou pela mesma regra (`como_era_em` na
véspera), em cima da base "como era na data" das demonstrações da CVM. Contas do plano de contas da
CVM (consolidado por padrão): 1 = ativo total, 3.03 = resultado bruto, 3.11 = lucro líquido,
6.01 = caixa das atividades operacionais. Fluxos (DRE, DFC) usam o ano fechado (`meses=12`).
"""

from __future__ import annotations

import pandas as pd

from base.ponto_no_tempo import como_era_em
from trader.base_local import UM_DIA, DadoAusenteError, balanco_na_vespera

ATIVO_TOTAL = "1"
RESULTADO_BRUTO = "3.03"
LUCRO_LIQUIDO = "3.11"
CAIXA_OPERACIONAL = "6.01"
MESES_DO_ANO = 12


def rentabilidade_bruta(
    base: pd.DataFrame,
    datas: pd.DatetimeIndex,
    cnpj: str,
    grupo: str = "con",
    aceitar_vazio: bool = False,
) -> pd.Series:
    """Resultado bruto do último ano fechado dividido pelo ativo total mais recente."""
    bruto = balanco_na_vespera(
        base, datas, cnpj, RESULTADO_BRUTO, grupo, MESES_DO_ANO, aceitar_vazio
    )
    ativo = balanco_na_vespera(
        base, datas, cnpj, ATIVO_TOTAL, grupo, aceitar_vazio=aceitar_vazio
    )
    return (bruto / ativo).rename("rentabilidade_bruta")


def accruals(
    base: pd.DataFrame,
    datas: pd.DatetimeIndex,
    cnpj: str,
    grupo: str = "con",
    aceitar_vazio: bool = False,
) -> pd.Series:
    """(Lucro líquido - caixa operacional) do último ano fechado, dividido pelo ativo total.

    Lucro que não virou caixa: quanto maior, pior a qualidade do lucro (Sloan, 1996).
    """
    lucro = balanco_na_vespera(
        base, datas, cnpj, LUCRO_LIQUIDO, grupo, MESES_DO_ANO, aceitar_vazio
    )
    caixa = balanco_na_vespera(
        base, datas, cnpj, CAIXA_OPERACIONAL, grupo, MESES_DO_ANO, aceitar_vazio
    )
    ativo = balanco_na_vespera(
        base, datas, cnpj, ATIVO_TOTAL, grupo, aceitar_vazio=aceitar_vazio
    )
    return ((lucro - caixa) / ativo).rename("accruals")


def _crescimento_na_data(ativos: pd.DataFrame, dia: pd.Timestamp) -> float:
    foto = como_era_em(ativos, dia - UM_DIA)
    if foto.empty:
        return float("nan")
    fim = foto["fim"].max()
    atual = foto.loc[foto["fim"] == fim, "valor"]
    anterior = foto.loc[foto["fim"] == fim - pd.DateOffset(years=1), "valor"]
    if anterior.empty:
        return float("nan")
    return float(atual.iloc[0] / anterior.iloc[0] - 1)


def crescimento_do_ativo(
    base: pd.DataFrame,
    datas: pd.DatetimeIndex,
    cnpj: str,
    grupo: str = "con",
    aceitar_vazio: bool = False,
) -> pd.Series:
    """Ativo total do balanço mais recente sobre o do mesmo mês um ano antes, menos 1.

    Os dois valores vêm da mesma foto da véspera: se o ano anterior foi reapresentado, vale o valor
    reapresentado que já era público.
    """
    ativos = base[
        (base["cnpj"] == cnpj)
        & (base["conta"] == ATIVO_TOTAL)
        & (base["grupo"] == grupo)
    ]
    valores = []
    for data in datas:
        dia = pd.Timestamp(data)
        valor = _crescimento_na_data(ativos, dia)
        if pd.isna(valor) and not aceitar_vazio:
            raise DadoAusenteError(
                f"{cnpj}: sem dois anos de ativo total públicos na véspera de {dia:%Y-%m-%d}."
            )
        valores.append(valor)
    return pd.Series(
        valores, index=pd.DatetimeIndex(datas), name="crescimento_do_ativo", dtype=float
    )
