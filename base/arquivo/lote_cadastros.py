"""Lote "cadastros globais" (rodada 4 da pesquisa de dados escondidos, linha 287 da fila): quem é quem
no mundo, por identificador (LEI, ISIN, CNPJ, CIK, ticker), e as listas de sanções de empresas.

Fontes (ADR 0102: coleta com ritmo, uso citando a fonte; ADR 0088: **só pessoa jurídica**):

- **GLEIF, golden copy** (CC0): o cadastro mundial de LEI (`lei2`), as relações entre entidades (`rr`,
  mãe direta e final) e as exceções de relato (`repex`). O `lei2` traz também as firmas individuais
  (`SOLE_PROPRIETOR`, pessoa física): essas linhas saem **antes** de guardar. A API de nível 2 por
  LEI (filhas, mãe final, ISIN) é sob demanda e já está no `gleif-br`/`gleif-emissores`; aqui entra o
  que a golden copy entrega inteiro, de uma vez;
- **Wikidata** (CC0), pelo SPARQL: LEI, ISIN, CNPJ, CIK e os itens listados na B3 (Q796297), sem os
  itens que são gente (Q5). Um pedido por vez, com o agente do TickerLab;
- **SEC `company_tickers.json`** (domínio público): ticker → CIK de quem arquiva na SEC;
- **sanções** (só **entidades**, nunca pessoas): OFAC SDN (`sdn.csv`), a lista consolidada da União
  Europeia (CSV com o token público do próprio site) e a ConList do OFSI (OGL v3). A lista da ONU fica
  de fora (termos pessoais, não comerciais).

Fora daqui, de propósito: OpenSanctions, Open Ownership, ICIJ, ONU, OpenCorporates, OpenFIGI, EU BRIS e
Companies House (licença não comercial, pessoas físicas ou agregador pago; `licencas-por-fonte.md`).

Regras (testes em `tests/test_base_arquivo_lote_cadastros.py`):
- cada filtro de LGPD é uma função de arquivo para arquivo, testada com um dublê que mistura pessoa
  física e jurídica; fonte nova de sanção sem filtro não entra;
- a golden copy muda de endereço todo dia (a data e o número do arquivo estão no caminho): a chave da
  coleta é o endereço **estável** do "último publicado", e a versão é a do arquivo de verdade
  (ETag, Last-Modified e tamanho), então ninguém baixa 480 MB duas vezes para o mesmo arquivo;
- o `lei2` e o `repex` rodam por mês (o arquivo cheio do `lei2` tem ~480 MB), o `rr` por semana;
- API que falha ou muda de formato é falha (`ErroDeDescoberta`), nunca "nada novo".
"""

import csv
import io
import json
import zipfile
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from base.arquivo.coleta import (
    Alvo,
    Cliente,
    Descobrir,
    ErroDeDescoberta,
    Fonte,
    Obter,
    assinatura,
)

PAUSA_ENTRE_PEDIDOS_A_CADASTROS_EM_SEGUNDOS = 1.0
# o Wikidata pede um pedido por vez e responde devagar a consulta pesada: espera maior
PAUSA_ENTRE_CONSULTAS_AO_WIKIDATA_EM_SEGUNDOS = 5.0

# ---- GLEIF, golden copy ----------------------------------------------------------------------
GOLDEN_COPY_DO_GLEIF = "https://goldencopy.gleif.org/api/v2/golden-copies/publishes"
# a coluna do `lei2` que diz se a entidade é firma individual (pessoa física)
COLUNA_DA_CATEGORIA_DO_LEI = "Entity.EntityCategory"
CATEGORIA_DE_PESSOA_FISICA_NO_LEI = "SOLE_PROPRIETOR"
# o que sai de cada arquivo da golden copy: id, grupo (ritmo) e se precisa do filtro de LGPD
ARQUIVOS_DA_GOLDEN_COPY = {
    "gleif-goldencopy-lei2": ("lei2", "mensal"),
    "gleif-goldencopy-rr": ("rr", "semanal"),
    "gleif-goldencopy-repex": ("repex", "mensal"),
}
TIPO_CHAVE_DO_LEI2 = "lei2"

# ---- Wikidata (SPARQL) -----------------------------------------------------------------------
WIKIDATA = "https://query.wikidata.org/sparql"
ITEM_B3 = "Q796297"  # a B3 (São Paulo Stock Exchange)
# itens que são gente (instância de Q5) ficam fora de todas as consultas
SEM_GENTE = "FILTER NOT EXISTS { ?item wdt:P31 wd:Q5 }"
NOME_EM_INGLES = 'OPTIONAL { ?item rdfs:label ?nome FILTER(LANG(?nome) = "en") }'
IDENTIFICADORES_DO_WIKIDATA = {
    "wikidata-lei": "P1278",
    "wikidata-isin": "P946",
    "wikidata-cnpj": "P6204",
    "wikidata-cik": "P5531",
}

# ---- SEC -------------------------------------------------------------------------------------
TICKERS_DA_SEC = "https://www.sec.gov/files/company_tickers.json"

# ---- sanções (só entidades) ------------------------------------------------------------------
OFAC_SDN = "https://www.treasury.gov/ofac/downloads/sdn.csv"
COLUNA_DO_TIPO_NO_SDN = 2  # sem cabeçalho: número, nome, tipo, programa...
TIPO_DE_ENTIDADE_NO_SDN = (
    "-0-"  # pessoa é "individual"; "vessel" e "aircraft" também saem
)
# o token é público (está no endereço de download do próprio site da Comissão Europeia)
UE_SANCOES = (
    "https://webgate.ec.europa.eu/fsd/fsf/public/files/csvFullSanctionsList_1_1/content"
    "?token=dG9rZW4tMjAxNw"
)
COLUNA_DO_TIPO_NA_UE = "Entity_SubjectType_ClassificationCode"
TIPO_DE_EMPRESA_NA_UE = "enterprise"
OFSI_CONLIST = (
    "https://ofsistorage.blob.core.windows.net/publishlive/2022format/ConList.csv"
)
COLUNA_DO_TIPO_NO_OFSI = "Group Type"
TIPO_DE_ENTIDADE_NO_OFSI = "Entity"
# a ConList começa com uma linha "Last Updated,data" antes do cabeçalho
LINHAS_ANTES_DO_CABECALHO_DO_OFSI = 1


# ---- filtros de LGPD (arquivo para arquivo) --------------------------------------------------
def _csv_filtrado(
    bruto: Path,
    destino: Path,
    manter: Callable[[list[str]], bool],
    *,
    codificacao: str,
    delimitador: str = ",",
    linhas_de_cabecalho: int = 0,
    cabecalho: Callable[[list[str]], None] | None = None,
) -> None:
    """Copia o CSV para `destino` mantendo as primeiras `linhas_de_cabecalho` linhas e só as
    linhas seguintes para as quais `manter` diz sim. `cabecalho` recebe a última linha de
    cabeçalho (para conferir que a coluna que decide a LGPD existe)."""
    with (
        bruto.open(encoding=codificacao, newline="") as entrada,
        destino.open("w", encoding=codificacao, newline="") as saida,
    ):
        leitor = csv.reader(entrada, delimiter=delimitador)
        escritor = csv.writer(saida, delimiter=delimitador, lineterminator="\r\n")
        for numero, linha in enumerate(leitor):
            if numero < linhas_de_cabecalho:
                escritor.writerow(linha)
                if numero == linhas_de_cabecalho - 1 and cabecalho is not None:
                    cabecalho(linha)
            elif manter(linha):
                escritor.writerow(linha)


def sdn_so_com_entidades(bruto: Path, destino: Path) -> None:
    """A lista SDN da OFAC só com as entidades (tipo "-0-"): pessoa, navio e avião saem."""
    _csv_filtrado(
        bruto,
        destino,
        lambda linha: (
            len(linha) > COLUNA_DO_TIPO_NO_SDN
            and linha[COLUNA_DO_TIPO_NO_SDN].strip() == TIPO_DE_ENTIDADE_NO_SDN
        ),
        codificacao="latin-1",  # não perde byte nenhum na ida e na volta
    )


def sancoes_da_ue_so_com_empresas(bruto: Path, destino: Path) -> None:
    """A lista consolidada da UE (CSV com ";" e BOM) só com as linhas de empresa."""
    posicao: list[int] = []

    def achar_coluna(cabecalho: list[str]) -> None:
        nomes = [c.lstrip("﻿") for c in cabecalho]
        if COLUNA_DO_TIPO_NA_UE not in nomes:
            raise ErroDeDescoberta(
                f"lista da UE sem a coluna {COLUNA_DO_TIPO_NA_UE} (formato mudou)"
            )
        posicao.append(nomes.index(COLUNA_DO_TIPO_NA_UE))

    _csv_filtrado(
        bruto,
        destino,
        lambda linha: (
            len(linha) > posicao[0] and linha[posicao[0]] == TIPO_DE_EMPRESA_NA_UE
        ),
        codificacao="utf-8-sig",
        delimitador=";",
        linhas_de_cabecalho=1,
        cabecalho=achar_coluna,
    )


def conlist_do_ofsi_so_com_entidades(bruto: Path, destino: Path) -> None:
    """A ConList do OFSI só com o grupo "Entity" (indivíduo e navio saem)."""
    posicao: list[int] = []

    def achar_coluna(cabecalho: list[str]) -> None:
        if COLUNA_DO_TIPO_NO_OFSI not in cabecalho:
            raise ErroDeDescoberta(
                f"ConList do OFSI sem a coluna {COLUNA_DO_TIPO_NO_OFSI} (formato mudou)"
            )
        posicao.append(cabecalho.index(COLUNA_DO_TIPO_NO_OFSI))

    _csv_filtrado(
        bruto,
        destino,
        lambda linha: (
            len(linha) > posicao[0] and linha[posicao[0]] == TIPO_DE_ENTIDADE_NO_OFSI
        ),
        codificacao="utf-8-sig",
        linhas_de_cabecalho=LINHAS_ANTES_DO_CABECALHO_DO_OFSI + 1,
        cabecalho=achar_coluna,
    )


def lei2_so_com_pessoa_juridica(bruto: Path, destino: Path) -> int:
    """Regrava o ZIP da golden copy do `lei2` sem as firmas individuais (`SOLE_PROPRIETOR`, pessoa
    física). Devolve quantas linhas saíram. Lê e escreve em fluxo: o CSV tem ~3,5 milhões de linhas."""
    removidas = 0
    with zipfile.ZipFile(bruto) as entrada:
        (membro,) = [m for m in entrada.infolist() if m.filename.endswith(".csv")]
        with (
            entrada.open(membro) as bytes_do_csv,
            zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as saida,
            saida.open(membro.filename, "w", force_zip64=True) as bytes_de_saida,
            io.TextIOWrapper(bytes_do_csv, encoding="utf-8", newline="") as texto_in,
            io.TextIOWrapper(bytes_de_saida, encoding="utf-8", newline="") as texto_out,
        ):
            leitor = csv.reader(texto_in)
            escritor = csv.writer(texto_out, lineterminator="\n")
            cabecalho = next(leitor)
            if COLUNA_DA_CATEGORIA_DO_LEI not in cabecalho:
                raise ErroDeDescoberta(
                    f"lei2 sem a coluna {COLUNA_DA_CATEGORIA_DO_LEI} (formato mudou)"
                )
            posicao = cabecalho.index(COLUNA_DA_CATEGORIA_DO_LEI)
            escritor.writerow(cabecalho)
            for linha in leitor:
                if linha[posicao] == CATEGORIA_DE_PESSOA_FISICA_NO_LEI:
                    removidas += 1
                else:
                    escritor.writerow(linha)
    return removidas


# ---- como obter (baixa para `.bruto`, filtra, devolve os cabeçalhos da origem) ---------------
def _filtrado(url: str, filtro: Callable[[Path, Path], object]) -> Obter:
    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        bruto = destino.with_name(destino.name + ".bruto")
        try:
            cabecalhos = cliente.baixar(url, bruto)
            filtro(bruto, destino)
        finally:
            bruto.unlink(missing_ok=True)
        return cabecalhos

    return obter


def _csv_de_sancoes(url: str, filtro: Callable[[Path, Path], None]) -> Descobrir:
    def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        return [Alvo(url, ".csv", _filtrado(url, filtro))]

    return _descobrir


# ---- descobertas -----------------------------------------------------------------------------
def endereco_do_ultimo_da_golden_copy(tipo: str) -> str:
    """O endereço estável do "último publicado" de um tipo (`lei2`, `rr`, `repex`)."""
    return f"{GOLDEN_COPY_DO_GLEIF}/{tipo}/latest"


def descobrir_golden_copy(tipo: str) -> Descobrir:
    """O CSV cheio do último publicado: o `Alvo` tem a chave estável do "último" e a versão do ZIP
    de verdade (o endereço dele muda todo dia, o arquivo muda quando o GLEIF publica outro)."""
    chave = endereco_do_ultimo_da_golden_copy(tipo)

    def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        publicado = json.loads(cliente.ler(chave).conteudo)
        try:
            url = publicado["data"]["full_file"]["csv"]["url"]
        except (KeyError, TypeError) as erro:
            raise ErroDeDescoberta(
                f"GLEIF: resposta inesperada em {chave} (sem full_file.csv.url)"
            ) from erro
        versao = assinatura(cliente.cabecalhos(url))
        # `rr` (relações) e `repex` (exceções) só têm código LEI e tipo de relação, sem nome de pessoa
        obter = (
            _filtrado(url, lei2_so_com_pessoa_juridica)
            if tipo == TIPO_CHAVE_DO_LEI2
            else _inteiro(url)
        )
        return [
            Alvo(
                chave,
                ".csv.zip",
                obter,
                versao=None if versao == assinatura({}) else versao,
            )
        ]

    return _descobrir


def _inteiro(url: str) -> Obter:
    def obter(cliente: Cliente, destino: Path) -> Mapping[str, str]:
        return cliente.baixar(url, destino)

    return obter


def consulta_do_wikidata(propriedade: str) -> str:
    """O SPARQL de um identificador: item, valor e nome em inglês, sem gente, em ordem de item (a
    ordem fixa faz o SHA-256 dizer "igual" quando nada mudou)."""
    return (
        f"SELECT ?item ?valor ?nome WHERE {{ ?item wdt:{propriedade} ?valor . "
        f"{SEM_GENTE} {NOME_EM_INGLES} }} ORDER BY ?item ?valor"
    )


def consulta_dos_listados_na_b3() -> str:
    """Os itens listados na B3, com o ticker (qualificador P249 da bolsa) e o nome em inglês."""
    return (
        "SELECT ?item ?ticker ?nome WHERE { ?item p:P414 ?bolsa . "
        f"?bolsa ps:P414 wd:{ITEM_B3} . OPTIONAL {{ ?bolsa pq:P249 ?ticker }} "
        f"{SEM_GENTE} {NOME_EM_INGLES} }} ORDER BY ?item ?ticker"
    )


def endereco_do_wikidata(consulta: str) -> str:
    return f"{WIKIDATA}?{urlencode({'format': 'json', 'query': consulta})}"


def descobrir_wikidata(consulta: str) -> Descobrir:
    def _descobrir(cliente: Cliente, agora: datetime) -> list[Alvo]:
        return [Alvo(endereco_do_wikidata(consulta), ".json")]

    return _descobrir


def descobrir_tickers_da_sec(cliente: Cliente, agora: datetime) -> list[Alvo]:
    return [Alvo(TICKERS_DA_SEC, ".json")]


# ---- as fontes -------------------------------------------------------------------------------
def fontes() -> list[Fonte]:
    """Todas as fontes do lote, para o `FONTES` do arquivista."""
    pausa = PAUSA_ENTRE_PEDIDOS_A_CADASTROS_EM_SEGUNDOS
    da_golden_copy = [
        Fonte(
            id_,
            grupo,
            descobrir_golden_copy(tipo),
            "zip",
            pesada=True,
            pausa_minima=pausa,
        )
        for id_, (tipo, grupo) in ARQUIVOS_DA_GOLDEN_COPY.items()
    ]
    do_wikidata = [
        *(
            Fonte(
                id_,
                "mensal",
                descobrir_wikidata(consulta_do_wikidata(propriedade)),
                "json",
                pausa_minima=PAUSA_ENTRE_CONSULTAS_AO_WIKIDATA_EM_SEGUNDOS,
            )
            for id_, propriedade in IDENTIFICADORES_DO_WIKIDATA.items()
        ),
        Fonte(
            "wikidata-b3",
            "mensal",
            descobrir_wikidata(consulta_dos_listados_na_b3()),
            "json",
            pausa_minima=PAUSA_ENTRE_CONSULTAS_AO_WIKIDATA_EM_SEGUNDOS,
        ),
    ]
    das_sancoes = [
        Fonte(
            "ofac-sdn",
            "diaria",
            _csv_de_sancoes(OFAC_SDN, sdn_so_com_entidades),
            "arquivo",
            pausa_minima=pausa,
        ),
        Fonte(
            "eufsf-sancoes",
            "diaria",
            _csv_de_sancoes(UE_SANCOES, sancoes_da_ue_so_com_empresas),
            "arquivo",
            pausa_minima=pausa,
        ),
        Fonte(
            "ofsi-conlist",
            "diaria",
            _csv_de_sancoes(OFSI_CONLIST, conlist_do_ofsi_so_com_entidades),
            "arquivo",
            pausa_minima=pausa,
        ),
    ]
    return [
        *da_golden_copy,
        *do_wikidata,
        Fonte(
            "sec-company-tickers",
            "semanal",
            descobrir_tickers_da_sec,
            "json",
            pausa_minima=pausa,
        ),
        *das_sancoes,
    ]


# páginas de termos que a vigia acompanha (avisa quando o texto muda); a OFAC não tem página de termos
# própria (obra do governo dos EUA em domínio público), o GLEIF e a SEC já têm vigia (`termos-gleif`,
# `termos-sec`)
TERMOS_DOS_CADASTROS = {
    "termos-wikidata": "https://www.wikidata.org/wiki/Wikidata:Licensing",
    "termos-eufsf": "https://commission.europa.eu/legal-notice_en",
    "termos-ofsi": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
}


def termos() -> dict[str, str]:
    """Os endereços de termos de uso do lote, para o `TERMOS` do arquivista."""
    return dict(TERMOS_DOS_CADASTROS)
