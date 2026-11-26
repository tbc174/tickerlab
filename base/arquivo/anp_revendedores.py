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
gravados**: o endereço do estabelecimento a Receita já tem pelo CNPJ. A resposta incompleta, repetida ou que muda
de total no meio da leitura é erro, sem nova tentativa na rodada: um retrato pela metade faria os postos que
faltaram "saírem" da tabela. Cada linha guardada leva o dia da coleta (`COLUNA_DO_DIA`).

O cadastro é do grupo mensal; a API **não tem agendamento** (a 1ª coleta é da Diretoria e a licença é a
confirmar): `python -m scripts.arquivar_fontes anp-revendedores-api`.

O GLP (`/v1/glp`) é outro cadastro e fica de fora.
"""

import csv
import json
import time
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from base.arquivo.coleta import (
    Alvo,
    Cliente,
    FalhaSemNovaTentativa,
    Fonte,
    Obter,
)
from base.arquivo.obter import csv_so_com_colunas, tem_cnpj_inteiro

FONTE_DO_CADASTRO = "anp-revendedores"
FONTE_DOS_PRODUTOS = "anp-revendedores-api"
MENSAL = "mensal"
SO_PELO_ID = "carga-unica"  # nenhum cron roda: a coleta é `arquivar_fontes <id>`
# o dia vai em cada linha do arquivo guardado: o acervo conta uma vez cada conteúdo diferente
# (`coletas.versoes_guardadas`), e a volta ao estado de antes (A, B, A) repetiria o SHA do 1º retrato
COLUNA_DO_DIA = "coletado_em"

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
        raise FalhaSemNovaTentativa(
            f"{endereco}: resposta fora do formato da API"
        ) from erro
    raise FalhaSemNovaTentativa(f"{endereco}: a API recusou o pedido")


def _todos_os_postos(cliente: Cliente) -> list[dict[str, Any]]:
    """Todas as páginas, ou erro: o total e o número de páginas têm de ser os mesmos do começo ao fim."""
    postos, total, paginas = _pagina(cliente, 1)
    if not total or not 0 < paginas <= MAXIMO_DE_PAGINAS:
        raise FalhaSemNovaTentativa(
            f"{ENDERECO_DA_API}: nenhum posto, ou páginas demais ({paginas})"
        )
    for numero in range(2, paginas + 1):
        esperar(PAUSA_ENTRE_PAGINAS_EM_SEGUNDOS)
        da_pagina, total_agora, paginas_agora = _pagina(cliente, numero)
        if (total_agora, paginas_agora) != (total, paginas):
            raise FalhaSemNovaTentativa(
                f"{ENDERECO_DA_API}: a lista mudou no meio da leitura (de {total} postos em {paginas} "
                f"páginas para {total_agora} em {paginas_agora}, na página {numero})"
            )
        postos = postos + da_pagina
    diferentes = len({posto.get("cnpj") for posto in postos})
    if diferentes != total:
        raise FalhaSemNovaTentativa(
            f"{ENDERECO_DA_API}: vieram {diferentes} de {total} postos"
        )
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


def _com_o_dia(obter: Obter, agora: datetime) -> Obter:
    """`obter`, e depois o dia da coleta em cada linha do CSV gravado (`COLUNA_DO_DIA`)."""
    dia = agora.date().isoformat()

    def com_o_dia(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        cabecalhos = obter(cliente, destino)
        with destino.open(encoding="utf-8", newline="") as entrada:
            cabecalho, *linhas = list(csv.reader(entrada, delimiter=";"))
        with destino.open("w", encoding="utf-8", newline="") as saida:
            escritor = csv.writer(saida, delimiter=";")
            escritor.writerow([*cabecalho, COLUNA_DO_DIA])
            escritor.writerows([*linha, dia] for linha in linhas)
        return cabecalhos

    return com_o_dia


# --- as fontes -------------------------------------------------------------------------------------------
def descobrir_cadastro(cliente: Cliente, agora: datetime) -> list[Alvo]:
    obter = csv_so_com_colunas(
        CSV_DO_CADASTRO,
        COLUNAS_DO_CADASTRO,
        CODIFICACAO_DO_CADASTRO,
        so_com_cnpj_em="CNPJ",
    )
    return [Alvo(CSV_DO_CADASTRO, ".csv", _com_o_dia(obter, agora))]


def descobrir_produtos(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Um endereço só: a coleta é que percorre as páginas."""
    return [Alvo(ENDERECO_DA_API, ".csv", _com_o_dia(obter_produtos, agora))]


def fontes() -> list[Fonte]:
    """As duas fontes, para a lista `FONTES` (o id decide a família da licença)."""
    return [
        Fonte(FONTE_DO_CADASTRO, MENSAL, descobrir_cadastro),
        Fonte(FONTE_DOS_PRODUTOS, SO_PELO_ID, descobrir_produtos),
    ]
