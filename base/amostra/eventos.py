"""Bloco "eventos e governança" da amostra integrada: o que a companhia comunicou, os sinais de risco e
como era a administração, tudo como se sabia em cada fim de mês.

- **Documentos nos 90 dias antes** (IPE da CVM, `eventos`): quantos por tema (resultados, proventos,
  eventos, risco) e quantos fatos relevantes, contados pela data de entrega.
- **Insolvência já conhecida** (`insolvencia`): recuperação judicial, extrajudicial, falência ou
  liquidação já comunicada à CVM; o rótulo mais recente e desde quando.
- **Auditor** (`auditores`, `trocas_de_auditor`): a firma do FCA mais novo já entregue e os meses desde
  a última troca conhecida.
- **Negociações da administração e do controlador nos 90 dias antes** (VLMO, desde 12/2018,
  `negociacoes`): compras e vendas em R$, pela data do negócio, só as já entregues à CVM.
- **Conselho e remuneração** (FRE): membros e independentes do conselho de administração, conselho
  fiscal, e a remuneração total da diretoria no exercício mais novo do FRE mais novo já entregue.
- **Ofertas públicas anunciadas nos 12 meses antes** (`ofertas`), pela data do anúncio.

Os proventos e os eventos de capital do FRE ficam de fora: as tabelas não trazem o dia em que ficaram
públicos, e a amostra não adivinha datas.
"""

import pandas as pd

from base.amostra.como_era import DATA, Entrada, na_janela, ultimo_publico

ENTRADAS = {
    "eventos": Entrada(publico_em="publicado_em"),
    "insolvencia": Entrada(publico_em="conhecido_em"),
    "auditores": Entrada(publico_em="conhecido_em"),
    "trocas_de_auditor": Entrada(publico_em="conhecido_em"),
    "negociacoes": Entrada(publico_em="entregue_em"),
    "fre_conselho": Entrada(publico_em="conhecido_em"),
    "fre_remuneracao": Entrada(publico_em="conhecido_em"),
    "ofertas": Entrada(publico_em="anunciada_em"),
}
TEMAS = ("resultados", "proventos", "eventos", "risco")
FATO_RELEVANTE = "Fato relevante"
JANELA_CURTA, JANELA_LONGA = 90, 365
CONSELHO = "Conselho de Administração"  # "Pertence apenas ao..." e "Pertence à Diretoria e ao..."
CONSELHO_FISCAL = "Conselho Fiscal"
DIRETORIA = "Diretoria Estatutária"
CONTROLADOR = "controlador"
COLUNAS = (
    "cnpj", "data",
    *(f"documentos_{t}_90d" for t in TEMAS), "fatos_relevantes_90d",
    "insolvencia_conhecida", "insolvencia_rotulo", "insolvencia_desde",
    "auditor_id", "auditor_publico_em", "meses_desde_a_troca_de_auditor",
    "compras_controlador_90d", "vendas_controlador_90d",
    "compras_administracao_90d", "vendas_administracao_90d",
    "conselho_membros", "conselho_independentes", "conselho_fiscal_membros", "fre_publico_em",
    "remuneracao_diretoria", "remuneracao_exercicio",
    "ofertas_12m",
)  # fmt: skip


def _contagens(janela: pd.DataFrame, por: str, valores: dict[str, str]) -> pd.DataFrame:
    """Linhas (cnpj, data) com a contagem de cada valor de `por` (coluna -> nome da saída)."""
    contadas = janela[janela[por].isin(valores)].groupby(["cnpj", "data", por]).size()
    largas = contadas.unstack(por, fill_value=0).rename(columns=valores)
    return largas.reindex(columns=list(valores.values()), fill_value=0).reset_index()


def _documentos(eventos: pd.DataFrame, ultimo_mes: pd.Timestamp) -> pd.DataFrame:
    janela = na_janela(
        eventos, data_do_fato="publicado_em", publico_em="publicado_em", dias=JANELA_CURTA,
        ultimo_mes=ultimo_mes,
    )  # fmt: skip
    por_tema = _contagens(janela, "tema", {t: f"documentos_{t}_90d" for t in TEMAS})
    fatos = _contagens(janela, "rotulo", {FATO_RELEVANTE: "fatos_relevantes_90d"})
    return por_tema.merge(fatos, on=["cnpj", "data"], how="outer")


def _insolvencia(grade: pd.DataFrame, insolvencia: pd.DataFrame) -> pd.DataFrame:
    tabela = insolvencia.sort_values("conhecido_em", kind="stable")
    tabela = tabela.assign(
        desde=tabela.groupby("cnpj")["conhecido_em"].transform("min")
    )
    lido = ultimo_publico(
        grade[["cnpj", "data"]], tabela, publico_em="conhecido_em", colunas=["rotulo", "desde"],
        prefixo="insolvencia",
    )  # fmt: skip
    return lido.assign(
        insolvencia_conhecida=lido["rotulo"].notna(),
        insolvencia_desde=lido["desde"].where(lido["desde"] <= lido["data"]),
    ).rename(columns={"rotulo": "insolvencia_rotulo"})


def _auditor(
    grade: pd.DataFrame, auditores: pd.DataFrame, trocas: pd.DataFrame
) -> pd.DataFrame:
    em_curso = auditores.sort_values(["conhecido_em", "inicio"], kind="stable")
    lido = ultimo_publico(
        grade[["cnpj", "data"]], em_curso, publico_em="conhecido_em", colunas=["auditor_id"],
        prefixo="auditor",
    )  # fmt: skip
    troca = ultimo_publico(
        grade[["cnpj", "data"]], trocas.sort_values("conhecido_em", kind="stable"),
        publico_em="conhecido_em", colunas=["efetiva_em"], prefixo="troca",
    )  # fmt: skip
    meses = (troca["data"] - pd.to_datetime(troca["efetiva_em"])).dt.days / 30.4375
    return lido.merge(
        troca[["cnpj", "data"]].assign(meses_desde_a_troca_de_auditor=meses.round(1)),
        on=["cnpj", "data"],
    )


def _negociacoes(negociacoes: pd.DataFrame, ultimo_mes: pd.Timestamp) -> pd.DataFrame:
    """Compras e vendas em R$ nos 90 dias antes, do controlador e da administração (os outros cargos)."""
    negocios = negociacoes.rename(columns={"data": "data_do_negocio"})
    janela = na_janela(
        negocios, data_do_fato="data_do_negocio", publico_em="entregue_em", dias=JANELA_CURTA,
        ultimo_mes=ultimo_mes,
    )  # fmt: skip
    if janela.empty:
        return pd.DataFrame(columns=["cnpj", "data"])
    quem = janela["cargo"].where(janela["cargo"] == CONTROLADOR, "administracao")
    lado = janela["operacao"].map({"compra": "compras", "venda": "vendas"})
    janela = janela.assign(_coluna=lado + "_" + quem + "_90d")
    somas = (
        janela.groupby(["cnpj", "data", "_coluna"])["valor"].sum().unstack("_coluna")
    )
    return somas.reset_index()


def _governanca(
    grade: pd.DataFrame, conselho: pd.DataFrame, remuneracao: pd.DataFrame
) -> pd.DataFrame:
    orgao = conselho["orgao"].fillna("")
    no_conselho = orgao.str.contains(CONSELHO, regex=False)
    contagens = pd.DataFrame(
        {
            "cnpj": conselho["cnpj"], "id_documento": conselho["id_documento"],
            "conhecido_em": conselho["conhecido_em"],
            "conselho_membros": conselho["membros"].where(no_conselho, 0),
            "conselho_independentes": conselho["independentes"].where(no_conselho, 0),
            "conselho_fiscal_membros": conselho["membros"].where(orgao == CONSELHO_FISCAL, 0),
        }
    )  # fmt: skip
    por_documento = contagens.groupby(
        ["cnpj", "id_documento", "conhecido_em"], as_index=False
    ).sum()
    lido = ultimo_publico(
        grade[["cnpj", "data"]], por_documento.sort_values("conhecido_em", kind="stable"),
        publico_em="conhecido_em",
        colunas=["conselho_membros", "conselho_independentes", "conselho_fiscal_membros"],
        prefixo="fre",
    )  # fmt: skip
    diretoria = remuneracao[remuneracao["orgao"] == DIRETORIA]
    mais_novo = diretoria.groupby(["cnpj", "id_documento"])[
        "fim_do_exercicio"
    ].transform("max")
    diretoria = diretoria[diretoria["fim_do_exercicio"] == mais_novo]
    diretoria = (
        diretoria.groupby(["cnpj", "id_documento", "conhecido_em", "fim_do_exercicio"])[
            "total_do_orgao"
        ]
        .sum()
        .reset_index()
    )
    remunera = ultimo_publico(
        grade[["cnpj", "data"]],
        diretoria.sort_values("conhecido_em", kind="stable"),
        publico_em="conhecido_em",
        colunas=["total_do_orgao", "fim_do_exercicio"],
        prefixo="remuneracao",
    ).rename(
        columns={
            "total_do_orgao": "remuneracao_diretoria",
            "fim_do_exercicio": "remuneracao_exercicio",
        }
    )
    return lido.merge(
        remunera[["cnpj", "data", "remuneracao_diretoria", "remuneracao_exercicio"]],
        on=["cnpj", "data"],
    )


def _ofertas(ofertas: pd.DataFrame, ultimo_mes: pd.Timestamp) -> pd.DataFrame:
    janela = na_janela(
        ofertas.rename(columns={"cnpj_emissor": "cnpj"}), data_do_fato="anunciada_em",
        publico_em="anunciada_em", dias=JANELA_LONGA, ultimo_mes=ultimo_mes,
    )  # fmt: skip
    return janela.groupby(["cnpj", "data"]).size().rename("ofertas_12m").reset_index()


def montar(entradas: dict[str, pd.DataFrame], grade: pd.DataFrame) -> pd.DataFrame:
    """As colunas de eventos e governança para cada linha da grade (cnpj, data)."""
    saida = grade[["cnpj", "data"]].assign(
        data=pd.to_datetime(grade["data"]).astype(DATA)
    )
    ultimo_mes = saida["data"].max()
    contagens = [
        _documentos(entradas["eventos"], ultimo_mes),
        _negociacoes(entradas["negociacoes"], ultimo_mes),
        _ofertas(entradas["ofertas"], ultimo_mes),
    ]
    for parte in contagens:
        saida = saida.merge(parte, on=["cnpj", "data"], how="left")
    contadas = [c for c in COLUNAS if c.endswith(("_90d", "_12m"))]
    saida[contadas] = saida.reindex(columns=contadas).fillna(0)
    estados = [
        _insolvencia(saida, entradas["insolvencia"]).drop(
            columns=["insolvencia_publico_em", "desde"]
        ),
        _auditor(saida, entradas["auditores"], entradas["trocas_de_auditor"]),
        _governanca(saida, entradas["fre_conselho"], entradas["fre_remuneracao"]),
    ]
    for parte in estados:
        saida = saida.merge(parte, on=["cnpj", "data"], how="left")
    saida["insolvencia_conhecida"] = (
        saida["insolvencia_conhecida"].fillna(False).astype(bool)
    )
    return (
        saida.reindex(columns=list(COLUNAS))
        .sort_values(["cnpj", "data"])
        .reset_index(drop=True)
    )
