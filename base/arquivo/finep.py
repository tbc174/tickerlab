"""Coleta da planilha de contratações da Finep (linha 469 da fila): só as duas abas de crédito
reembolsável, só as colunas da lista e só as linhas de CNPJ inteiro.

A Finep publica um `.xlsx` só (`Contratacao.xlsx`), reescrito a cada posição, com onze abas: guia,
legenda, não reembolsável, subvenção, startups, ANCINE e as três de crédito. Ficam o crédito direto
(a Finep empresta à empresa) e o descentralizado (um agente financeiro empresta com recurso da Finep).
A aba de condições do crédito fica de fora por enquanto: 2.309 números de contrato dela vêm estragados
pelo Excel (gravados como data), e a junção com os projetos pede conferência própria.

Lista de colunas que ficam, e não de colunas que saem (como `obter.csv_so_com_colunas`): o nome do
proponente, do executor e do beneficiário (o de empresário individual é o da pessoa), o título e o
resumo do projeto nunca chegam ao acervo. A planilha vira um CSV ";" em UTF-8, com a aba e a posição
("Posição: 23/10/2026", na linha 6 de cada aba) em cada linha; data em AAAA-MM-DD e número como o Excel
guardou ("4000000.04"), sem arredondar.

Layout conferido em 04/11/2026 (posição de 23/10/2026): cabeçalho na linha 7, dados da 8 em diante.
"""

import csv
import re
from collections.abc import Iterator, Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

import openpyxl

from base.arquivo.coleta import Alvo, Cliente, Obter
from base.arquivo.obter import tem_cnpj_inteiro

CONTRATACAO_DA_FINEP = "https://download.finep.gov.br/Contratacao.xlsx"
ABA_DO_CREDITO_DIRETO = "Projetos_Crédito_Direto"
ABA_DO_DESCENTRALIZADO = "Projetos_Créd__Descentralizado"
LINHA_DA_POSICAO = 6
LINHA_DO_CABECALHO = 7
POSICAO = re.compile(r"Posi[cç][aã]o:\s*(\d{2})/(\d{2})/(\d{4})")

# os cabeçalhos das duas abas como os testes os montam (a planilha de verdade tem outros no meio)
CABECALHO_DO_CREDITO_DIRETO = (
    "Demanda", "Ref", "Contrato", "Data Entrada SF", "Data Assinatura", "Título", "Proponente",
    "CNPJ Proponente", "Município Proponente", "UF Proponente", "Executor", "CNPJ Executor",
    "UF Projeto", "Valor Finep", "Contrapartida Financeira", "Valor Pago", "Status",
    "Resumo Publicável",
)  # fmt: skip
CABECALHO_DO_DESCENTRALIZADO = (
    "Data Assinatura", "Contrato Finep Agente", "Beneficiario", "CNPJ Beneficiário",
    "UF Beneficiário", "Valor Financiado", "Valor Liberado", "Contrapartida", "Outros Recursos",
    "Agente",
)  # fmt: skip
GUARDADAS_DO_CREDITO_DIRETO = (
    "Ref", "Contrato", "Data Assinatura", "CNPJ Proponente", "UF Proponente", "CNPJ Executor",
    "UF Projeto", "Valor Finep", "Contrapartida Financeira", "Valor Pago", "Status",
)  # fmt: skip
GUARDADAS_DO_DESCENTRALIZADO = (
    "Data Assinatura", "Contrato Finep Agente", "CNPJ Beneficiário", "UF Beneficiário",
    "Valor Financiado", "Valor Liberado", "Contrapartida", "Outros Recursos", "Agente",
)  # fmt: skip
# aba da planilha → (nome curto, coluna do CNPJ de quem tomou, colunas que ficam)
ABAS = {
    ABA_DO_CREDITO_DIRETO: (
        "credito_direto",
        "CNPJ Proponente",
        GUARDADAS_DO_CREDITO_DIRETO,
    ),
    ABA_DO_DESCENTRALIZADO: (
        "credito_descentralizado",
        "CNPJ Beneficiário",
        GUARDADAS_DO_DESCENTRALIZADO,
    ),
}
COLUNAS_GUARDADAS = tuple(
    dict.fromkeys([*GUARDADAS_DO_CREDITO_DIRETO, *GUARDADAS_DO_DESCENTRALIZADO])
)
COLUNAS_DO_CSV = ("aba", "posicao", *COLUNAS_GUARDADAS)


class _Aba(Protocol):
    """O pedaço da aba do openpyxl (sem tipos publicados) que a leitura usa."""

    def iter_rows(
        self, min_row: int, max_row: int | None = None, *, values_only: bool
    ) -> Iterator[tuple[object, ...]]: ...


def _texto(valor: object) -> str:
    """A célula como texto: data em AAAA-MM-DD, número como o Excel guardou, vazio como ""."""
    if valor is None:
        return ""
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor).strip()


def _uma_linha(aba: _Aba, numero: int) -> tuple[object, ...]:
    return next(aba.iter_rows(min_row=numero, max_row=numero, values_only=True), ())


def _posicao(aba: _Aba) -> str:
    """A data da posição ("Posição: 23/10/2026") em AAAA-MM-DD, ou "" se a aba não disser."""
    for valor in _uma_linha(aba, LINHA_DA_POSICAO):
        achado = POSICAO.search(str(valor or ""))
        if achado:
            dia, mes, ano = achado.groups()
            return f"{ano}-{mes}-{dia}"
    return ""


def _linhas_da_aba(livro: openpyxl.Workbook, nome: str) -> Iterator[dict[str, str]]:
    """As linhas de CNPJ inteiro de uma aba de crédito, só com as colunas que ficam."""
    if nome not in livro.sheetnames:
        raise ValueError(f"Finep: a planilha não tem a aba {nome} (mudou o layout?)")
    curto, documento, guardadas = ABAS[nome]
    aba: _Aba = livro[nome]
    posicao = _posicao(aba)
    cabecalho = [_texto(v) for v in _uma_linha(aba, LINHA_DO_CABECALHO)]
    if faltam := [c for c in guardadas if c not in cabecalho]:
        raise ValueError(f"Finep, aba {nome}: faltam as colunas {', '.join(faltam)}")
    indice = {c: cabecalho.index(c) for c in guardadas}
    for valores in aba.iter_rows(min_row=LINHA_DO_CABECALHO + 1, values_only=True):
        linha = {
            c: _texto(valores[i]) if i < len(valores) else "" for c, i in indice.items()
        }
        if tem_cnpj_inteiro(linha[documento]):
            yield {"aba": curto, "posicao": posicao, **linha}


def _gravar_csv(planilha: Path, destino: Path) -> None:
    # aberto como arquivo: o openpyxl recusa um caminho que não termine em .xlsx (o nosso é .bruto)
    with planilha.open("rb") as entrada:
        livro = openpyxl.load_workbook(entrada, read_only=True, data_only=True)
        try:
            with destino.open("w", encoding="utf-8", newline="") as saida:
                escritor = csv.DictWriter(
                    saida, COLUNAS_DO_CSV, delimiter=";", restval=""
                )
                escritor.writeheader()
                for nome in ABAS:
                    escritor.writerows(_linhas_da_aba(livro, nome))
        finally:
            livro.close()


def planilha_so_credito(url: str) -> Obter:
    """Baixa a planilha e grava em `destino` o CSV só com o crédito (ver o começo do módulo)."""

    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        bruto = destino.with_name(destino.name + ".bruto")
        try:
            cabecalhos = cliente.baixar(url, bruto)
            _gravar_csv(bruto, destino)
        except BaseException:
            destino.unlink(missing_ok=True)  # nunca fica CSV pela metade
            raise
        finally:
            bruto.unlink(missing_ok=True)
        return cabecalhos

    return obter


def descobrir_contratacao(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """O endereço é fixo: a Finep reescreve a mesma planilha a cada posição."""
    return [
        Alvo(CONTRATACAO_DA_FINEP, ".csv", planilha_so_credito(CONTRATACAO_DA_FINEP))
    ]
