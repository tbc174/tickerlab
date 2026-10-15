"""Barras de 1 minuto a partir de negócios, e as conferências da qualidade delas.

Vale para qualquer fonte de negócios (IEX nos EUA; na B3, o arquivo de negócios do pregão). A barra
das 10:31 junta os negócios de 10:31:00 até 10:31:59,999 no horário da bolsa: o rótulo é o
**começo** do minuto, como no Yahoo e na maioria dos gráficos.
"""

import pandas as pd

COLUNAS_DAS_BARRAS = [
    "simbolo",
    "minuto",
    "abertura",
    "maxima",
    "minima",
    "fechamento",
    "volume",
    "negocios",
]
MINUTOS_NO_PREGAO_DOS_EUA = 390  # 9h30 às 16h, horário de Nova York


def montar_barras(negocios: pd.DataFrame, fuso: str) -> pd.DataFrame:
    """Uma linha por símbolo e minuto com negócio (minuto sem negócio não vira barra).

    `negocios` precisa das colunas instante (com fuso), simbolo, preco e quantidade, em qualquer
    ordem; `fuso` é o da bolsa ("America/New_York", "America/Sao_Paulo"). O minuto sai sem fuso,
    no horário da bolsa.
    """
    if negocios.empty:
        return pd.DataFrame(columns=COLUNAS_DAS_BARRAS)
    ordenados = negocios.sort_values("instante", kind="stable")
    minuto = (
        ordenados["instante"].dt.tz_convert(fuso).dt.floor("min").dt.tz_localize(None)
    )
    grupos = ordenados.assign(minuto=minuto).groupby(["simbolo", "minuto"], sort=True)
    barras = grupos.agg(
        abertura=("preco", "first"),
        maxima=("preco", "max"),
        minima=("preco", "min"),
        fechamento=("preco", "last"),
        volume=("quantidade", "sum"),
        negocios=("preco", "size"),
    )
    return barras.reset_index()[COLUNAS_DAS_BARRAS]


def cobertura_por_simbolo(
    barras: pd.DataFrame, minutos_no_pregao: int = MINUTOS_NO_PREGAO_DOS_EUA
) -> pd.Series:
    """Fração dos minutos do pregão que têm barra, por símbolo (1,0 = nenhum minuto vazio)."""
    return barras.groupby("simbolo")["minuto"].nunique() / minutos_no_pregao


def conferir_fechamentos(
    barras: pd.DataFrame, fechamentos_oficiais: pd.Series
) -> pd.DataFrame:
    """Último preço das barras do dia contra o fechamento oficial, por símbolo.

    `fechamentos_oficiais` tem o símbolo no índice. A diferença sai em fração (0,001 = 0,1%).
    Não precisa bater exatamente: o fechamento oficial vem do leilão da bolsa principal, e o
    último negócio de uma bolsa só pode ser de alguns segundos antes.
    """
    ultimo = barras.sort_values("minuto").groupby("simbolo")["fechamento"].last()
    tabela = pd.DataFrame(
        {"ultimo_das_barras": ultimo, "oficial": fechamentos_oficiais}
    )
    tabela = tabela.dropna()
    tabela["diferenca"] = tabela["ultimo_das_barras"] / tabela["oficial"] - 1
    return tabela


# --- B3 (plano dos intradiários grátis, PR 2) ----------------------------------------------------
# Regra medida em 14/10/2026 contra os boletins oficiais: abertura, máxima, mínima e fechamento só
# do pregão regular (sessão 1); volume e número de negócios também do after-market (sessão 6), aqui
# em colunas à parte. Uma linha com `cancelado` repete o identificador do negócio cancelado (o
# identificador é por instrumento): os dois saem. Negócios no mesmo milésimo se ordenam pelo
# identificador. `montar_barras` não serve aqui porque as barras de um arquivo de 1 GB são montadas
# em pedaços: cada pedaço dá barras parciais, que guardam o instante e o identificador do primeiro e
# do último negócio para que a junção saiba qual preço vem antes.

SESSAO_REGULAR = 1
SESSAO_AFTER = 6
COLUNAS_DAS_BARRAS_B3 = [*COLUNAS_DAS_BARRAS, "volume_after", "negocios_after"]
_CHAVE_DA_BARRA = ["simbolo", "minuto"]
_ORDEM_DO_PRIMEIRO = ["_instante_primeiro", "_id_primeiro"]
_ORDEM_DO_ULTIMO = ["_instante_ultimo", "_id_ultimo"]
FUSO_DA_B3 = "America/Sao_Paulo"


def remover_cancelados(
    negocios: pd.DataFrame, cancelados: set[tuple[str, int]] | None = None
) -> pd.DataFrame:
    """Tira as linhas de cancelamento e os negócios que elas cancelam (mesmo símbolo e identificador).

    `cancelados` soma pares (símbolo, identificador) vistos fora de `negocios` (outro pedaço do
    arquivo).
    """
    linhas_de_cancelamento = negocios["cancelado"].astype(bool)
    pares = set(
        zip(
            negocios.loc[linhas_de_cancelamento, "simbolo"],
            negocios.loc[linhas_de_cancelamento, "identificador"],
            strict=True,
        )
    ) | (cancelados or set())
    if not pares:
        return negocios[~linhas_de_cancelamento]
    chave = pd.MultiIndex.from_arrays([negocios["simbolo"], negocios["identificador"]])
    return negocios[~linhas_de_cancelamento & ~chave.isin(list(pares))]


def barras_parciais_b3(negocios: pd.DataFrame) -> pd.DataFrame:
    """Barras de um pedaço de negócios já sem os cancelados, com a ordem do primeiro e do último
    negócio (colunas que começam com `_`) para `juntar_barras_b3`."""
    ordenados = negocios.sort_values(["instante", "identificador"], kind="stable")
    ordenados = ordenados.assign(
        minuto=ordenados["instante"]
        .dt.tz_convert(FUSO_DA_B3)
        .dt.floor("min")
        .dt.tz_localize(None),
        _instante=ordenados["instante"].dt.tz_convert("UTC").dt.tz_localize(None),
    )
    regular = ordenados[ordenados["sessao"] == SESSAO_REGULAR]
    after = ordenados[ordenados["sessao"] == SESSAO_AFTER]
    precos = regular.groupby(_CHAVE_DA_BARRA, sort=False).agg(
        abertura=("preco", "first"),
        maxima=("preco", "max"),
        minima=("preco", "min"),
        fechamento=("preco", "last"),
        volume=("quantidade", "sum"),
        negocios=("preco", "size"),
        _instante_primeiro=("_instante", "first"),
        _id_primeiro=("identificador", "first"),
        _instante_ultimo=("_instante", "last"),
        _id_ultimo=("identificador", "last"),
    )
    depois = after.groupby(_CHAVE_DA_BARRA, sort=False).agg(
        volume_after=("quantidade", "sum"), negocios_after=("preco", "size")
    )
    return precos.join(depois, how="outer").reset_index()


def juntar_barras_b3(partes: list[pd.DataFrame]) -> pd.DataFrame:
    """Junta barras parciais (de pedaços diferentes do mesmo dia) nas barras finais."""
    todas = pd.concat([p for p in partes if not p.empty], ignore_index=True)
    if todas.empty:
        return pd.DataFrame(columns=COLUNAS_DAS_BARRAS_B3)
    grupos = todas.groupby(_CHAVE_DA_BARRA, sort=True)
    somas = grupos[["volume", "negocios", "volume_after", "negocios_after"]].sum()
    extremos = grupos.agg(maxima=("maxima", "max"), minima=("minima", "min"))
    com_preco = todas.dropna(subset=["abertura"])
    abertura = (
        com_preco.sort_values(_ORDEM_DO_PRIMEIRO, kind="stable")
        .groupby(_CHAVE_DA_BARRA)["abertura"]
        .first()
    )
    fechamento = (
        com_preco.sort_values(_ORDEM_DO_ULTIMO, kind="stable")
        .groupby(_CHAVE_DA_BARRA)["fechamento"]
        .last()
    )
    barras = somas.join([extremos, abertura, fechamento]).reset_index()
    inteiros = ["volume", "negocios", "volume_after", "negocios_after"]
    barras[inteiros] = barras[inteiros].astype("int64")
    return barras[COLUNAS_DAS_BARRAS_B3]


def montar_barras_b3(negocios: pd.DataFrame) -> pd.DataFrame:
    """Barras de 1 minuto da B3 de uma tabela de negócios inteira (colunas instante com fuso,
    simbolo, preco, quantidade, sessao, identificador e cancelado)."""
    return juntar_barras_b3([barras_parciais_b3(remover_cancelados(negocios))])


# --- selo da IEX (plano dos intradiários grátis, PR 5) -------------------------------------------
# A IEX é uma bolsa entre várias: as barras dela não têm todos os negócios do dia, então o selo não
# diz "completo", diz se o dia é coerente com o oficial. A máxima e a mínima não servem (o lote
# fracionário entra nas barras e não mexe na máxima e na mínima oficiais: 20% a 25% das ações "fora"
# em 13/10/2026). O fechamento serve, com um limite explícito: o último negócio da IEX sai segundos
# antes do leilão de fechamento da bolsa principal. Medido em 13/10, 09/10 e 04/09/2026 (503 ações):
# mediana 0,02%, 99% abaixo de 0,12%, pior caso 0,23%. O limite é o dobro do pior caso.
LIMITE_DO_FECHAMENTO_DA_IEX = 0.005
SELO_CONFERE = "confere"
SELO_NAO_CONFERE = "nao_confere"
SELO_AUSENTE_NA_IEX = "ausente"
SELO_SEM_OFICIAL = "sem_boletim"


def selo_dos_fechamentos(
    barras: pd.DataFrame,
    fechamentos_oficiais: pd.Series,
    limite: float = LIMITE_DO_FECHAMENTO_DA_IEX,
) -> pd.DataFrame:
    """Uma linha por símbolo (das barras ou do oficial): diferença do fechamento, cobertura dos
    minutos do pregão e o selo (`confere`, `nao_confere`, `ausente` na IEX ou `sem_boletim`).

    O fechamento oficial não fica na tabela (vem do Yahoo, que não entra na base).
    """
    diferenca = conferir_fechamentos(barras, fechamentos_oficiais)["diferenca"]
    cobertura = cobertura_por_simbolo(barras)
    simbolos = sorted(set(cobertura.index) | set(fechamentos_oficiais.dropna().index))
    selo = pd.DataFrame(
        {
            "diferenca": diferenca.reindex(simbolos),
            "cobertura": cobertura.reindex(simbolos).fillna(0.0),
        },
        index=pd.Index(simbolos, name="simbolo"),
    )
    selo["selo"] = SELO_CONFERE
    selo.loc[selo["diferenca"].abs() > limite, "selo"] = SELO_NAO_CONFERE
    selo.loc[~selo.index.isin(cobertura.index), "selo"] = SELO_AUSENTE_NA_IEX
    sem_oficial = ~selo.index.isin(fechamentos_oficiais.dropna().index)
    selo.loc[sem_oficial, "selo"] = SELO_SEM_OFICIAL
    return selo.reset_index()
