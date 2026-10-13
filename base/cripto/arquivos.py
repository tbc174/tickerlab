"""Gravar e ler as tabelas da base de cripto em Parquet (usado pela leitura do nó e pela coleta).

Cada tabela é uma pasta com vários arquivos Parquet (por mês ou por ano). Acrescentar linhas troca
as que já existem com a mesma chave (a última vence): refazer uma coleta não duplica nada.
"""

import os
from collections.abc import Sequence
from pathlib import Path

import pandas as pd


def acrescentar(
    pasta: Path, novas: pd.DataFrame, arquivo_de: pd.Series, chave: str | Sequence[str]
) -> None:
    """Junta `novas` aos arquivos da pasta (nome do arquivo por linha em `arquivo_de`)."""
    colunas_da_chave = [chave] if isinstance(chave, str) else list(chave)
    for nome, grupo in novas.groupby(arquivo_de):
        arquivo = pasta / f"{nome}.parquet"
        juntas = (
            pd.concat([pd.read_parquet(arquivo), grupo]) if arquivo.exists() else grupo
        )
        juntas = juntas.drop_duplicates(colunas_da_chave, keep="last").sort_values(
            colunas_da_chave
        )
        gravar_parquet(arquivo, juntas)


def gravar_parquet(arquivo: Path, tabela: pd.DataFrame) -> None:
    """Grava inteiro ou nada: escreve ao lado e troca de nome no fim."""
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    provisorio = arquivo.with_name(arquivo.name + ".provisorio")
    tabela.to_parquet(provisorio, index=False)
    os.replace(provisorio, arquivo)


def arquivos_da_tabela(pasta: Path) -> list[Path]:
    """Os arquivos Parquet da tabela, em ordem de nome."""
    return sorted(pasta.rglob("*.parquet")) if pasta.exists() else []


def ler_tabela(pasta: Path, ordem: str | Sequence[str]) -> pd.DataFrame:
    """A tabela inteira, ordenada (vazia se ainda não há arquivo)."""
    arquivos = arquivos_da_tabela(pasta)
    if not arquivos:
        return pd.DataFrame()
    tabela = pd.concat(pd.read_parquet(arquivo) for arquivo in arquivos)
    colunas = [ordem] if isinstance(ordem, str) else list(ordem)
    return tabela.sort_values(colunas).reset_index(drop=True)
