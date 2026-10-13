"""Resumo diário da rede do Bitcoin, "como era na data" (base de cripto, série 1, PR 2).

Junta as linhas de blocos (`leitura.ler_blocos`) por dia UTC, pela hora de cada bloco, e acrescenta a
fração parada há mais de um ano (`leitura.ler_parado`).

**Quando o dia passa a valer (`divulgado_em`):** um dia D só está completo quando nenhum bloco
futuro pode mais cair nele. Como a hora de um bloco novo tem de ser maior que a hora mediana dos 11
anteriores, isso acontece no primeiro bloco com a hora mediana na meia-noite que encerra D ou depois.
E o dia só "existe" para a base quando esse bloco tem as mesmas 6 confirmações da leitura: o
`divulgado_em` é a hora do bloco da 6ª confirmação. Dia que ainda não chegou lá fica de fora.
"""

import pandas as pd

from base.cripto.leitura import CONFIRMACOES

SOMAS = [
    "n_transacoes",
    "taxas_total",
    "valor_movimentado",
    "dias_moeda_destruidos",
    "emissao",
]


def resumo_diario(
    blocos: pd.DataFrame, parado: pd.DataFrame, confirmacoes: int = CONFIRMACOES
) -> pd.DataFrame:
    """Uma linha por dia UTC fechado: somas, taxa mediana (mediana das medianas dos blocos),
    dificuldade do último bloco, fração parada, `divulgado_em` e `coletado_em`."""
    if blocos.empty:
        return pd.DataFrame()
    blocos = blocos.sort_values("altura").assign(
        dia=lambda b: b["hora"].dt.floor("D").dt.date
    )
    agrupado = blocos.groupby("dia")
    dias = agrupado[SOMAS].sum()
    dias["n_blocos"] = agrupado.size()
    dias["taxa_mediana_por_vbyte"] = agrupado["taxa_mediana_por_vbyte"].median()
    dias["dificuldade"] = agrupado["dificuldade"].last()
    dias["coletado_em"] = agrupado["coletado_em"].max()
    dias["divulgado_em"] = [
        _divulgado_em(blocos, dia, confirmacoes) for dia in dias.index
    ]
    dias = dias.dropna(subset=["divulgado_em"]).reset_index()
    if not parado.empty:
        dias = dias.merge(parado[["dia", "fracao_parada_1_ano"]], on="dia", how="left")
    return dias


def _divulgado_em(
    blocos: pd.DataFrame, dia: object, confirmacoes: int
) -> pd.Timestamp | None:
    """A hora do bloco que deu a última confirmação ao fechamento do dia, ou None se não fechou."""
    fim_do_dia = pd.Timestamp(dia, tz="UTC") + pd.Timedelta(days=1)
    # a hora mediana só cresce, então a busca binária acha o primeiro bloco que fecha o dia
    posicao = int(blocos["hora_mediana"].searchsorted(fim_do_dia, side="left"))
    if posicao >= len(blocos):
        return None
    confirmacao = blocos["altura"].iloc[posicao] + confirmacoes - 1
    hora = blocos.loc[blocos["altura"] == confirmacao, "hora"]
    return hora.iloc[0] if not hora.empty else None
