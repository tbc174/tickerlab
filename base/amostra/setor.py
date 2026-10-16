"""Bloco "fundos, setor e macro" da amostra integrada: quem tinha a ação, os números da operação que as
agências publicam e os juros, como se sabia em cada fim de mês.

- **Fundos** (`painel_dos_fundos`, por empresa, posição comprada): quantos fundos e quanto valor no
  mês de carteira mais novo já público, nos blocos 4 e 8 do CDA.
- **Números da operação** (`base/setoriais`), ligados à companhia pela B13: passageiros pagos (ANAC),
  litros vendidos de combustíveis líquidos (ANP), consumidores (SAMP), acessos (Anatel), beneficiários
  (ANS) e prêmios diretos (SUSEP). Para cada fonte: o mês mais novo já público, o volume dele e o
  volume do mesmo mês um ano antes.
- **Juros** (`curva_juros`, a curva própria do Tesouro): as taxas nominais de 1 e 5 anos e a real de
  5 anos do dia mais novo já público.

A ligação de cada código à companhia vale desde a entrega do FRE que a mostrou (`desde`) até ~17
meses depois do último FRE que ainda a mostrava (o próximo FRE, entregue até maio do ano seguinte,
já não a trazia). A `principal` da B13 **não** é usada: ela escolhe pelo ticker de hoje. Nos números da
operação vale o valor da **primeira publicação** de cada mês: nunca adianta nada, e as revisões
entram quando houver mais de uma coleta.
"""

import pandas as pd

from base.amostra.como_era import DATA, Entrada, ultimo_publico
from base.cnpj import formatar, normalizar_cnpj

ENTRADAS = {
    "fundos": Entrada(publico_em="disponivel_em"),
    "operacao": Entrada(publico_em="publico_em"),
    "ligacoes": Entrada(publico_em="desde"),
    "juros": Entrada(publico_em="disponivel_em"),
}
DEPOIS_DO_ULTIMO_FRE = pd.DateOffset(months=17)
ORDEM_DAS_VIAS = {"propria": 0, "controlada": 1, "coligada": 2, "sem_tipo": 3}
FONTES = {  # nome da coluna -> fonte da ligação na B13
    "passageiros_anac": "anac-estatistico",
    "vendas_anp": "anp-vendas-distribuidora",
    "consumidores_samp": "aneel-samp",
    "acessos_anatel": "anatel-acessos",
    "beneficiarios_ans": "ans-beneficiarios",
    "premios_susep": "susep-ses",
}
VERTICES = {"juros_nominal_1a": ("nominal", 1.0), "juros_nominal_5a": ("nominal", 5.0),
            "juros_real_5a": ("real", 5.0)}  # fmt: skip
NOMES_DOS_FUNDOS = {
    "fundos": "fundos_com_a_acao", "valor": "fundos_valor",
    "fundos_no_bloco_8": "fundos_no_bloco_8", "valor_no_bloco_8": "fundos_valor_no_bloco_8",
}  # fmt: skip
COLUNAS = (
    "cnpj", "data",
    "fundos_competencia", "fundos_publico_em", *NOMES_DOS_FUNDOS.values(),
    *(f"{nome}{sufixo}" for nome in FONTES for sufixo in ("", "_12m_antes", "_competencia")),
    *VERTICES, "juros_data_base",
)  # fmt: skip


def cnpj_formatado(serie: pd.Series) -> pd.Series:
    """O CNPJ como no painel (00.000.000/0000-00), a partir de qualquer forma."""
    return serie.map(
        lambda valor: formatar(c) if (c := normalizar_cnpj(valor)) else None
    )


def ligacoes_no_tempo(empresa_serie: pd.DataFrame) -> pd.DataFrame:
    """As ligações código da fonte -> companhia com o período em que valem (`desde`, `ate`)."""
    ligadas = empresa_serie.dropna(subset=["cnpj_companhia", "desde"])
    ligadas = ligadas[ligadas["via"].isin(ORDEM_DAS_VIAS)]
    ate = pd.to_datetime(ligadas["ultima_referencia"]) + DEPOIS_DO_ULTIMO_FRE
    return pd.DataFrame(
        {
            "fonte": ligadas["fonte"], "chave": ligadas["chave"].astype(str),
            "cnpj": cnpj_formatado(ligadas["cnpj_companhia"]),
            "desde": pd.to_datetime(ligadas["desde"]).astype(DATA), "ate": ate.astype(DATA),
            "ordem": ligadas["via"].map(ORDEM_DAS_VIAS),
            "participacao": pd.to_numeric(ligadas["participacao"], errors="coerce"),
        }
    ).dropna(subset=["cnpj"])  # fmt: skip


def _dono_na_data(ligacoes: pd.DataFrame, meses: pd.Series) -> pd.DataFrame:
    """Para cada (fonte, código) e fim de mês: a companhia dona naquele dia (a própria antes da
    controlada, depois a maior participação e a ligação mais nova)."""
    pares = ligacoes.merge(pd.DataFrame({"data": meses.drop_duplicates()}), how="cross")
    valem = (pares["desde"] <= pares["data"]) & (
        pares["ate"].isna() | (pares["data"] <= pares["ate"])
    )
    validas = pares[valem].sort_values(
        ["ordem", "participacao", "desde"],
        ascending=[True, False, False],
        na_position="last",
    )
    return validas.drop_duplicates(["fonte", "chave", "data"])[
        ["fonte", "chave", "data", "cnpj"]
    ]


def _operacao(
    grade: pd.DataFrame, operacao: pd.DataFrame, ligacoes: pd.DataFrame
) -> pd.DataFrame:
    """Para cada companhia, fonte e data: o mês mais novo já público, o volume dele (somado nos
    códigos da companhia naquele dia) e o do mesmo mês um ano antes."""
    serie = operacao.assign(
        publico_em=pd.to_datetime(operacao["publico_em"]).astype(DATA),
        competencia=pd.to_datetime(operacao["competencia"]).astype(DATA),
    ).sort_values("publico_em", kind="stable")
    meses = pd.to_datetime(grade["data"]).astype(DATA)
    donos = _dono_na_data(ligacoes, meses)
    if donos.empty or serie.empty:
        return grade[["cnpj", "data"]].copy()
    donos = donos.assign(_chave=donos["fonte"] + "|" + donos["chave"]).sort_values(
        "data"
    )
    serie = serie.assign(_chave=serie["fonte"] + "|" + serie["chave"].astype(str))
    recente = pd.merge_asof(
        donos, serie[["_chave", "publico_em", "competencia"]], left_on="data", right_on="publico_em",
        by="_chave", direction="backward",
    ).dropna(subset=["competencia"])  # fmt: skip
    # o mês mais novo já público de cada companhia e fonte; os códigos atrasados não somam
    recente["_mais_novo"] = recente.groupby(["cnpj", "fonte", "data"])[
        "competencia"
    ].transform("max")
    recente = recente[recente["competencia"] == recente["_mais_novo"]]
    publicados = serie[["_chave", "competencia", "publico_em", "valor"]]
    agora = recente.merge(publicados, on=["_chave", "competencia"], suffixes=("", "_v"))
    agora = agora[agora["publico_em_v"] <= agora["data"]]
    antes = recente.assign(
        competencia=recente["competencia"]
        - pd.DateOffset(years=1)
        + pd.offsets.MonthEnd(0)
    )
    antes = antes.merge(publicados, on=["_chave", "competencia"], suffixes=("", "_v"))
    antes = antes[antes["publico_em_v"] <= antes["data"]]
    soma_agora = agora.groupby(["cnpj", "data", "fonte"]).agg(
        volume=("valor", "sum"), competencia=("competencia", "max")
    )
    soma_antes = (
        antes.groupby(["cnpj", "data", "fonte"])["valor"]
        .sum()
        .rename("volume_12m_antes")
    )
    juntas = soma_agora.join(soma_antes).reset_index()
    nomes = {fonte: nome for nome, fonte in FONTES.items()}
    juntas["fonte"] = juntas["fonte"].map(nomes)
    largas = juntas.pivot_table(
        index=["cnpj", "data"], columns="fonte", values=["volume", "volume_12m_antes", "competencia"],
        aggfunc="first",
    )  # fmt: skip
    sufixos = {
        "volume": "",
        "volume_12m_antes": "_12m_antes",
        "competencia": "_competencia",
    }
    largas.columns = [f"{fonte}{sufixos[medida]}" for medida, fonte in largas.columns]
    return largas.reset_index()


def _fundos(grade: pd.DataFrame, fundos: pd.DataFrame) -> pd.DataFrame:
    comprado = fundos[fundos["tipo"] == "comprado"]
    lido = ultimo_publico(
        grade[["cnpj", "data"]], comprado.sort_values(["disponivel_em", "competencia"], kind="stable"),
        publico_em="disponivel_em", colunas=["competencia", *NOMES_DOS_FUNDOS], prefixo="fundos",
    )  # fmt: skip
    return lido.rename(
        columns={"competencia": "fundos_competencia", **NOMES_DOS_FUNDOS}
    )


def _juros(grade: pd.DataFrame, juros: pd.DataFrame) -> pd.DataFrame:
    """As taxas do dia mais novo já público (as mesmas para todas as companhias da data)."""
    partes = []
    for nome, (curva, prazo) in VERTICES.items():
        vertice = juros[(juros["curva"] == curva) & (juros["prazo_anos"] == prazo)]
        partes.append(
            vertice[["data_base", "disponivel_em", "taxa"]]
            .rename(columns={"taxa": nome})
            .set_index(["data_base", "disponivel_em"])
        )
    taxas = pd.concat(partes, axis=1).reset_index().assign(_todas="todas")
    meses = grade[["data"]].drop_duplicates().assign(_todas="todas")
    lido = ultimo_publico(
        meses, taxas.sort_values("disponivel_em", kind="stable"), publico_em="disponivel_em",
        colunas=[*VERTICES, "data_base"], prefixo="juros", por="_todas",
    )  # fmt: skip
    return lido.rename(columns={"data_base": "juros_data_base"}).drop(
        columns=["_todas", "juros_publico_em"]
    )


def montar(entradas: dict[str, pd.DataFrame], grade: pd.DataFrame) -> pd.DataFrame:
    """As colunas de fundos, setor e macro para cada linha da grade (cnpj, data)."""
    saida = grade[["cnpj", "data"]].assign(
        data=pd.to_datetime(grade["data"]).astype(DATA)
    )
    for parte in (
        _fundos(saida, entradas["fundos"]),
        _operacao(saida, entradas["operacao"], entradas["ligacoes"]),
    ):
        saida = saida.merge(parte, on=["cnpj", "data"], how="left")
    saida = saida.merge(_juros(saida, entradas["juros"]), on="data", how="left")
    saida = saida.reindex(columns=list(COLUNAS))
    datas = [
        c for c in COLUNAS if c.endswith(("_competencia", "_publico_em", "_data_base"))
    ]
    for coluna in datas:  # uma coluna toda vazia também é de datas
        saida[coluna] = pd.to_datetime(saida[coluna]).astype(DATA)
    return saida.sort_values(["cnpj", "data"]).reset_index(drop=True)
