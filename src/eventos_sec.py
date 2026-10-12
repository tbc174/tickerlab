"""Eventos das empresas dos EUA a partir da SEC (EDGAR), no mesmo formato dos da CVM.

- `company_tickers.json`: liga o ticker (AAPL) ao **CIK**, o número da empresa na SEC. Na tabela
  de tickers, o CIK ocupa o lugar do CNPJ, com prefixo: `CIK0000320193`.
- `submissions/CIK##########.json`: os documentos entregues por cada empresa (~1.000 mais
  recentes), com data de entrega, data de referência, tipo de formulário, os **itens** do 8-K
  (o assunto: 2.02 = resultados, 5.02 = diretoria...) e o documento principal, de onde sai o
  **link para o original** na SEC.

A regra de acesso da SEC exige que cada consulta se identifique com nome e e-mail de contato
(`User-Agent`) e no máximo 10 consultas por segundo: quem baixa é `scripts/atualizar_eventos_sec.py`.
Este módulo só lê e classifica (funções puras). A classificação é editorial e só ordena a leitura.
"""

import json
from dataclasses import dataclass
from datetime import date

import pandas as pd

URL_DOS_TICKERS = "https://www.sec.gov/files/company_tickers.json"
URL_DOS_DOCUMENTOS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
URL_DO_ARQUIVO = "https://www.sec.gov/Archives/edgar/data/{cik}/{pasta}/{documento}"
FONTE_SEC = "sec_edgar"
PREFIXO_DO_CIK = "CIK"


@dataclass(frozen=True)
class ClasseSec:
    tema: str
    materialidade: int
    rotulo: str


# itens do 8-K (Form 8-K, General Instructions B) que viram evento, do mais ao menos material
ITENS_DO_8K = {
    "1.03": ClasseSec("eventos", 100, "Falência ou recuperação judicial"),
    "4.02": ClasseSec("risco", 90, "Balanço anterior não confiável"),
    "2.01": ClasseSec("eventos", 90, "Aquisição ou venda de ativos"),
    "1.01": ClasseSec("eventos", 80, "Contrato relevante"),
    "3.01": ClasseSec("risco", 70, "Aviso de deslistagem"),
    "2.06": ClasseSec("risco", 70, "Baixa contábil (impairment)"),
    "2.02": ClasseSec("resultados", 70, "Resultados"),
    "5.02": ClasseSec("eventos", 50, "Mudança na diretoria ou no conselho"),
    "8.01": ClasseSec("eventos", 40, "Outros eventos"),
    "5.07": ClasseSec("eventos", 30, "Assembleia de acionistas"),
    "7.01": ClasseSec("eventos", 30, "Divulgação ao mercado"),
}
FORMULARIOS = {
    "10-K": ClasseSec("resultados", 70, "Relatório anual (10-K)"),
    "20-F": ClasseSec("resultados", 70, "Relatório anual (20-F)"),
    "40-F": ClasseSec("resultados", 70, "Relatório anual (40-F)"),
    "10-Q": ClasseSec("resultados", 60, "Relatório trimestral (10-Q)"),
    "6-K": ClasseSec("eventos", 40, "Comunicado (6-K)"),
}
REAPRESENTACAO = "/A"  # "8-K/A": reapresentação de um documento já entregue
COLUNAS = [
    "protocolo", "versao", "cnpj", "empresa", "categoria", "tipo", "assunto", "rotulo", "tema",
    "materialidade", "referencia", "publicado_em", "link",
]  # fmt: skip


def cik_como_chave(cik: int) -> str:
    """O CIK no lugar do CNPJ: `CIK0000320193`."""
    return f"{PREFIXO_DO_CIK}{int(cik):010d}"


def ler_tickers(
    conteudo_json: bytes, tickers_pedidos: set[str] | None = None
) -> pd.DataFrame:
    """Ticker → CIK e nome, no formato da tabela de tickers (só os pedidos, se houver lista).

    Colunas: ticker, codigo, cnpj (o CIK com prefixo), empresa, valor_mobiliario.
    """
    linhas = []
    for item in json.loads(conteudo_json).values():
        ticker = (
            str(item["ticker"]).upper().replace(".", "-")
        )  # BRK.B vira BRK-B, como no Yahoo
        if tickers_pedidos is not None and ticker not in tickers_pedidos:
            continue
        linhas.append(
            {
                "ticker": ticker,
                "codigo": ticker,
                "cnpj": cik_como_chave(item["cik_str"]),
                "empresa": str(item["title"]).strip(),
                "valor_mobiliario": "Ação (EUA)",
            }
        )
    tabela = pd.DataFrame(
        linhas, columns=["ticker", "codigo", "cnpj", "empresa", "valor_mobiliario"]
    )
    return tabela.drop_duplicates("ticker").reset_index(drop=True)


def classificar(formulario: str, itens: str) -> ClasseSec | None:
    """Tema, materialidade e rótulo de um documento da SEC (None: não vira evento)."""
    base = formulario.removesuffix(REAPRESENTACAO)
    if base == "8-K":
        achados = [ITENS_DO_8K[i] for i in itens.split(",") if i.strip() in ITENS_DO_8K]
        if not achados:
            return None  # só anexos (9.01) ou itens raros
        return max(achados, key=lambda c: c.materialidade)
    return FORMULARIOS.get(base)


def _data(texto: str) -> date | None:
    return pd.to_datetime(texto, errors="coerce").date() if texto else None


def ler_documentos(conteudo_json: bytes, desde: date) -> pd.DataFrame:
    """Os eventos de uma empresa (submissions da SEC) entregues desde `desde`, mais novo primeiro."""
    dados = json.loads(conteudo_json)
    cik = int(dados["cik"])
    empresa = str(dados.get("name", "")).strip()
    recentes = dados.get("filings", {}).get("recent", {})
    linhas = []
    for i, formulario in enumerate(recentes.get("form", [])):
        publicado = _data(recentes["filingDate"][i])
        if publicado is None or publicado < desde:
            continue
        itens = recentes.get("items", [""] * (i + 1))[i] or ""
        classe = classificar(formulario, itens)
        documento = recentes["primaryDocument"][i]
        if classe is None or not documento:
            continue
        reapresentado = formulario.endswith(REAPRESENTACAO)
        protocolo = recentes["accessionNumber"][i]
        descricoes = [
            ITENS_DO_8K[x].rotulo for x in itens.split(",") if x in ITENS_DO_8K
        ]
        linhas.append(
            {
                "protocolo": protocolo,
                "versao": 2
                if reapresentado
                else 1,  # reapresentação conta como versão nova
                "cnpj": cik_como_chave(cik),
                "empresa": empresa,
                "categoria": formulario,
                "tipo": itens,
                "assunto": (
                    ("Reapresentação: " if reapresentado else "")
                    + ("; ".join(descricoes) if descricoes else classe.rotulo)
                ),
                "rotulo": classe.rotulo
                + (" (reapresentação)" if reapresentado else ""),
                "tema": classe.tema,
                "materialidade": classe.materialidade,
                "referencia": _data(recentes.get("reportDate", [""] * (i + 1))[i]),
                "publicado_em": publicado,
                "link": URL_DO_ARQUIVO.format(
                    cik=cik, pasta=protocolo.replace("-", ""), documento=documento
                ),
            }
        )
    tabela = pd.DataFrame(linhas, columns=COLUNAS)
    return tabela.sort_values("publicado_em", ascending=False).reset_index(drop=True)
