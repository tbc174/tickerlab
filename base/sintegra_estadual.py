"""Leitores restritos dos layouts Sintegra PR, RS e MG; nenhum acesso à rede.

Só documentos de 14 dígitos com DV, sem CPF preenchido com zeros. CNPJ não
prova natureza jurídica: toda a tabela permanece interna até classificar EI/MEI.
RS e MG têm leitor para prova offline, mas a coleta está bloqueada.
"""

import csv
import io
import re
import zipfile
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import TextIO

import pandas as pd

from base.cnpj import cpf_confere, dv_confere

TABELA = "sintegra_estadual"
UFS = ("PR", "RS", "MG")
URLS_PR = {
    "ativos": "http://processos.fazenda.pr.gov.br/arquivos/ativos",
    "cancelados": "http://processos.fazenda.pr.gov.br/arquivos/cancelados",
}
BLOQUEIOS = {
    "RS": "robots.txt do RS: Disallow: /*.asp cobre o download (27/11/2026)",
    "MG": "link do Cadastro Resumido de MG respondeu HTTP 404 (27/11/2026)",
}
FONTES = {
    "PR": "SEFA-PR / Sintegra",
    "RS": "SEFAZ-RS / CGCTE",
    "MG": "SEF-MG / Sintegra",
}
COLUNAS = (
    "ie",
    "cnpj",
    "uf",
    "arquivo",
    "situacao",
    "categoria",
    "cnae",
    "codigo_municipio",
    "habilitado_desde_mes",
    "data_abertura",
    "uf_estabelecimento",
)
COLUNAS_SIMPLES = (
    "cnpj_basico",
    "optante_simples",
    "optante_mei",
    "data_opcao_simples",
    "data_exclusao_simples",
    "data_opcao_mei",
    "data_exclusao_mei",
)
CHAVE = ("uf", "arquivo", "ie", "cnpj")
MAX_TEXTO = 256 * 1024 * 1024
MAX_LINHA = 32 * 1024
CATEGORIAS_RS = frozenset({"GERAL", "EPP", "MICRO", "S NAC"})
ESTADOS = frozenset(
    [
        "AC",
        "AL",
        "AP",
        "AM",
        "BA",
        "CE",
        "DF",
        "ES",
        "GO",
        "MA",
        "MT",
        "MS",
        "MG",
        "PA",
        "PB",
        "PR",
        "PE",
        "PI",
        "RJ",
        "RN",
        "RS",
        "RO",
        "RR",
        "SC",
        "SP",
        "SE",
        "TO",
    ]
)


def urls_para_coleta(uf: str) -> dict[str, str]:
    """Só PR está operacional; a trava antecede qualquer rede ou gravação."""
    if uf in BLOQUEIOS:
        raise ValueError(f"Sintegra {uf}: {BLOQUEIOS[uf]}")
    if uf != "PR":
        raise ValueError("Sintegra: UF não suportada")
    return dict(URLS_PR)


def _cnpj_valido(documento: str) -> bool:
    return bool(
        re.fullmatch(r"[0-9]{14}", documento)
        and dv_confere(documento)
        and not (documento.startswith("000") and cpf_confere(documento[3:]))
    )


def _numero(valor: str, tamanho: str) -> str:
    if not re.fullmatch(r"[0-9]{" + tamanho + "}", valor):
        raise ValueError("Sintegra: campo numérico fora do layout")
    return valor


def _pr(campos: list[str]) -> dict[str, object]:
    mes = _numero(campos[2], "6")
    try:
        date(int(mes[:4]), int(mes[4:]), 1)
    except ValueError:
        raise ValueError("Sintegra PR: mês inválido") from None
    return {
        "ie": _numero(campos[0], "10"),
        "habilitado_desde_mes": mes,
        "situacao": _numero(campos[3], "8"),
        "codigo_municipio": _numero(campos[4], "5"),
        "cnae": _numero(campos[5], "7"),
    }


def _rs(campos: list[str]) -> dict[str, object]:
    if campos[2] not in CATEGORIAS_RS or campos[5] not in ESTADOS:
        raise ValueError("Sintegra RS: categoria ou UF fora do layout")
    try:
        if not re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}", campos[3]):
            raise ValueError
        dia, mes, ano = (int(p) for p in campos[3].split("/"))
        abertura = date(ano, mes, dia)
    except ValueError:
        raise ValueError("Sintegra RS: data inválida") from None
    return {
        "ie": _numero(campos[0], "10"),
        "situacao": "ativo",
        "categoria": campos[2],
        "data_abertura": abertura,
        "cnae": _numero(campos[4], "7"),
        "uf_estabelecimento": campos[5],
    }


def _mg(campos: list[str]) -> dict[str, object]:
    # A posição 2 (nome) nunca entra na tabela ou nos erros.
    if campos[3] not in {"H", "N"} or len(campos[0]) not in {9, 13}:
        raise ValueError("Sintegra MG: situação fora do layout")
    return {
        "ie": _numero(campos[0], "9,13"),
        "situacao": campos[3],
        "cnae": _numero(campos[4], "7"),
    }


def _linhas(entrada: TextIO, uf: str, arquivo: str) -> Iterator[dict[str, object]]:
    esperadas = {"PR": 6, "RS": 7, "MG": 5}[uf]
    leitor = {"PR": _pr, "RS": _rs, "MG": _mg}[uf]
    for linha in entrada:
        if not linha.strip():
            continue
        if len(linha) > MAX_LINHA:
            raise ValueError("Sintegra: linha acima do limite")
        # RS: o levantamento descreve campos separados, sem fixar o caractere.
        # Aceitar somente um destes separadores e a contagem exata do layout.
        separadores = (";", "\t", "|") if uf == "RS" else (";",)
        separador = next((s for s in separadores if s in linha), None)
        if separador is None:
            raise ValueError("Sintegra: layout inesperado")
        campos = next(csv.reader([linha], delimiter=separador, strict=True))
        if len(campos) != esperadas:
            raise ValueError("Sintegra: quantidade de campos inesperada")
        campos = [c.strip() for c in campos]
        if not _cnpj_valido(campos[1]):
            continue
        yield {"cnpj": campos[1], "uf": uf, "arquivo": arquivo, **leitor(campos)}


def _tabela(entrada: TextIO, uf: str, arquivo: str) -> pd.DataFrame:
    try:
        tabela = pd.DataFrame(_linhas(entrada, uf, arquivo), columns=COLUNAS)
    except (ValueError, csv.Error, UnicodeError):
        raise ValueError(
            "Sintegra: conteúdo fora do layout; arquivo recusado"
        ) from None
    if tabela.empty or tabela.duplicated(list(CHAVE)).any():
        raise ValueError("Sintegra: arquivo vazio ou chave duplicada")
    for coluna in set(COLUNAS) - {"data_abertura"}:
        tabela[coluna] = tabela[coluna].astype("string")
    tabela["data_abertura"] = pd.to_datetime(tabela.data_abertura).dt.date
    return tabela.sort_values(list(CHAVE)).reset_index(drop=True)


def ler_arquivo(caminho: Path, uf: str, arquivo: str) -> pd.DataFrame:
    """Interpreta TXT de PR/MG (também compactado no PR) e ICS_Ativo.zip do RS."""
    if uf not in UFS or arquivo not in (
        {"ativos", "cancelados"} if uf == "PR" else {"ativos"}
    ):
        raise ValueError("Sintegra: UF ou arquivo não suportado")
    if caminho.stat().st_size > MAX_TEXTO:
        raise ValueError("Sintegra: arquivo acima do limite")
    if uf != "RS" and not zipfile.is_zipfile(caminho):
        with caminho.open(encoding="latin-1", newline="") as entrada:
            return _tabela(entrada, uf, arquivo)
    with zipfile.ZipFile(caminho) as pacote:
        membros = [
            m
            for m in pacote.infolist()
            if not m.is_dir()
            and (
                m.filename.rsplit("/", 1)[-1].casefold() == "ics_ativo.txt"
                if uf == "RS"
                else m.filename.casefold().endswith(".txt")
            )
        ]
        if len(membros) != 1 or membros[0].file_size > MAX_TEXTO:
            raise ValueError(
                "Sintegra: TXT ausente, duplicado ou acima do limite no ZIP"
            )
        with (
            pacote.open(membros[0]) as bruto,
            io.TextIOWrapper(bruto, encoding="latin-1", newline="") as entrada,
        ):
            return _tabela(entrada, uf, arquivo)
