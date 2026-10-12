"""Séries de retorno de cada tentativa da M2 (para o PBO e o DSR compararem com tudo o que já foi testado).

Cada tentativa guarda a carteira do desenvolvimento (o caminho mediano, para modelos; a série
inteira, para baselines) com custos ×1 e ×2 em `pesquisa_m2/series/<hash>.parquet`. As baselines
também ficam com um nome fixo (`baseline_B1.parquet`), porque o critério A5 compara com a B1.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from trader.registro import PASTA_DA_PESQUISA

PASTA_PADRAO = PASTA_DA_PESQUISA / "series"


def salvar(
    hash_: str,
    x1: pd.Series,
    x2: pd.Series,
    pasta: Path = PASTA_PADRAO,
    apelido: str = "",
) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    tabela = pd.concat({"x1": x1, "x2": x2}, axis=1, sort=True)
    caminho = pasta / f"{hash_}.parquet"
    tabela.to_parquet(caminho)
    if apelido:
        tabela.to_parquet(pasta / f"{apelido}.parquet")
    return caminho


def carregar(nome: str, pasta: Path = PASTA_PADRAO) -> pd.DataFrame:
    caminho = pasta / f"{nome}.parquet"
    if not caminho.exists():
        raise FileNotFoundError(
            f"Série {nome} não encontrada em {pasta}. Rode antes `python -m trader.rodar_baselines`."
        )
    return pd.read_parquet(caminho)


def todas(pasta: Path = PASTA_PADRAO) -> dict[str, pd.DataFrame]:
    """Todas as tentativas guardadas (pelo hash; os apelidos ficam de fora para não contar duas vezes)."""
    if not pasta.exists():
        return {}
    return {
        a.stem: pd.read_parquet(a)
        for a in sorted(pasta.glob("*.parquet"))
        if len(a.stem) == 64
    }


def candidatos(
    indice: pd.DatetimeIndex, coluna: str = "x1", pasta: Path = PASTA_PADRAO
) -> pd.DataFrame:
    """Uma coluna por tentativa guardada, nas datas pedidas (dia sem dado = 0, sem posição)."""
    series = {h: t[coluna] for h, t in todas(pasta).items()}
    if not series:
        return pd.DataFrame(index=indice)
    return pd.concat(series, axis=1, sort=True).reindex(indice).fillna(0.0)
