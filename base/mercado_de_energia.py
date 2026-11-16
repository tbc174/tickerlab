"""O mercado de energia do setor das elétricas: PLD, curtailment e capacidade instalada.

Os três números são de um mercado, não de uma companhia (`ccee_pld`, `ons_restricao`,
`ons_capacidade` não têm ligação à empresa): entram na seção `setor` das elétricas, ao lado do
mercado de consumidores. Tudo é "como era no dia da ficha": a base entrega só o que já era público
(`disponivel_em`) e, no curtailment, a revisão que o ONS só fez depois não conta.
"""

import pandas as pd

MESES_MOSTRADOS = 12  # a janela das tabelas mensais
ATRASO_DO_ONS_EM_DIAS = (
    2  # o dado de uma hora só é público 2 dias depois (`disponivel_em`)
)
COLUNAS_DO_PLD = ["referencia", "submercado", "pld", "disponivel_em"]
COLUNAS_DO_CURTAILMENT = ["mes", "tipo", "mwh", "disponivel_em"]
COLUNAS_DA_CAPACIDADE = ["tipo_de_usina", "unidades", "potencia_mw", "disponivel_em"]
SUBMERCADO_DE_REFERENCIA = (
    "Sudeste"  # o PLD que o item da ficha mostra; os 4 vão na tabela
)


def _mes_fechou(inicio: pd.Series, hoje: pd.Timestamp) -> pd.Series:
    """O mês inteiro já era público no dia (o último dado dele sai 2 dias depois do fim)."""
    fim = inicio + pd.offsets.MonthBegin(1)
    return fim + pd.Timedelta(days=ATRASO_DO_ONS_EM_DIAS) <= hoje


def pld_mensal(pld: pd.DataFrame, hoje: pd.Timestamp) -> pd.DataFrame:
    """O PLD médio de cada mês fechado e submercado, R$/MWh, dos últimos 12 meses (a média que a
    CCEE publica, sem refazer). `pld` traz `granularidade == "mes"`, já como era no dia."""
    if pld.empty:
        return pd.DataFrame(columns=COLUNAS_DO_PLD)
    mensal = pld[pld["granularidade"] == "mes"].copy()
    mensal["referencia"] = pd.to_datetime(mensal["referencia"]).dt.tz_localize(None)
    mensal = mensal[_mes_fechou(mensal["referencia"], hoje)]
    mensal = mensal.dropna(subset=["pld"])
    mensal["disponivel_em"] = pd.to_datetime(mensal["disponivel_em"]).dt.tz_localize(
        None
    )
    ultimo = mensal["referencia"].max()
    if pd.isna(ultimo):
        return pd.DataFrame(columns=COLUNAS_DO_PLD)
    desde = ultimo - pd.DateOffset(months=MESES_MOSTRADOS - 1)
    return (
        mensal[mensal["referencia"] >= desde][COLUNAS_DO_PLD]
        .sort_values(["referencia", "submercado"], ascending=[False, True])
        .reset_index(drop=True)
    )


def curtailment_mensal(horas: pd.DataFrame, hoje: pd.Timestamp) -> pd.DataFrame:
    """A energia que eólicas e solares deixaram de gerar por ordem do operador, MWh por mês fechado
    e tipo, dos últimos 12 meses. `horas` traz (instante, tipo, nao_realizada_mwmed) somados por
    hora; numa hora, MWmed é igual a MWh."""
    if horas.empty:
        return pd.DataFrame(columns=COLUNAS_DO_CURTAILMENT)
    tabela = horas.copy()
    tabela["instante"] = pd.to_datetime(tabela["instante"]).dt.tz_localize(None)
    tabela["mes"] = tabela["instante"].dt.to_period("M").dt.to_timestamp()
    por_mes = (
        tabela.groupby(["mes", "tipo"], as_index=False)["nao_realizada_mwmed"]
        .sum()
        .rename(columns={"nao_realizada_mwmed": "mwh"})
    )
    por_mes = por_mes[_mes_fechou(por_mes["mes"], hoje)].copy()
    por_mes["disponivel_em"] = (
        por_mes["mes"]
        + pd.offsets.MonthBegin(1)
        + pd.Timedelta(days=ATRASO_DO_ONS_EM_DIAS)
    )
    if por_mes.empty:
        return pd.DataFrame(columns=COLUNAS_DO_CURTAILMENT)
    desde = por_mes["mes"].max() - pd.DateOffset(months=MESES_MOSTRADOS - 1)
    return (
        por_mes[por_mes["mes"] >= desde][COLUNAS_DO_CURTAILMENT]
        .sort_values(["mes", "tipo"], ascending=[False, True])
        .reset_index(drop=True)
    )


def capacidade_por_tipo(capacidade: pd.DataFrame, hoje: pd.Timestamp) -> pd.DataFrame:
    """A potência efetiva (MW) das unidades em operação no dia, por tipo de usina: entrou em
    operação (ou em teste, quando falta) até o dia e não foi desativada até ele."""
    if capacidade.empty:
        return pd.DataFrame(columns=COLUNAS_DA_CAPACIDADE)
    unidades = capacidade.copy()
    entrada = pd.to_datetime(unidades["entrada_em_operacao"]).fillna(
        pd.to_datetime(unidades["entrada_em_teste"])
    )
    saida = pd.to_datetime(unidades["desativada_em"])
    em_operacao = (entrada <= hoje) & (saida.isna() | (saida > hoje))
    unidades = unidades[em_operacao].dropna(subset=["potencia_efetiva_mw"]).copy()
    unidades["disponivel_em"] = entrada[unidades.index]
    return (
        unidades.groupby("tipo_de_usina", as_index=False)
        .agg(
            unidades=("potencia_efetiva_mw", "size"),
            potencia_mw=("potencia_efetiva_mw", "sum"),
            disponivel_em=("disponivel_em", "max"),
        )
        .sort_values("potencia_mw", ascending=False)
        .reset_index(drop=True)
    )
