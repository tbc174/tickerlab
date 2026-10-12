"""Demonstrações das empresas dos EUA a partir do XBRL da SEC (`companyfacts`), no formato da CVM.

A SEC publica, por empresa, todos os números marcados em XBRL nos relatórios (`companyfacts`):
cada **fato** tem o conceito (`Revenues`, `NetIncomeLoss`...), o valor, o período (início e fim,
ou só a data para saldos), o formulário (10-K anual, 10-Q trimestral) e o protocolo do documento.

Aqui os fatos viram as mesmas **contas-chave** e **períodos** que `src/demonstracoes.py` tira da
CVM, para o cálculo (`src/fundamentos.py`) e a página Fundamentos servirem aos dois mercados. Na
tabela, "DFP" é o relatório anual (10-K) e "ITR" o trimestral (10-Q).

Cuidados:
- O nome do conceito muda com o tempo (a Apple usou `Revenues` até 2018 e depois
  `RevenueFromContractWithCustomerExcludingAssessedTax`): cada conta tem uma lista de conceitos,
  e em cada documento vale o primeiro que existir.
- **Ano fiscal** nem sempre é o do calendário (Apple termina em setembro; Walmart, em janeiro):
  os períodos saem das datas de cada fato, não do ano.
- A quantidade de ações vem da capa do relatório (`dei:EntityCommonStockSharesOutstanding`),
  conferida depois com o lucro por ação declarado, como na CVM.
- Só fatos sem "dimensão" entram no `companyfacts` (são os totais da empresa).
"""

import json
from datetime import date, timedelta

import pandas as pd

from src.demonstracoes import (
    ACUMULADO,
    ACUMULADO_ANTERIOR,
    COLUNAS,
    EXERCICIO,
    POSICAO,
)

URL_DOS_FATOS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
URL_DO_INDICE = (
    "https://www.sec.gov/Archives/edgar/data/{cik}/{pasta}/{protocolo}-index.htm"
)
ANUAL, TRIMESTRAL = "10-K", "10-Q"
DOCUMENTO = {ANUAL: "DFP", TRIMESTRAL: "ITR"}  # o nome que o cálculo conhece
ANO_MINIMO, ANO_MAXIMO = 330, 380  # dias de um exercício (52 ou 53 semanas)
ACUMULADO_MAXIMO = 290  # dias: o acumulado de um 10-Q vai até 9 meses
FOLGA = 10  # dias: o mesmo período do ano anterior pode terminar alguns dias antes ou depois
ANOS_DE_10K = 6
ANOS_DE_10Q = 2
# conta-chave → conceitos do us-gaap, em ordem de preferência
CONCEITOS = {
    "receita": (
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "RevenuesNetOfInterestExpense",
        "SalesRevenueNet",
    ),
    "resultado_bruto": ("GrossProfit",),
    "ebit": ("OperatingIncomeLoss",),
    "lucro_liquido": ("ProfitLoss", "NetIncomeLoss"),
    "lucro_controladores": ("NetIncomeLoss",),
    "lpa_basico": ("EarningsPerShareBasic", "EarningsPerShareBasicAndDiluted"),
    "fco": ("NetCashProvidedByUsedInOperatingActivities",),
    "ativo_total": ("Assets",),
    "caixa": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
    "aplicacoes": ("ShortTermInvestments", "MarketableSecuritiesCurrent"),
    "divida_lp": ("LongTermDebtNoncurrent",),
    "minoritarios": ("MinorityInterest",),
    "acoes_total": ("CommonStockSharesOutstanding",),
}
# dívida de curto prazo: o total, ou a soma das partes quando o total não vem
DIVIDA_CP_TOTAL = "DebtCurrent"
DIVIDA_CP_PARTES = ("LongTermDebtCurrent", "ShortTermBorrowings", "CommercialPaper")
PATRIMONIO_TOTAL = (
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
)
PATRIMONIO_DOS_ACIONISTAS = "StockholdersEquity"
ACOES_DA_CAPA = "EntityCommonStockSharesOutstanding"
UNIDADES = ("USD", "USD/shares", "shares")
CONCEITOS_USADOS = {
    *(c for conceitos in CONCEITOS.values() for c in conceitos),
    DIVIDA_CP_TOTAL, *DIVIDA_CP_PARTES, PATRIMONIO_TOTAL, PATRIMONIO_DOS_ACIONISTAS,
    ACOES_DA_CAPA,
}  # fmt: skip


def _fatos(dados: dict) -> pd.DataFrame:
    """Os fatos dos conceitos usados (em USD, USD por ação ou ações), dos 10-K e 10-Q."""
    linhas = []
    for taxonomia in ("us-gaap", "dei"):
        for conceito, conteudo in dados.get("facts", {}).get(taxonomia, {}).items():
            if conceito not in CONCEITOS_USADOS:
                continue
            for unidade, fatos in conteudo.get("units", {}).items():
                if unidade not in UNIDADES:
                    continue
                linhas.extend(
                    (taxonomia, conceito, f.get("start"), f["end"], f["val"], f["accn"],
                     f["form"], f.get("filed"))
                    for f in fatos
                    if f.get("form") in DOCUMENTO
                )  # fmt: skip
    tabela = pd.DataFrame(
        linhas,
        columns=[
            "taxonomia",
            "conceito",
            "inicio",
            "fim",
            "valor",
            "protocolo",
            "formulario",
            "entregue",
        ],
    )
    for coluna in ("inicio", "fim", "entregue"):
        tabela[coluna] = pd.to_datetime(tabela[coluna], errors="coerce").dt.date
    return tabela.dropna(subset=["fim"])


def _documentos(fatos: pd.DataFrame, desde_10k: date, desde_10q: date) -> pd.DataFrame:
    """Um documento por protocolo: a data-base é o fim mais recente dos fatos do us-gaap dele
    (os da capa, `dei`, têm datas posteriores e ficam de fora)."""
    contabeis = fatos[fatos["taxonomia"] == "us-gaap"]
    docs = contabeis.groupby("protocolo").agg(
        formulario=("formulario", "first"),
        referencia=("fim", "max"),
        entregue=("entregue", "min"),
    )
    docs = docs.reset_index()
    limite = docs["formulario"].map({ANUAL: desde_10k, TRIMESTRAL: desde_10q})
    docs = docs[docs["referencia"] >= limite]
    # o mesmo período entregue mais de uma vez: fica o último, com a versão = quantas entregas
    docs = docs.sort_values("entregue")
    docs["versao"] = docs.groupby(["formulario", "referencia"]).cumcount() + 1
    docs = docs.drop_duplicates(["formulario", "referencia"], keep="last")
    return docs.reset_index(drop=True)


def _dias(inicio: date | None, fim: date) -> int | None:
    return None if inicio is None or pd.isna(inicio) else (fim - inicio).days


def _periodo(fato: pd.Series, formulario: str, referencia: date) -> str | None:
    """Que tipo de valor é este fato dentro do documento (ou None se não serve)."""
    dias = _dias(fato["inicio"], fato["fim"])
    if dias is None:
        return POSICAO if fato["fim"] == referencia else None
    if formulario == ANUAL:
        return (
            EXERCICIO
            if fato["fim"] == referencia and ANO_MINIMO <= dias <= ANO_MAXIMO
            else None
        )
    if dias > ACUMULADO_MAXIMO:
        return None
    if fato["fim"] == referencia:
        return ACUMULADO
    um_ano_antes = referencia - timedelta(days=365)
    return (
        ACUMULADO_ANTERIOR if abs((fato["fim"] - um_ano_antes).days) <= FOLGA else None
    )


def _valores_do_documento(
    fatos: pd.DataFrame, formulario: str, referencia: date
) -> pd.DataFrame:
    """Os fatos do documento com o período de cada um; no acumulado, só o mais longo (o do ano
    até a data, não o do trimestre isolado)."""
    periodos = fatos.apply(lambda f: _periodo(f, formulario, referencia), axis=1)
    validos = fatos.assign(periodo=periodos).dropna(subset=["periodo"])
    validos = validos.assign(
        duracao=[
            _dias(i, f) or 0
            for i, f in zip(validos["inicio"], validos["fim"], strict=True)
        ]
    )
    validos = validos.sort_values("duracao", ascending=False)
    return validos.drop_duplicates(["conceito", "periodo"], keep="first")


def _valor(tabela: pd.DataFrame, conceito: str) -> tuple | None:
    """(início, fim, valor) de um conceito na tabela de um período, ou None."""
    if conceito not in tabela.index:
        return None
    linha = tabela.loc[conceito]
    return linha["inicio"], linha["fim"], float(linha["valor"])


def _primeiro(tabela: pd.DataFrame, conceitos: tuple[str, ...]) -> tuple | None:
    return next((v for c in conceitos if (v := _valor(tabela, c)) is not None), None)


def _saldos_compostos(tabela: pd.DataFrame) -> list[tuple]:
    """Dívida de curto prazo e patrimônio, que podem vir em pedaços."""
    contas = []
    total = _valor(tabela, DIVIDA_CP_TOTAL)
    partes = [v for c in DIVIDA_CP_PARTES if (v := _valor(tabela, c)) is not None]
    if total or partes:
        soma = total[2] if total else sum(p[2] for p in partes)
        contas.append(("divida_cp", POSICAO, None, (total or partes[0])[1], soma))
    patrimonio = _valor(tabela, PATRIMONIO_TOTAL)
    dos_acionistas = _valor(tabela, PATRIMONIO_DOS_ACIONISTAS)
    if patrimonio is None and dos_acionistas is not None:
        minoritarios = _valor(tabela, "MinorityInterest")
        extra = minoritarios[2] if minoritarios else 0.0
        patrimonio = (None, dos_acionistas[1], dos_acionistas[2] + extra)
    if patrimonio:
        contas.append(
            ("patrimonio_liquido", POSICAO, None, patrimonio[1], patrimonio[2])
        )
    return contas


def _contas(valores: pd.DataFrame) -> list[tuple]:
    """(conta, período, início, fim, valor) a partir dos conceitos, com as regras de preferência."""
    contas = []
    for periodo, grupo in valores.groupby("periodo"):
        tabela = grupo.set_index("conceito")
        for conta, conceitos in CONCEITOS.items():
            achado = _primeiro(tabela, conceitos)
            if achado:
                contas.append((conta, periodo, *achado))
        if periodo == POSICAO:
            contas += _saldos_compostos(tabela)
    return contas


def _acoes_da_capa(fatos: pd.DataFrame, referencia: date) -> tuple | None:
    """Ações na capa do relatório (data posterior ao balanço; várias classes sem dimensão somam)."""
    capa = fatos[fatos["conceito"] == ACOES_DA_CAPA]
    if capa.empty:
        return None
    ultima = capa[capa["fim"] == capa["fim"].max()]
    return ("acoes_total", POSICAO, None, referencia, float(ultima["valor"].sum()))


def ler_companyfacts(
    conteudo_json: bytes, hoje: date, cnpj: str | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(contas, documentos) de uma empresa, no formato de `src.demonstracoes.ler_demonstracoes`.

    Guarda os 10-K dos últimos `ANOS_DE_10K` anos e os 10-Q dos últimos `ANOS_DE_10Q`.
    """
    dados = json.loads(conteudo_json)
    cik = int(dados["cik"])
    cnpj = cnpj or f"CIK{cik:010d}"
    fatos = _fatos(dados)
    colunas_docs = [
        "cnpj",
        "empresa",
        "documento",
        "referencia",
        "versao",
        "recebido_em",
        "link",
    ]
    if fatos.empty:
        return pd.DataFrame(columns=COLUNAS), pd.DataFrame(columns=colunas_docs)
    documentos = _documentos(
        fatos,
        date(hoje.year - ANOS_DE_10K, 1, 1),
        date(hoje.year - ANOS_DE_10Q, 1, 1),
    )
    linhas, docs = [], []
    for doc in documentos.itertuples(index=False):
        do_documento = fatos[fatos["protocolo"] == doc.protocolo]
        valores = _valores_do_documento(do_documento, doc.formulario, doc.referencia)
        contas_do_documento = _contas(valores)
        capa = _acoes_da_capa(do_documento, doc.referencia)
        if capa:  # a capa vence o saldo do balanço (é a contagem mais recente)
            contas_do_documento = [
                c for c in contas_do_documento if c[0] != "acoes_total"
            ]
            contas_do_documento.append(capa)
        for conta, periodo, inicio, fim, valor in contas_do_documento:
            linhas.append((cnpj, DOCUMENTO[doc.formulario], doc.referencia, doc.versao, periodo,
                           inicio, fim, conta, valor))  # fmt: skip
        docs.append(
            (cnpj, str(dados.get("entityName", "")).strip(), DOCUMENTO[doc.formulario],
             doc.referencia, doc.versao, doc.entregue,
             URL_DO_INDICE.format(cik=cik, pasta=doc.protocolo.replace("-", ""), protocolo=doc.protocolo))
        )  # fmt: skip
    contas = pd.DataFrame(linhas, columns=COLUNAS)
    contas = contas.drop_duplicates(
        ["cnpj", "documento", "referencia", "periodo", "fim", "conta"]
    )
    return contas, pd.DataFrame(docs, columns=colunas_docs)


def ultimo_relatorio(conteudo_json: bytes) -> tuple[date | None, str]:
    """(data-base do 10-K ou 10-Q mais recente, setor) a partir da lista de documentos
    (`submissions`) da empresa. Serve para só baixar o `companyfacts` quando há relatório novo."""
    dados = json.loads(conteudo_json)
    recentes = dados.get("filings", {}).get("recent", {})
    datas = [
        recentes["reportDate"][i]
        for i, formulario in enumerate(recentes.get("form", []))
        if formulario in DOCUMENTO and recentes["reportDate"][i]
    ]
    ultima = pd.to_datetime(max(datas), errors="coerce") if datas else pd.NaT
    setor = str(dados.get("sicDescription") or "").strip()
    return (None if pd.isna(ultima) else ultima.date()), setor
