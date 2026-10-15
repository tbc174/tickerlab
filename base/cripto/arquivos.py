"""Gravar e ler as tabelas da base de cripto em Parquet (usado pela leitura do nó e pela coleta).

Cada tabela é uma pasta com vários arquivos Parquet (por mês ou por ano). Acrescentar linhas troca
as que já existem com a mesma chave (a última vence): refazer uma coleta não duplica nada.
"""

from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from base.parquet import gravar_se_mudou


def acrescentar(
    pasta: Path, novas: pd.DataFrame, arquivo_de: pd.Series, chave: str | Sequence[str]
) -> int:
    """Junta `novas` aos arquivos da pasta (nome do arquivo por linha em `arquivo_de`) e devolve
    quantas chaves não existiam (as que já existiam são regravadas, não contam)."""
    colunas_da_chave = [chave] if isinstance(chave, str) else list(chave)
    chaves_novas = 0
    for nome, grupo in novas.groupby(arquivo_de):
        arquivo = pasta / f"{nome}.parquet"
        guardadas = pd.read_parquet(arquivo) if arquivo.exists() else grupo.iloc[0:0]
        ja_existiam = grupo.set_index(colunas_da_chave).index.isin(
            guardadas.set_index(colunas_da_chave).index
        )
        chaves_novas += int((~ja_existiam).sum())
        juntas = pd.concat([guardadas, grupo]) if arquivo.exists() else grupo
        juntas = juntas.drop_duplicates(colunas_da_chave, keep="last").sort_values(
            colunas_da_chave
        )
        gravar_parquet(arquivo, juntas)
    return chaves_novas


def gravar_parquet(arquivo: Path, tabela: pd.DataFrame) -> None:
    """Grava inteiro ou nada, com manifesto ao lado (entra na âncora no Bitcoin, ADR 0078).

    Sem regravar o que não mudou (o nó roda a cada 10 min) e sem versão `.vN`: na cripto a linha
    refeita substitui a anterior de propósito, e a linhagem fica nas colunas (`coletado_em`,
    `divulgado_em`), não nas origens do manifesto.
    """
    gravar_se_mudou(tabela, arquivo, [], [], carimbos=("coletado_em",), versoes=False)


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
