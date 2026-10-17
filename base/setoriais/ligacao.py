"""Ligação do código de cada fonte setorial à empresa, só pela B13 (`base/empresa_serie.py`): a chave
exata da fonte (o nome do agente na ANP, a sigla na ANAC), na linha principal da B13 com CNPJ. Nada é
casado por nome aproximado; o que não liga vai para os buracos, com o volume."""

import pandas as pd


def _ligadas(fonte: str, empresa_serie: pd.DataFrame) -> pd.DataFrame:
    linhas = empresa_serie[
        (empresa_serie["fonte"] == fonte)
        & empresa_serie["principal"].fillna(False).astype(bool)
        & empresa_serie["cnpj_companhia"].notna()
    ]
    return linhas.drop_duplicates("chave")[["chave", "cnpj_companhia"]]


def ligar(
    tabela: pd.DataFrame, coluna: str, fonte: str, empresa_serie: pd.DataFrame
) -> pd.DataFrame:
    """A tabela com `cnpj_companhia` (vazio quando a B13 não liga a chave)."""
    ligadas = _ligadas(fonte, empresa_serie).rename(columns={"chave": coluna})
    return tabela.merge(ligadas, on=coluna, how="left")


def buracos(
    tabela: pd.DataFrame,
    coluna: str,
    volume: str,
    fonte: str,
    empresa_serie: pd.DataFrame,
) -> pd.DataFrame:
    """As chaves sem ligação, do maior volume para o menor (chave, valor, primeira, última, fonte)."""
    ligada = ligar(tabela, coluna, fonte, empresa_serie)
    sem = ligada[ligada["cnpj_companhia"].isna()]
    tempo = "competencia" if "competencia" in sem else "instante"
    return (
        sem.groupby(coluna)
        .agg(valor=(volume, "sum"), primeira=(tempo, "min"), ultima=(tempo, "max"))
        .sort_values("valor", ascending=False)
        .reset_index()
        .rename(columns={coluna: "chave"})
        .assign(fonte=fonte)
    )
