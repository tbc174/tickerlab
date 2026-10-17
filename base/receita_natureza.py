"""Natureza jurídica e opção pelo MEI, do CNPJ aberto da Receita já guardado (`rfb-cnpj`).

**Só duas colunas de cada arquivo** (Q1 do plano da rede, "sim" do Tiago em 15/10/2026): (CNPJ básico,
natureza jurídica) dos `Empresas*.zip` e (CNPJ básico, opção pelo MEI) do `Simples.zip`. Razão social,
sócios e o resto nunca saem do leitor: a razão social do MEI e do empresário individual traz o nome e o
CPF da pessoa. É dado de empresa, já no acervo, e tira milhares de entidades de `nao_informada`.

Layout conferido no servidor de casa em 15/10 (cópia de 2026-10): sem cabeçalho, `;`, aspas, latin-1;
Empresas = básico; razão social; **natureza**; qualificação; capital; porte; ente federativo. Simples =
básico; opção Simples; datas; **opção MEI** (`S`/`N`); datas. Cada arquivo tem ~2 a 3 GB descompactado:
lê por partes e guarda só as raízes pedidas (as entidades da rede).
"""

import re
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import IO

import pandas as pd
import sqlalchemy as sa

from src import acervo
from src.banco.coletas import originais_mais_recentes

CODIFICACAO = "latin-1"
TAMANHO_DA_PARTE = 1_000_000
COLUNA_DA_NATUREZA = 2
COLUNA_DO_MEI = 4
OPTANTE = "S"
FONTE = "rfb-cnpj"
ARQUIVO = re.compile(r"/(\d{4}-\d{2})/(Empresas\d+|Simples)\.zip$")


def _partes(arquivo_zip: Path | IO[bytes], coluna: int) -> Iterator[pd.DataFrame]:
    with zipfile.ZipFile(arquivo_zip) as zipado:
        (membro,) = zipado.namelist()  # cada ZIP da Receita tem um arquivo só
        with zipado.open(membro) as texto:
            yield from pd.read_csv(
                texto, sep=";", header=None, usecols=[0, coluna], dtype=str,
                encoding=CODIFICACAO, keep_default_na=False, chunksize=TAMANHO_DA_PARTE,
            )  # fmt: skip


def _filtrar(
    arquivo_zip: Path | IO[bytes], coluna: int, raizes: set[str]
) -> pd.DataFrame:
    pedacos = [p[p[0].isin(raizes)] for p in _partes(arquivo_zip, coluna)]
    tabela = (
        pd.concat(pedacos, ignore_index=True)
        if pedacos
        else pd.DataFrame(columns=[0, coluna])
    )
    return tabela.rename(columns={0: "cnpj_basico", coluna: "valor"})


def ler_naturezas(arquivo_zip: Path | IO[bytes], raizes: set[str]) -> pd.DataFrame:
    """(cnpj_basico, natureza_juridica) das raízes pedidas, de um `Empresas*.zip`."""
    tabela = _filtrar(arquivo_zip, COLUNA_DA_NATUREZA, raizes)
    return pd.DataFrame(
        {
            "cnpj_basico": tabela["cnpj_basico"],
            "natureza_juridica": tabela["valor"].str.strip(),
        }
    )


def ler_mei(arquivo_zip: Path | IO[bytes], raizes: set[str]) -> pd.DataFrame:
    """(cnpj_basico, mei) das raízes pedidas que estão no `Simples.zip` (opção atual pelo MEI)."""
    tabela = _filtrar(arquivo_zip, COLUNA_DO_MEI, raizes)
    return pd.DataFrame(
        {
            "cnpj_basico": tabela["cnpj_basico"],
            "mei": tabela["valor"].str.strip() == OPTANTE,
        }
    )


def arquivos_do_mes_mais_recente(conexao: sa.Connection) -> list[tuple[str, Path]]:
    """(nome, caminho no acervo) dos `Empresas*.zip` e do `Simples.zip` do mês mais recente guardado."""
    pasta = acervo.pasta_do_acervo()
    if pasta is None:
        return []
    achados = []
    for original in originais_mais_recentes(conexao, FONTE):
        casou = ARQUIVO.search(original.url)
        if casou and (pasta / original.caminho_do_original).is_file():
            achados.append(
                (casou.group(1), casou.group(2), original.caminho_do_original)
            )
    if not achados:
        return []
    mes = max(m for m, _, _ in achados)
    return sorted((n, pasta / c) for m, n, c in achados if m == mes)
