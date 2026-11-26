"""Revendedores varejistas de combustíveis automotivos da ANP no arquivista (linha 1123).

Fonte: a API de Revendedores da própria ANP (`revendedoresapi.anp.gov.br`, anunciada no portal dela; sem chave,
5.000 postos por página). O CSV do mesmo cadastro nos dados abertos não traz a tancagem nem os bicos, que só a
API dá. Conferido em 26/11/2026: 45.848 postos em 10 páginas de uns 5,7 MB, um CNPJ por posto.

Chega ao acervo só um CSV (";", UTF-8) com `COLUNAS`, uma linha por posto e produto, e só de CNPJ inteiro. A
razão social (que no empresário individual traz o nome e o CPF do titular), o endereço, as coordenadas e a
observação livre **nunca são gravados**: o endereço do estabelecimento a Receita já tem pelo CNPJ. A página que
vem incompleta ou repetida é erro: um retrato pela metade faria os postos que faltaram "saírem" da tabela.

O GLP (`/v1/glp`) é outro cadastro e fica de fora.
"""

import csv
import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from base.arquivo.coleta import Alvo, Cliente, Fonte, Obter
from base.arquivo.obter import tem_cnpj_inteiro

ENDERECO = "https://revendedoresapi.anp.gov.br/v1/combustivel"
FONTE = "anp-revendedores"
MENSAL = "mensal"
MAXIMO_DE_PAGINAS = 100  # hoje são 10; mais que isso é a API respondendo outra coisa
# o nome do campo da API → a coluna do acervo; o que não está aqui não é gravado
DO_POSTO = {
    "cnpj": "cnpj",
    "codigoSIMP": "codigo_simp",
    "autorizacao": "autorizacao",
    "dataPublicacao": "data_da_autorizacao",
    "uf": "uf",
    "municipio": "municipio",
    "distribuidora": "bandeira",
    "dataVinculacao": "data_da_vinculacao",
}
DO_PRODUTO = {
    "produto": "produto",
    "tancagem": "tancagem",
    "unidMedidaTancagem": "unidade_da_tancagem",
    "qtdeBicos": "bicos",
}
COLUNAS = (*DO_POSTO.values(), *DO_PRODUTO.values())


def endereco_da_pagina(numero: int) -> str:
    return f"{ENDERECO}?numeropagina={numero}"


def _pagina(cliente: Cliente, numero: int) -> tuple[list[dict[str, Any]], int, int]:
    """Os postos de uma página, o total de postos e o total de páginas que a API declara."""
    endereco = endereco_da_pagina(numero)
    resposta = json.loads(cliente.ler(endereco).conteudo)
    try:
        if not resposta["succeeded"]:
            raise ValueError(f"{endereco}: a API recusou o pedido")
        filtro = resposta["searchPageFilter"]
        return resposta["data"], filtro["totalRegistro"], filtro["totalPagina"]
    except (KeyError, TypeError) as erro:
        raise ValueError(f"{endereco}: resposta fora do formato da API") from erro


def _todos_os_postos(cliente: Cliente) -> list[dict[str, Any]]:
    postos, total, paginas = _pagina(cliente, 1)
    if not total or not 0 < paginas <= MAXIMO_DE_PAGINAS:
        raise ValueError(f"{ENDERECO}: nenhum posto, ou páginas demais ({paginas})")
    for numero in range(2, paginas + 1):
        postos = postos + _pagina(cliente, numero)[0]
    diferentes = len({posto.get("cnpj") for posto in postos})
    if diferentes < total:
        raise ValueError(f"{ENDERECO}: vieram {diferentes} de {total} postos")
    return postos


def _texto(valor: object) -> str:
    return "" if valor is None else str(valor).strip()


def linhas_do_posto(posto: Mapping[str, Any]) -> list[dict[str, str]]:
    """Uma linha por produto; o posto sem produto vira uma linha com o produto vazio."""
    do_posto = {nosso: _texto(posto.get(campo)) for campo, nosso in DO_POSTO.items()}
    return [
        do_posto
        | {nosso: _texto(produto.get(campo)) for campo, nosso in DO_PRODUTO.items()}
        for produto in posto.get("produtos") or [{}]
    ]


def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
    """Lê todas as páginas e grava em `destino` o CSV só com `COLUNAS`, na mesma ordem a cada vez."""
    linhas = [
        linha
        for posto in _todos_os_postos(cliente)
        if tem_cnpj_inteiro(posto.get("cnpj"))
        for linha in linhas_do_posto(posto)
    ]
    linhas.sort(key=lambda linha: (linha["cnpj"], linha["produto"]))
    with destino.open("w", encoding="utf-8", newline="") as saida:
        escritor = csv.DictWriter(saida, COLUNAS, delimiter=";")
        escritor.writeheader()
        escritor.writerows(linhas)
    return {}


def descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Um endereço só: a coleta é que percorre as páginas."""
    para_gravar: Obter = obter
    return [Alvo(ENDERECO, ".csv", para_gravar)]


def fontes() -> list[Fonte]:
    """A fonte, para a lista `FONTES` (o id é a família da licença)."""
    return [Fonte(FONTE, MENSAL, descobrir, pesada=False)]
