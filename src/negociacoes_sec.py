"""Negociações de pessoas de dentro nos EUA, pelo Form 4 da SEC (Research R2).

Cada Form 4 é um XML (`ownershipDocument`) entregue em até 2 dias úteis depois da negociação:
quem é a empresa (`issuerCik`), o cargo de quem negociou (diretor, executivo, conselheiro, dono de
10%+), se a negociação seguiu um **plano 10b5-1** (programada com antecedência) e as transações.

Só entram as transações com código **P** (compra em bolsa ou negociada) e **S** (venda). As outras
(A: ações recebidas como pagamento; M: exercício de opção; F: ações retidas para imposto; G:
doação...) não são decisões de compra ou venda. O nome da pessoa existe no XML, mas **não é lido**
(decisão 0018): fica só o cargo.

A lista de Form 4 de cada empresa vem do mesmo `submissions` dos eventos (`formularios_4`).
"""

import json
import xml.etree.ElementTree as ET
from datetime import date

import pandas as pd

from src.negociacoes import COLUNAS, COMPRA, FONTE_FORM4, VENDA, tabela_vazia

CODIGOS = {"P": COMPRA, "S": VENDA}
VERDADEIRO = {"1", "true"}
PLANO_10B5_1 = "10b5-1"


def formularios_4(conteudo_json: bytes, desde: date) -> list[tuple[str, date, str]]:
    """Os Form 4 da lista de documentos de uma empresa: (protocolo, entregue em, documento).

    O documento (`primaryDocument`) é a versão formatada para ler (`xslF345X06/form4.xml`); o XML
    puro é o mesmo arquivo sem a pasta do estilo (`xml_puro`).
    """
    recentes = json.loads(conteudo_json).get("filings", {}).get("recent", {})
    achados = []
    for i, formulario in enumerate(recentes.get("form", [])):
        if formulario != "4":
            continue
        entregue = pd.to_datetime(recentes["filingDate"][i], errors="coerce")
        if pd.isna(entregue) or entregue.date() < desde:
            continue
        achados.append(
            (
                recentes["accessionNumber"][i],
                entregue.date(),
                recentes["primaryDocument"][i],
            )
        )
    return achados


def xml_puro(documento: str) -> str:
    """`xslF345X06/form4.xml` → `form4.xml` (o XML sem a formatação para leitura)."""
    return documento.rsplit("/", 1)[-1]


def _texto(no: ET.Element | None, caminho: str) -> str:
    achado = no.find(caminho) if no is not None else None
    return (achado.text or "").strip() if achado is not None else ""


def _verdadeiro(no: ET.Element | None, caminho: str) -> bool:
    return _texto(no, caminho).lower() in VERDADEIRO


def _cargo(dono: ET.Element | None) -> tuple[str, str]:
    """(cargo, descrição) do primeiro dono do formulário; executivo vem antes de conselheiro."""
    relacao = dono.find("reportingOwnerRelationship") if dono is not None else None
    if _verdadeiro(relacao, "isOfficer"):
        return "diretoria", _texto(relacao, "officerTitle")[:120]
    if _verdadeiro(relacao, "isDirector"):
        return "conselho", ""
    if _verdadeiro(relacao, "isTenPercentOwner"):
        return "dez_por_cento", ""
    return "outros", _texto(relacao, "otherText")[:120]


def _plano(raiz: ET.Element) -> bool | None:
    """Plano 10b5-1: o campo novo (desde 2023) ou, nos antigos, uma nota de rodapé que o cite."""
    marcado = _texto(raiz, "aff10b5One").lower()
    if marcado:
        return marcado in VERDADEIRO
    notas = " ".join((n.text or "") for n in raiz.iter("footnote"))
    return True if PLANO_10B5_1 in notas else None


def _numero(no: ET.Element, caminho: str) -> float | None:
    valor = pd.to_numeric(_texto(no, caminho), errors="coerce")
    return float(valor) if pd.notna(valor) and valor > 0 else None


def ler_form4(
    conteudo_xml: bytes, cik: int, protocolo: str, entregue_em: date, link: str
) -> pd.DataFrame:
    """As compras (P) e vendas (S) de um Form 4, no formato comum; vazio se não houver nenhuma
    ou se o formulário for sobre outra empresa (quem é dono de 10% de outra entrega Form 4 dela)."""
    raiz = ET.fromstring(conteudo_xml)
    emissor = raiz.find("issuer")
    if pd.to_numeric(_texto(emissor, "issuerCik"), errors="coerce") != cik:
        return tabela_vazia()
    cargo, descricao = _cargo(raiz.find("reportingOwner"))
    plano = _plano(raiz)
    referencia = pd.to_datetime(_texto(raiz, "periodOfReport"), errors="coerce")
    linhas = []
    for transacao in raiz.iter("nonDerivativeTransaction"):
        operacao = CODIGOS.get(_texto(transacao, "transactionCoding/transactionCode"))
        quantidade = _numero(transacao, "transactionAmounts/transactionShares/value")
        if operacao is None or quantidade is None:
            continue
        preco = _numero(transacao, "transactionAmounts/transactionPricePerShare/value")
        dia = pd.to_datetime(
            _texto(transacao, "transactionDate/value"), errors="coerce"
        )
        linhas.append(
            {
                "fonte": FONTE_FORM4,
                "documento": protocolo,
                "versao": 1,
                "cnpj": f"CIK{cik:010d}",
                "empresa": _texto(emissor, "issuerName")[:200],
                "cargo": cargo,
                "cargo_descricao": descricao,
                "operacao": operacao,
                "ativo": _texto(transacao, "securityTitle/value")[:80],
                "data": dia.date() if pd.notna(dia) else None,
                "referencia": referencia.date()
                if pd.notna(referencia)
                else entregue_em,
                "entregue_em": entregue_em,
                "quantidade": quantidade,
                "preco": preco,
                "valor": quantidade * preco if preco is not None else None,
                "moeda": "USD",
                "plano_10b5_1": plano,
                "link": link,
            }
        )
    return pd.DataFrame(linhas, columns=COLUNAS) if linhas else tabela_vazia()
