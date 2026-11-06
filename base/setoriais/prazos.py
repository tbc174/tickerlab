"""Desde quando cada número das fontes setoriais era público ("como era na data").

As fontes não dizem quando publicaram cada mês. Medido em 14/10/2026 (baixadas do arquivista): a ANAC
e a ANP tinham agosto/2026 publicado (44 dias depois do fim do mês) e ainda não setembro; o ONS tinha o
dia anterior inteiro. Série 4, PR 5: a Anatel também tinha agosto/2026; o SAMP da ANEEL gerado em
15/09/2026 tinha julho completo (103 distribuidoras, 46 dias) e agosto pela metade (30); a ANS, abaixo. A regra usa folga sobre o medido: pode atrasar um número, nunca adiantar. As
próximas baixadas do arquivista permitem conferir a regra mês a mês.
"""

import pandas as pd

ATRASO_MEDIDO_MENSAL = (
    44  # dias entre o fim de agosto/2026 e a baixada de 14/10/2026 (ANAC e ANP)
)
DIAS_ATE_PUBLICAR_MENSAL = 60
DIAS_ATE_PUBLICAR_ONS = 2  # a geração do dia sai no dia seguinte
# ANS (beneficiários por operadora): o arquivo de 08/08/2026 trazia até junho/2026 (39 dias) e ainda era
# o mesmo em 14/10/2026: a ANS não republica todo mês, e a regra dá folga sobre os 39 dias medidos
ATRASO_MEDIDO_ANS = 39
DIAS_ATE_PUBLICAR_ANS = 90


def fim_do_mes(ano: pd.Series, mes: pd.Series) -> pd.Series:
    """O último dia do mês (a competência), a partir das colunas de ano e mês da fonte."""
    inicio = pd.to_datetime(
        pd.DataFrame({"year": ano.astype(int), "month": mes.astype(int), "day": 1})
    )
    return inicio + pd.offsets.MonthEnd(0)


def disponivel_mensal(competencia: pd.Series) -> pd.Series:
    return competencia + pd.Timedelta(days=DIAS_ATE_PUBLICAR_MENSAL)


def disponivel_ans(competencia: pd.Series) -> pd.Series:
    return competencia + pd.Timedelta(days=DIAS_ATE_PUBLICAR_ANS)


def disponivel_ons(instante: pd.Series) -> pd.Series:
    return instante + pd.Timedelta(days=DIAS_ATE_PUBLICAR_ONS)


# PLD da CCEE (série T, PR T6). Só há uma captura (14/10/2026): o preço do dia 14/10 já estava no arquivo
# das 5h UTC, ou seja, sai no dia anterior; a regra conta o fim do dia + 1 dia (nunca adianta). A média
# do mês sai depois do mês (2 dias de folga), e o preço semanal de antes de 2021 tem 7 dias de folga.
DIAS_ATE_PUBLICAR_PLD_DIARIO = 1
DIAS_ATE_PUBLICAR_PLD_SEMANAL = 7
DIAS_ATE_PUBLICAR_PLD_MENSAL = 2


def disponivel_pld(
    referencia: pd.Series, competencia: pd.Series, granularidade: str
) -> pd.Series:
    """Desde quando o preço era público: hora e dia pelo dia, semana pelo início, mês pelo fim do mês."""
    if granularidade == "mes":
        return competencia + pd.Timedelta(days=DIAS_ATE_PUBLICAR_PLD_MENSAL)
    if granularidade == "semana_por_patamar":
        return referencia + pd.Timedelta(days=DIAS_ATE_PUBLICAR_PLD_SEMANAL)
    return referencia.dt.normalize() + pd.Timedelta(days=DIAS_ATE_PUBLICAR_PLD_DIARIO)
