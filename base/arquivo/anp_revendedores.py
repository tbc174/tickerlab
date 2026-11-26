"""Revendedores varejistas de combustíveis automotivos da ANP no arquivista (linha 1123). Duas fontes, as duas da
própria ANP:

- `anp-revendedores`: o CSV do cadastro nos dados abertos (CC BY na ficha do conjunto no dados.gov.br, lida em
  26/11/2026): CNPJ, município, bandeira e datas. Não traz tancagem nem bicos;
- `anp-revendedores-api`: a API de Revendedores (`revendedoresapi.anp.gov.br`, anunciada no portal da ANP), de
  onde saem produto, tancagem, bicos e interdição. Licença a confirmar. Sem chave em 26/11/2026: 45.848 postos em
  10 páginas de uns 5,7 MB, um CNPJ por posto. **Um pedido por vez, com pausa**; se a API passar a pedir chave,
  cadastro, aceite de termos ou teste de robô, a coleta falha e quem decide é o Tiago: não contornar.

Chega ao acervo só um CSV (";", UTF-8) com as colunas das listas, e só de CNPJ inteiro. A razão social (que no
empresário individual traz o nome e o CPF do titular), o endereço, as coordenadas e a observação livre **nunca são
gravados**: o endereço do estabelecimento a Receita já tem pelo CNPJ. A resposta incompleta ou repetida é erro: um
retrato pela metade faria os postos que faltaram "saírem" da tabela.

O GLP (`/v1/glp`) é outro cadastro e fica de fora.
"""

import csv
import json
import time
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from base.arquivo.coleta import Alvo, Cliente, Fonte
from base.arquivo.obter import csv_so_com_colunas, tem_cnpj_inteiro

FONTE_DO_CADASTRO = "anp-revendedores"
FONTE_DOS_PRODUTOS = "anp-revendedores-api"
MENSAL = "mensal"

# --- o cadastro: CSV dos dados abertos -------------------------------------------------------------------
CSV_DO_CADASTRO = (
    "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/"
    "arquivos-dados-cadastrais-dos-revendedores-varejistas-de-combustiveis-automotivos/"
    "dados-cadastrais-revendedores-varejistas-combustiveis-automoveis.csv"
)
CODIFICACAO_DO_CADASTRO = "utf-8-sig"
# as colunas da fonte que ficam, com o nome dela
COLUNAS_DO_CADASTRO = (
    "DATAPUBLICACAO",
    "CNPJ",
    "UF",
    "MUNICIPIO",
    "BANDEIRA",
    "DATAVINCULACAO",
)

# --- o detalhe por produto: API ---------------------------------------------------------------------------
ENDERECO_DA_API = "https://revendedoresapi.anp.gov.br/v1/combustivel"
PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS = 30
MAXIMO_DE_PAGINAS = 100  # hoje são 10; mais que isso é a API respondendo outra coisa
# o nome do campo da API → a coluna do acervo; o que não está aqui não é gravado
DO_PRODUTO = {
    "produto": "produto",
    "tancagem": "tancagem",
    "unidMedidaTancagem": "unidade_da_tancagem",
    "qtdeBicos": "bicos",
}
COLUNAS_DOS_PRODUTOS = ("cnpj", *DO_PRODUTO.values(), "interdicao")
CAMPO_DA_INTERDICAO = "statusSIGAF"

esperar = time.sleep  # os testes trocam este nome


def endereco_da_pagina(numero: int) -> str:
    return f"{ENDERECO_DA_API}?numeropagina={numero}"


def _pagina(cliente: Cliente, numero: int) -> tuple[list[dict[str, Any]], int, int]:
    """Os postos de uma página, o total de postos e o total de páginas que a API declara."""
    endereco = endereco_da_pagina(numero)
    conteudo = cliente.ler(endereco).conteudo
    try:
        resposta = json.loads(conteudo)
        aceito = resposta["succeeded"]
        if aceito:
            filtro = resposta["searchPageFilter"]
            return resposta["data"], filtro["totalRegistro"], filtro["totalPagina"]
    except (ValueError, KeyError, TypeError) as erro:
        raise ValueError(f"{endereco}: resposta fora do formato da API") from erro
    raise ValueError(f"{endereco}: a API recusou o pedido")


def _todos_os_postos(cliente: Cliente) -> list[dict[str, Any]]:
    postos, total, paginas = _pagina(cliente, 1)
    if not total or not 0 < paginas <= MAXIMO_DE_PAGINAS:
        raise ValueError(
            f"{ENDERECO_DA_API}: nenhum posto, ou páginas demais ({paginas})"
        )
    for numero in range(2, paginas + 1):
        esperar(PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS)
        postos = postos + _pagina(cliente, numero)[0]
    diferentes = len({posto.get("cnpj") for posto in postos})
    if diferentes < total:
        raise ValueError(f"{ENDERECO_DA_API}: vieram {diferentes} de {total} postos")
    return postos


def _texto(valor: object) -> str:
    return "" if valor is None else str(valor).strip()


def linhas_do_posto(posto: Mapping[str, Any]) -> list[dict[str, str]]:
    """Uma linha por produto; o posto sem produto vira uma linha com o produto vazio."""
    cnpj = _texto(posto.get("cnpj"))
    interdicao = _texto(posto.get(CAMPO_DA_INTERDICAO))
    return [
        {
            "cnpj": cnpj,
            **{
                nosso: _texto(produto.get(campo)) for campo, nosso in DO_PRODUTO.items()
            },
            "interdicao": interdicao,
        }
        for produto in posto.get("produtos") or [{}]
    ]


def obter_produtos(cliente: Cliente, destino: Path) -> Mapping[str, str]:
    """Lê todas as páginas e grava em `destino` o CSV só com `COLUNAS_DOS_PRODUTOS`, na mesma ordem a cada vez."""
    linhas = [
        linha
        for posto in _todos_os_postos(cliente)
        if tem_cnpj_inteiro(posto.get("cnpj"))
        for linha in linhas_do_posto(posto)
    ]
    linhas.sort(key=lambda linha: (linha["cnpj"], linha["produto"]))
    with destino.open("w", encoding="utf-8", newline="") as saida:
        escritor = csv.DictWriter(saida, COLUNAS_DOS_PRODUTOS, delimiter=";")
        escritor.writeheader()
        escritor.writerows(linhas)
    return {}


# --- as fontes -------------------------------------------------------------------------------------------
def descobrir_cadastro(cliente: Cliente, agora: datetime) -> list[Alvo]:
    obter = csv_so_com_colunas(
        CSV_DO_CADASTRO,
        COLUNAS_DO_CADASTRO,
        CODIFICACAO_DO_CADASTRO,
        so_com_cnpj_em="CNPJ",
    )
    return [Alvo(CSV_DO_CADASTRO, ".csv", obter)]


def descobrir_produtos(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Um endereço só: a coleta é que percorre as páginas."""
    return [Alvo(ENDERECO_DA_API, ".csv", obter_produtos)]


def fontes() -> list[Fonte]:
    """As duas fontes, para a lista `FONTES` (o id decide a família da licença)."""
    return [
        Fonte(FONTE_DO_CADASTRO, MENSAL, descobrir_cadastro),
        Fonte(FONTE_DOS_PRODUTOS, MENSAL, descobrir_produtos),
    ]
