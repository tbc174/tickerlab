"""Consulta e exportação de cada tabela da base, sem login (virada de 5/11/2026, fase 1, PR 3).

Três rotas em `/v1/base/tabelas`, com o mesmo limite por IP e a mesma origem permitida da busca
pública (`base_publica`): a lista das tabelas consultáveis, uma página de uma tabela em JSON e a
tabela em CSV, página a página. Só sai o que `base.dossie.pode_consultar` deixa (tabela que pode ser
mostrada e que a porta serve por Parquet do acervo); tabela de pessoa, barrada, fora da porta ou
inexistente responde o mesmo 404, sem dizer o motivo. As colunas de pessoa
(`base.dossie.COLUNAS_DE_PESSOA`) nunca saem, e a view da porta já esconde as linhas de pessoa
(ADR 0075).

Toda linha sai com a origem: a fonte e a licença vão no envelope; o dia em que a linha ficou pública
(`publico_em`) e a linhagem (`origem_sha256`, `origem_coletada_em`...) são colunas da própria tabela.
`como_era_em` corta o futuro: só o que já era público naquele dia, e a data nunca pode ser futura.

A porta abre a cada pedido (uma conexão do DuckDB não se compartilha entre threads) e a página é
cortada no SQL (`LIMIT`/`OFFSET`): o contêiner da API tem pouca memória, e o CSV sai em partes.
"""

import csv
import io
import json
import math
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache

import duckdb
import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from base import cnpj as cnpjs
from base import contrato, vitrine
from base import dossie as regras
from base import porta as porta_da_base
from base.dicionario import DATA, TABELAS, Tabela
from base.porta import Porta
from src.api_v1 import base_publica
from src.api_v1.acesso import exigir_api_ligada
from src.api_v1.base_publica import cabecalhos_do_site, recusar
from src.banco.coletas import licenca_da_fonte

LIMITE_PADRAO = 100
LIMITE_MAXIMO = 1000
LINHAS_POR_PAGINA_DO_CSV = 5_000
TETO_DO_CSV = 100_000
CABECALHO_DO_TETO = "X-TickerLab-Teto"
# o contêiner da API tem 1536m (`compose.yaml`): a porta fica com pouco e a página é cortada no SQL
MEMORIA_DA_PORTA = "512MB"
CACHE_PUBLICO = "public, max-age=3600"  # a base muda uma vez por dia
NAO_ENCONTRADA = "Tabela não encontrada."
INDISPONIVEL = "A consulta à base está indisponível agora. Tente novamente mais tarde."
AVISO = (
    "Cada linha diz quando ficou pública (publico_em) e de onde veio (fonte e licença). "
    "Nada aqui é recomendação de investimento."
)
APELIDOS_DAS_DATAS = {
    "aconteceu_em": "Dia a que a linha se refere",
    "publico_em": "Dia em que a linha ficou pública: um dado só entra a partir dele",
    "coletado_em": "Dia em que o TickerLab coletou a linha",
}
BOM = "﻿"  # o Excel abre UTF-8 com acento certo quando o arquivo começa com o BOM

router = APIRouter(
    prefix="/v1/base/tabelas",
    dependencies=[Depends(exigir_api_ligada), Depends(base_publica.conferir_pedido)],
)


def abrir_porta() -> Porta:
    """A porta da base, uma por pedido (os testes trocam esta função)."""
    return porta_da_base.abrir(memoria=MEMORIA_DA_PORTA)


def limpar_cache() -> None:
    """Zera o limite por IP e a lista das tabelas (testes e atualização manual)."""
    base_publica.LIMITE_POR_IP.zerar()
    _lista.cache_clear()


# --- o que pode sair ------------------------------------------------------------------------------
def _tabela_consultavel(request: Request, nome: str) -> Tabela:
    """A tabela pedida; o mesmo 404 para a que não existe, a de pessoa, a barrada e a fora da porta."""
    if not regras.pode_consultar(nome):
        raise recusar(request, 404, NAO_ENCONTRADA)
    return TABELAS[nome]


def _colunas_na_base(porta: Porta, nome: str) -> list[str]:
    """As colunas que a consulta serve: as da tabela nesta base, sem as de pessoa."""
    return [c for c in porta.colunas(nome) if c not in regras.COLUNAS_DE_PESSOA]


def _colunas_do_contrato(tabela: Tabela) -> list[dict[str, str]]:
    """As colunas pelo dicionário, sem as de pessoa, mais as datas pelos apelidos da porta."""
    colunas = [
        {"nome": nome, "tipo": unidade, "descricao": descricao}
        for nome, (descricao, unidade) in tabela.colunas.items()
        if nome not in regras.COLUNAS_DE_PESSOA
    ]
    for apelido, coluna in tabela.datas.items():
        if apelido != coluna:
            descricao = APELIDOS_DAS_DATAS.get(apelido, apelido)
            colunas.append(
                {
                    "nome": apelido,
                    "tipo": DATA,
                    "descricao": f"{descricao} (de `{coluna}`).",
                }
            )
    return colunas


def _origem(nome: str, tabela: Tabela) -> dict[str, object]:
    """De onde a tabela vem: vai em toda resposta (a atribuição que a licença pede). A licença sai
    como o site a mostra, sem a decisão interna entre parênteses."""
    licenca = licenca_da_fonte(tabela.familia_da_fonte)
    return {
        "tabela": nome,
        "versao": tabela.versao_do_contrato,
        "fonte": vitrine.primeira_frase(tabela.fonte),
        "orgao": vitrine.orgao_da_licenca(licenca),
        "licenca": vitrine.licenca_do_site(licenca),
    }


def _entrada_da_lista(linha: vitrine.TabelaDoSite) -> dict[str, object]:
    tabela = TABELAS[linha.tabela]
    return {
        **_origem(linha.tabela, tabela),
        "modulo": linha.modulo,
        "frase": linha.frase,
        "chaves": list(tabela.chaves),
        "colunas": _colunas_do_contrato(tabela),
        "historico_desde": linha.historico_desde,
        "frequencia": linha.frequencia,
        "situacao_da_licenca": linha.situacao,
    }


@lru_cache(maxsize=1)
def _lista() -> tuple[dict[str, object], ...]:
    """Uma entrada por tabela consultável, na ordem do catálogo (a mesma da página Dados)."""
    catalogo = vitrine.catalogo_publico(contrato.catalogo())
    frases = {nome: vitrine.primeira_frase(t.descricao) for nome, t in TABELAS.items()}
    return tuple(
        _entrada_da_lista(linha)
        for linha in vitrine.tabelas_do_catalogo(catalogo, frases)
        if linha.consultavel
    )


# --- o pedido -------------------------------------------------------------------------------------
def _dia_pedido(request: Request, como_era_em: str | None) -> date | None:
    """O `como_era_em` como data; 422 se não é AAAA-MM-DD ou está no futuro (nada do futuro sai)."""
    if como_era_em is None:
        return None
    try:
        dia = date.fromisoformat(como_era_em)
    except ValueError:
        raise recusar(
            request, 422, "como_era_em: use uma data no formato AAAA-MM-DD."
        ) from None
    if dia > base_publica.hoje():
        raise recusar(request, 422, "como_era_em: a data não pode estar no futuro.")
    return dia


def _conferir_pagina(request: Request, limite: int, deslocamento: int) -> None:
    if not 1 <= limite <= LIMITE_MAXIMO:
        raise recusar(request, 422, f"limite: um número de 1 a {LIMITE_MAXIMO}.")
    if deslocamento < 0:
        raise recusar(request, 422, "deslocamento: zero ou mais.")


def _filtro_do_cnpj(
    request: Request, nome: str, cnpj: str | None, colunas: list[str]
) -> dict[str, object]:
    """O filtro por CNPJ (14 dígitos ou formatado): pela coluna `cnpj` como a base guarda (formatado
    ou só dígitos) ou, se a tabela só tem `cnpj_basico`, pela raiz; 422 se o CNPJ não confere ou a
    tabela não é por CNPJ."""
    if cnpj is None:
        return {}
    completo = cnpjs.completo(cnpj)
    if completo is None or not cnpjs.dv_confere(completo):
        raise recusar(
            request, 422, "cnpj: confira os 14 caracteres e os dígitos verificadores."
        )
    if "cnpj" in colunas:
        return {"cnpj": [cnpjs.formatar(completo), completo]}
    if "cnpj_basico" in colunas:
        return {"cnpj_basico": completo[: cnpjs.TAMANHO_DA_RAIZ]}
    raise recusar(
        request,
        422,
        f"A tabela {nome} não é por CNPJ (não tem coluna cnpj nem cnpj_basico): peça sem o filtro.",
    )


# --- a porta --------------------------------------------------------------------------------------
def _abrir(request: Request) -> Porta:
    """A porta aberta; 503, sem dizer onde nem por quê, se a base não está neste servidor."""
    try:
        return abrir_porta()
    except (ImportError, OSError, ValueError) as erro:
        raise recusar(request, 503, INDISPONIVEL) from erro


@contextmanager
def _porta(request: Request) -> Iterator[Porta]:
    """A porta de um pedido; 503 se a tabela não tem arquivo nesta base ou a leitura falha."""
    with _abrir(request) as porta:
        try:
            yield porta
        except (duckdb.Error, OSError, KeyError) as erro:
            raise recusar(request, 503, INDISPONIVEL) from erro


# --- as células -----------------------------------------------------------------------------------
def _valor_json(valor: object, tipo: str = "") -> object:
    """Uma célula do pandas como JSON: vazio vira null, data vira ISO (só o dia quando a coluna é
    `DATE`), número do numpy vira número do Python, lista e struct entram por dentro."""
    if isinstance(valor, Mapping):
        return {str(chave): _valor_json(item) for chave, item in valor.items()}
    if isinstance(valor, list | tuple | np.ndarray):
        return [_valor_json(item) for item in valor]
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):
        return None
    if isinstance(valor, pd.Timestamp | datetime):
        return valor.date().isoformat() if tipo == "DATE" else valor.isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return float(valor)
    item = getattr(valor, "item", None)
    if callable(item):
        valor = item()  # número ou booleano do numpy vira o do Python
    if isinstance(valor, float) and not math.isfinite(valor):
        return None
    return valor if isinstance(valor, bool | int | float | str) else str(valor)


def _linhas_json(
    pagina: pd.DataFrame, tipos: Mapping[str, str]
) -> list[dict[str, object]]:
    nomes = [str(c) for c in pagina.columns]
    return [
        {c: _valor_json(v, tipos.get(c, "")) for c, v in zip(nomes, linha, strict=True)}
        for linha in pagina.itertuples(index=False, name=None)
    ]


def _texto_csv(valor: object, tipo: str) -> str:
    """Uma célula do CSV: vazio fica vazio, booleano `true`/`false`, data em ISO, lista em JSON."""
    convertido = _valor_json(valor, tipo)
    if convertido is None:
        return ""
    if isinstance(convertido, bool):
        return "true" if convertido else "false"
    if isinstance(convertido, list | dict):
        return json.dumps(convertido, ensure_ascii=False)
    return str(convertido)


def _linhas_csv(pagina: pd.DataFrame, tipos: Mapping[str, str]) -> bytes:
    """As linhas da página em CSV (vírgula, aspas quando preciso), sem cabeçalho."""
    saida = io.StringIO()
    escritor = csv.writer(saida)
    nomes = [str(c) for c in pagina.columns]
    for linha in pagina.itertuples(index=False, name=None):
        escritor.writerow(
            [_texto_csv(v, tipos.get(c, "")) for c, v in zip(nomes, linha, strict=True)]
        )
    return saida.getvalue().encode("utf-8")


def _cabecalho_csv(colunas: list[str]) -> bytes:
    saida = io.StringIO()
    csv.writer(saida).writerow(colunas)
    return (BOM + saida.getvalue()).encode("utf-8")


# --- as rotas -------------------------------------------------------------------------------------
@router.get("")
def listar(request: Request) -> JSONResponse:
    """As tabelas que podem ser consultadas e exportadas, com colunas, chaves, fonte e licença."""
    return JSONResponse(
        {
            "tabelas": list(_lista()),
            "limite_maximo": LIMITE_MAXIMO,
            "teto_do_csv": TETO_DO_CSV,
        },
        headers={**cabecalhos_do_site(request), "Cache-Control": CACHE_PUBLICO},
    )


def _pagina_do_csv(
    porta: Porta,
    nome: str,
    dia: date | None,
    filtros: Mapping[str, object],
    colunas: list[str],
    deslocamento: int,
) -> pd.DataFrame:
    return porta.ler_pagina(
        nome,
        como_era_em=dia,
        filtros=filtros,
        colunas=colunas,
        limite=LINHAS_POR_PAGINA_DO_CSV,
        deslocamento=deslocamento,
    )


def _comeco_do_csv(
    request: Request, porta: Porta, nome: str, dia: date | None, cnpj: str | None
) -> tuple[list[str], dict[str, object], dict[str, str], pd.DataFrame]:
    """As colunas, o filtro, os tipos e a primeira página, lidos antes de responder: base que falha
    dá 503, não um CSV cortado no meio."""
    try:
        colunas = _colunas_na_base(porta, nome)
        filtros = _filtro_do_cnpj(request, nome, cnpj, colunas)
        tipos = porta.tipos(nome)
        primeira = _pagina_do_csv(porta, nome, dia, filtros, colunas, 0)
    except (duckdb.Error, OSError, KeyError) as erro:
        raise recusar(request, 503, INDISPONIVEL) from erro
    return colunas, filtros, tipos, primeira


def _csv(
    porta: Porta,
    nome: str,
    dia: date | None,
    filtros: Mapping[str, object],
    colunas: list[str],
    tipos: Mapping[str, str],
    primeira: pd.DataFrame,
) -> Iterator[bytes]:
    """O CSV em partes: BOM e cabeçalho, a primeira página já lida e as seguintes até o fim ou o teto;
    a porta fecha no fim, mesmo se quem pediu desligou no meio."""
    try:
        yield _cabecalho_csv(colunas)
        pagina, enviadas = primeira, 0
        while not pagina.empty:
            pagina = pagina.head(TETO_DO_CSV - enviadas)
            yield _linhas_csv(pagina, tipos)
            enviadas += len(pagina)
            if enviadas >= TETO_DO_CSV or len(pagina) < LINHAS_POR_PAGINA_DO_CSV:
                break
            pagina = _pagina_do_csv(porta, nome, dia, filtros, colunas, enviadas)
    finally:
        porta.fechar()


@router.get("/{nome}.csv")
def exportar(
    request: Request,
    nome: str,
    cnpj: str | None = None,
    como_era_em: str | None = None,
) -> StreamingResponse:
    """A tabela em CSV (UTF-8 com BOM, vírgula), página a página, até `TETO_DO_CSV` linhas."""
    _tabela_consultavel(request, nome)
    dia = _dia_pedido(request, como_era_em)
    porta = _abrir(request)
    try:
        colunas, filtros, tipos, primeira = _comeco_do_csv(
            request, porta, nome, dia, cnpj
        )
    except HTTPException:
        porta.fechar()
        raise
    return StreamingResponse(
        _csv(porta, nome, dia, filtros, colunas, tipos, primeira),
        media_type="text/csv; charset=utf-8",
        headers={
            **cabecalhos_do_site(request),
            "Cache-Control": CACHE_PUBLICO,
            "Content-Disposition": f'attachment; filename="{nome}.csv"',
            CABECALHO_DO_TETO: str(TETO_DO_CSV),
        },
    )


@router.get("/{nome}")
def consultar(
    request: Request,
    nome: str,
    cnpj: str | None = None,
    como_era_em: str | None = None,
    limite: int = LIMITE_PADRAO,
    deslocamento: int = 0,
) -> JSONResponse:
    """Uma página da tabela, na ordem das chaves do contrato, com o total e a origem."""
    tabela = _tabela_consultavel(request, nome)
    dia = _dia_pedido(request, como_era_em)
    _conferir_pagina(request, limite, deslocamento)
    with _porta(request) as porta:
        colunas = _colunas_na_base(porta, nome)
        filtros = _filtro_do_cnpj(request, nome, cnpj, colunas)
        total = porta.contar(nome, como_era_em=dia, filtros=filtros)
        pagina = porta.ler_pagina(
            nome,
            como_era_em=dia,
            filtros=filtros,
            colunas=colunas,
            limite=limite,
            deslocamento=deslocamento,
        )
        tipos = porta.tipos(nome)
    corpo = {
        **_origem(nome, tabela),
        "como_era_em": dia.isoformat() if dia else None,
        "total": total,
        "limite": limite,
        "deslocamento": deslocamento,
        "colunas": colunas,
        "linhas": _linhas_json(pagina, tipos),
        "aviso": AVISO,
    }
    return JSONResponse(
        corpo, headers={**cabecalhos_do_site(request), "Cache-Control": CACHE_PUBLICO}
    )
