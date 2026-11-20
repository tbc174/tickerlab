"""Fontes novas da conferência de 19/11/2026 (meta das 300 tabelas pelo CNPJ): SICAF e Banco de Preços em Saúde.

O que o arquivista passa a guardar:

- **Compras.gov.br, SICAF** (`comprasgov-sicaf-ativos` e `comprasgov-sicaf-inativos`): o cadastro dos fornecedores
  do governo federal pela API de dados abertos (`modulo-fornecedor/1_consultarFornecedor`), em páginas de 500,
  uma lista para os ativos e outra para os inativos (a API exige o filtro). O cadastro mistura pessoa física
  (campo `cpf`) e jurídica (campo `cnpj`): **chega ao acervo só o item com CNPJ inteiro**, e só os campos da
  lista `CAMPOS_DO_SICAF` (sem o `cpf` e sem a razão social, que pode ser o nome de uma pessoa). O item de pessoa
  física é descartado na leitura da página, antes de qualquer gravação. A leitura conta todos os itens, de
  pessoa física também, e confere com o total que a API diz: diferença é erro, nunca um pedaço do cadastro;
- **Ministério da Saúde, Banco de Preços em Saúde** (`bps`): as compras públicas de medicamentos e
  produtos de saúde, um ZIP por ano (o CSV de dentro tem o nome do ano), de 2020 em diante. Chega ao acervo só
  a lista `COLUNAS_DO_BPS` (sem o nome do fornecedor e do fabricante e sem a observação, texto livre) e só a
  linha com o CNPJ do fornecedor inteiro; o CNPJ do fabricante e o da instituição que não forem CNPJ inteiro
  saem em branco.

Escolhas (testes em `tests/test_base_arquivo_lote_conferidas_19_11.py`): a lista de campos é dos que ficam (o que
a fonte acrescentar depois não entra sozinho); o ano corrente só entra quando o ZIP dele existe (o S3 responde
403 ao ano que ainda não saiu).
"""

import csv
from collections.abc import Callable, Mapping
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

from base.arquivo.coleta import Alvo, Cliente, Descobrir, Fonte, Obter
from base.arquivo.obter import csv_so_com_colunas, tem_cnpj_inteiro
from base.arquivo.obter_pj import json_paginado

MENSAL = "mensal"


class ContagemDoSicafDivergente(RuntimeError):
    """A API do SICAF pagou um número de itens diferente do total que ela mesma contou."""


# --- Compras.gov.br: SICAF -------------------------------------------------------------------------------
FORNECEDORES_DO_COMPRASGOV = (
    "https://dadosabertos.compras.gov.br/modulo-fornecedor/1_consultarFornecedor"
)
POR_PAGINA_DO_SICAF = 500  # o máximo que a API aceita (de 10 a 500)
# em 19/11/2026: 1.654 páginas de ativos e 271 de inativos; a folga é para o cadastro crescer
MAXIMO_DE_PAGINAS_DO_SICAF = 3_000
PAUSA_ENTRE_PAGINAS_DO_SICAF_EM_SEGUNDOS = 0.5
CAMPO_DO_CNPJ_DO_SICAF = "cnpj"
# os campos que ficam; o `cpf` e o `nomeRazaoSocialFornecedor` ficam de fora de propósito
CAMPOS_DO_SICAF = (
    CAMPO_DO_CNPJ_DO_SICAF,
    "ativo",
    "habilitadoLicitar",
    "codigoCnae",
    "nomeCnae",
    "naturezaJuridicaId",
    "naturezaJuridicaNome",
    "porteEmpresaId",
    "porteEmpresaNome",
    "nomeMunicipio",
    "ufSigla",
)
# o id da fonte → o valor do filtro `ativo`, que a API exige
SITUACOES_DO_SICAF = {
    "comprasgov-sicaf-ativos": "true",
    "comprasgov-sicaf-inativos": "false",
}


def endereco_do_sicaf(ativo: str) -> Callable[[int], str]:
    """A página n da lista de fornecedores com o filtro `ativo`."""

    def endereco(pagina: int) -> str:
        consulta = urlencode(
            {"pagina": pagina, "tamanhoPagina": POR_PAGINA_DO_SICAF, "ativo": ativo}
        )
        return f"{FORNECEDORES_DO_COMPRASGOV}?{consulta}"

    return endereco


def item_do_sicaf(item: Mapping[str, Any]) -> dict[str, Any] | None:
    """O item só com os campos da lista, ou None se não tem CNPJ inteiro (pessoa física, CNPJ em branco)."""
    if not tem_cnpj_inteiro(item.get(CAMPO_DO_CNPJ_DO_SICAF)):
        return None
    return {campo: item[campo] for campo in CAMPOS_DO_SICAF if campo in item}


def leitor_do_sicaf() -> Callable[[object], tuple[list[dict[str, Any]], bool]]:
    """Lê a página (`resultado`, `totalRegistros`, `paginasRestantes`), devolve só os itens de pessoa jurídica
    e, na última página, confere quantos itens vieram (de pessoa física também) contra o total da API."""
    lidos = 0

    def ler(resposta: object) -> tuple[list[dict[str, Any]], bool]:
        nonlocal lidos
        corpo = resposta if isinstance(resposta, dict) else {}
        itens = corpo.get("resultado") or []
        lidos += len(itens)
        ha_mais = (corpo.get("paginasRestantes") or 0) > 0
        total = corpo.get("totalRegistros")
        if not ha_mais and lidos != total:
            raise ContagemDoSicafDivergente(
                f"SICAF: {lidos} itens lidos, a API contou {total}"
            )
        juridicas = (item_do_sicaf(item) for item in itens)
        return [item for item in juridicas if item is not None], ha_mais

    return ler


def _do_sicaf(ativo: str) -> Descobrir:
    endereco = endereco_do_sicaf(ativo)

    def descobrir(_cliente: Cliente, _agora: datetime) -> list[Alvo]:
        # um leitor por coleta: a contagem dos itens não passa de uma coleta para a outra
        obter = json_paginado(
            endereco,
            leitor_do_sicaf(),
            maximo_de_paginas=MAXIMO_DE_PAGINAS_DO_SICAF,
            pausa_s=PAUSA_ENTRE_PAGINAS_DO_SICAF_EM_SEGUNDOS,
        )
        return [Alvo(endereco(1), ".jsonl", obter)]

    return descobrir


# --- Ministério da Saúde: Banco de Preços em Saúde --------------------------------------------------------
PASTA_DO_BPS = "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/BPS/csv/"
PRIMEIRO_ANO_DO_BPS = 2020  # o S3 nega (403) os anos anteriores
COLUNA_DO_FORNECEDOR_DO_BPS = "cnpj_fornecedor"
# colunas de CNPJ secundárias: o que não for CNPJ inteiro sai em branco
OUTRAS_COLUNAS_DE_CNPJ_DO_BPS = ("cnpj_fabricante", "cnpj_instituicao")
# as colunas que ficam; `no_fornecedor`, `no_fabricante` e `ds_observacao` ficam de fora de propósito
COLUNAS_DO_BPS = (
    "co_seq_bps",
    "ano_compra",
    "dt_compra",
    "dt_insercao",
    "validade_compra",
    COLUNA_DO_FORNECEDOR_DO_BPS,
    *OUTRAS_COLUNAS_DE_CNPJ_DO_BPS,
    "no_instituicao",
    "sg_uf",
    "no_municipio",
    "ds_esfera",
    "co_catmat",
    "ds_item",
    "co_pdm",
    "no_pdm",
    "co_classe",
    "no_classe",
    "fg_generico",
    "registro_anvisa",
    "tp_compra",
    "modalidade",
    "nu_processo_compra",
    "nu_ata",
    "sg_unidade_medida",
    "un_fornecimento",
    "un_medida_capacidade",
    "vl_capacidade",
    "qt_medicamento",
    "vl_preco_unitario",
    "vl_preco_total",
)
CODIFICACAO_DO_BPS = "utf-8-sig"


def zip_do_bps(ano: int) -> str:
    """O endereço do ZIP do ano."""
    return f"{PASTA_DO_BPS}{ano}_csv.zip"


def _sem_cnpj_quebrado(obter: Obter, colunas: tuple[str, ...]) -> Obter:
    """Depois de `obter`, regrava o CSV com as `colunas` em branco onde o valor não é um CNPJ inteiro. Se a
    regravação falha, nenhum dos dois arquivos fica (o de `obter` ainda pode ter um CPF nessas colunas)."""

    def obter_limpo(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        cabecalhos = obter(cliente, destino)
        limpo = destino.with_name(destino.name + ".limpo")
        try:
            _regrava_sem_cnpj_quebrado(destino, limpo, colunas)
        except BaseException:
            destino.unlink(missing_ok=True)
            raise
        finally:
            limpo.unlink(missing_ok=True)
        return cabecalhos

    return obter_limpo


def _regrava_sem_cnpj_quebrado(
    destino: Path, limpo: Path, colunas: tuple[str, ...]
) -> None:
    codificacao = CODIFICACAO_DO_BPS.removesuffix("-sig")
    with (
        destino.open(encoding=codificacao, newline="") as entrada,
        limpo.open("w", encoding=codificacao, newline="") as saida,
    ):
        leitor = csv.DictReader(entrada, delimiter=";")
        escritor = csv.DictWriter(saida, leitor.fieldnames or [], delimiter=";")
        escritor.writeheader()
        for linha in leitor:
            for coluna in colunas:
                if coluna in linha and not tem_cnpj_inteiro(linha[coluna]):
                    linha[coluna] = ""
            escritor.writerow(linha)
    limpo.replace(destino)


def obter_do_bps(ano: int) -> Obter:
    """O CSV do ano, só com as colunas da lista e só a linha com o CNPJ do fornecedor inteiro."""
    obter = csv_so_com_colunas(
        zip_do_bps(ano),
        COLUNAS_DO_BPS,
        CODIFICACAO_DO_BPS,
        so_com_cnpj_em=COLUNA_DO_FORNECEDOR_DO_BPS,
        dentro_do_zip=True,
        membro=f"{ano}.csv",
    )
    return _sem_cnpj_quebrado(obter, OUTRAS_COLUNAS_DE_CNPJ_DO_BPS)


# o S3 responde 403 (e não 404) ao arquivo que não existe
NAO_EXISTE_NO_S3 = (HTTPStatus.FORBIDDEN, HTTPStatus.NOT_FOUND)


def _existe(cliente: Cliente, url: str) -> bool:
    try:
        cliente.cabecalhos(url)
    except requests.HTTPError as erro:
        if erro.response is not None and erro.response.status_code in NAO_EXISTE_NO_S3:
            return False
        raise
    return True


def descobrir_o_bps(cliente: Cliente, agora: datetime) -> list[Alvo]:
    """Um alvo por ano, de 2020 até o ano de hoje; o ano corrente só quando o ZIP dele já saiu."""
    alvos: list[Alvo] = []
    for ano in range(PRIMEIRO_ANO_DO_BPS, agora.year + 1):
        url = zip_do_bps(ano)
        if ano == agora.year and not _existe(cliente, url):
            continue
        alvos.append(Alvo(url, ".csv", obter_do_bps(ano)))
    return alvos


def fontes() -> list[Fonte]:
    """As fontes do lote, para a lista `FONTES` (os ids seguem a família da licença)."""
    return [
        *(
            Fonte(id_, MENSAL, _do_sicaf(ativo))
            for id_, ativo in SITUACOES_DO_SICAF.items()
        ),
        Fonte("bps", MENSAL, descobrir_o_bps),
    ]
