"""Bloco "demonstrações" da amostra integrada: o balanço e o resultado como eram na data.

Lê a base "como era na data" das demonstrações (`demonstracoes_como_era`, série 1): cada valor de cada
conta em cada versão de cada DFP e ITR, com o dia da entrega (`divulgado_em`). Para cada companhia e
fim de mês, cada indicador vem em dois passos:
1. o período mais novo **já público** na data (o fim do trimestre ou do exercício);
2. o valor desse período na versão mais nova já entregue na data (uma reapresentação só vale depois
   de entregue).

Três grupos de colunas, cada um com o fim do período e o dia em que ficou público:
- **balanço** (saldo na data do período): ativo total, caixa, patrimônio líquido e dívida bruta
  (empréstimos e financiamentos de curto e longo prazo);
- **acumulado no ano** (o período mais longo do documento mais novo: do início do exercício ao fim do
  trimestre): receita, EBIT e lucro;
- **anual** (o exercício da DFP mais nova): receita, EBIT e lucro.

A conta é escolhida pelo código **e** pela descrição: o plano de contas dos bancos é outro (a conta 3.05
é "Resultado antes dos tributos", não o EBIT), e uma conta que não bate fica vazia em vez de errada.
Vale o consolidado; sem consolidado no período, o individual (`*_grupo` diz qual).
"""

import pandas as pd

from base.amostra.como_era import DATA, Entrada

ENTRADAS = {"demonstracoes": Entrada(publico_em="divulgado_em", termina_em="ate")}
CONSOLIDADO, INDIVIDUAL = "con", "ind"
UM_ANO = pd.Timedelta(days=360)
COLUNAS_DOS_FATOS = (
    "cnpj",
    "grupo",
    "indicador",
    "inicio",
    "fim",
    "valor",
    "divulgado_em",
)
# indicador -> (demonstração, contas aceitas, começo aceito da descrição)
INDICADORES = {
    "ativo_total": ("BPA", ("1",), ("Ativo Total",)),
    "caixa": ("BPA", ("1.01.01", "1.01"), ("Caixa e Equivalentes",)),
    "patrimonio_liquido": ("BPP", ("2.03", "2.07", "2.08"), ("Patrimônio Líquido",)),
    "divida_bruta": ("BPP", ("2.01.04", "2.02.01"), ("Empréstimos e Financiamentos",)),
    "receita": ("DRE", ("3.01",), ("Receita de Venda", "Receitas de Venda", "Receitas da Intermediação")),
    "ebit": ("DRE", ("3.05",), ("Resultado Antes do Resultado Financeiro",)),
    "lucro": ("DRE", ("3.09", "3.11", "3.13"), ("Lucro/Prejuízo Consolidado do Período", "Lucro/Prejuízo do Período")),
}  # fmt: skip
DO_BALANCO = ("ativo_total", "caixa", "patrimonio_liquido", "divida_bruta")
DO_RESULTADO = ("receita", "ebit", "lucro")
COLUNAS = (
    "cnpj", "data",
    "balanco_fim", "balanco_publico_em", "balanco_grupo", *DO_BALANCO,
    "acumulado_inicio", "acumulado_fim", "acumulado_publico_em", "acumulado_grupo",
    *(f"{i}_acumulado" for i in DO_RESULTADO),
    "anual_fim", "anual_publico_em", "anual_grupo", *(f"{i}_anual" for i in DO_RESULTADO),
)  # fmt: skip


def _indicador(tabela: pd.DataFrame) -> pd.Series:
    indicador = pd.Series(None, index=tabela.index, dtype=object)
    descricao = tabela["descricao"].fillna("").str.strip()
    for nome, (demonstracao, contas, comecos) in INDICADORES.items():
        bate = (
            (tabela["demonstracao"] == demonstracao)
            & tabela["conta"].isin(contas)
            & descricao.str.startswith(comecos)
        )
        indicador = indicador.mask(bate & indicador.isna(), nome)
    return indicador


def fatos(demonstracoes: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por versão de cada indicador, companhia, grupo e período (a dívida bruta é a soma do
    curto e do longo prazo publicados juntos)."""
    tabela = demonstracoes.assign(indicador=_indicador(demonstracoes)).dropna(
        subset=["indicador"]
    )
    chave = ["cnpj", "grupo", "indicador", "inicio", "fim", "documento", "referencia", "versao",
             "ordem", "divulgado_em"]  # fmt: skip
    somados = tabela.groupby(chave, dropna=False, sort=False)["valor"].sum(min_count=1)
    juntos = somados.reset_index()
    for coluna in ("inicio", "fim", "divulgado_em"):
        juntos[coluna] = pd.to_datetime(juntos[coluna]).astype(DATA)
    return juntos


def _acumulados(fatos_do_resultado: pd.DataFrame) -> pd.DataFrame:
    """Do resultado, só o período mais longo de cada documento (o acumulado do ano, não o trimestre)."""
    documento = [
        "cnpj",
        "grupo",
        "indicador",
        "fim",
        "documento",
        "referencia",
        "versao",
        "ordem",
    ]
    mais_longo = fatos_do_resultado.groupby(documento)["inicio"].transform("min")
    return fatos_do_resultado[fatos_do_resultado["inicio"] == mais_longo]


def _mais_recente(grade: pd.DataFrame, serie: pd.DataFrame) -> pd.DataFrame:
    """Para cada (cnpj, grupo, indicador) da `serie` e cada data da grade: o fim mais novo já público
    e o valor dele na versão mais nova já pública (`valor`, `inicio`, `fim`, `publico_em`)."""
    chave = ["cnpj", "grupo", "indicador"]
    serie = serie.sort_values(["divulgado_em", "fim"], kind="stable")
    conhecido = serie[[*chave, "divulgado_em", "fim"]].copy()
    conhecido["fim"] = conhecido.groupby(chave)["fim"].cummax()
    pares = serie[chave].drop_duplicates()
    linhas = grade[["cnpj", "data"]].merge(pares, on="cnpj")
    linhas["data"] = pd.to_datetime(linhas["data"]).astype(DATA)
    linhas = pd.merge_asof(
        linhas.sort_values("data", kind="stable"), conhecido, left_on="data",
        right_on="divulgado_em", by=chave, direction="backward",
    ).drop(columns="divulgado_em").dropna(subset=["fim"])  # fmt: skip
    versoes = serie[[*chave, "fim", "divulgado_em", "inicio", "valor"]].rename(
        columns={"divulgado_em": "publico_em"}
    )
    return pd.merge_asof(
        linhas.sort_values("data", kind="stable"), versoes.sort_values("publico_em", kind="stable"),
        left_on="data", right_on="publico_em", by=[*chave, "fim"], direction="backward",
    )  # fmt: skip


def _bloco(grade: pd.DataFrame, serie: pd.DataFrame, indicadores: tuple[str, ...], sufixo: str,
           prefixo: str) -> pd.DataFrame:  # fmt: skip
    """As colunas de um grupo (balanço, acumulado ou anual): o período do indicador-guia (o primeiro),
    o consolidado antes do individual, e os outros indicadores só quando são do mesmo período."""
    recentes = _mais_recente(grade, serie[serie["indicador"].isin(indicadores)])
    guia = recentes[recentes["indicador"] == indicadores[0]]
    guia = guia.assign(_ordem=(guia["grupo"] != CONSOLIDADO).astype(int)).sort_values(
        "_ordem"
    )
    escolhido = guia.drop_duplicates(["cnpj", "data"])[
        ["cnpj", "data", "grupo", "inicio", "fim"]
    ]
    valores = recentes.merge(
        escolhido, on=["cnpj", "data", "grupo", "fim"], suffixes=("", "_guia")
    )
    largos = valores.pivot_table(
        index=["cnpj", "data"],
        columns="indicador",
        values="valor",
        aggfunc="first",
        dropna=False,
    )
    publico = valores.groupby(["cnpj", "data"])["publico_em"].max()
    saida = (
        escolhido.set_index(["cnpj", "data"]).join(largos).join(publico).reset_index()
    )
    nomes = {i: f"{i}{sufixo}" for i in indicadores}
    nomes |= {"inicio": f"{prefixo}_inicio", "fim": f"{prefixo}_fim", "grupo": f"{prefixo}_grupo",
              "publico_em": f"{prefixo}_publico_em"}  # fmt: skip
    return saida.rename(columns=nomes)


def montar(entradas: dict[str, pd.DataFrame], grade: pd.DataFrame) -> pd.DataFrame:
    """As colunas das demonstrações para cada linha da grade (cnpj, data)."""
    todos = fatos(entradas["demonstracoes"])
    balanco = todos[todos["indicador"].isin(DO_BALANCO)]
    resultado = _acumulados(todos[todos["indicador"].isin(DO_RESULTADO)])
    anual = resultado[(resultado["fim"] - resultado["inicio"]) >= UM_ANO]
    saida = grade[["cnpj", "data"]].assign(
        data=pd.to_datetime(grade["data"]).astype(DATA)
    )
    for parte in (
        _bloco(saida, balanco, DO_BALANCO, "", "balanco").drop(
            columns="balanco_inicio"
        ),
        _bloco(saida, resultado, DO_RESULTADO, "_acumulado", "acumulado"),
        _bloco(saida, anual, DO_RESULTADO, "_anual", "anual").drop(
            columns="anual_inicio"
        ),
    ):
        saida = saida.merge(parte, on=["cnpj", "data"], how="left")
    return (
        saida.reindex(columns=list(COLUNAS))
        .sort_values(["cnpj", "data"])
        .reset_index(drop=True)
    )
