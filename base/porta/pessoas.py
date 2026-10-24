"""A porta dos sócios do CNPJ (ADR 0077, item 9; ADR 0106): a leitura do QSA e do restrito.

O CNPJ com sócios ainda não está no dicionário da base (é montado em partes por `scripts.carga_receita_mes`),
então a leitura dele vem por aqui, uma raiz de CNPJ por vez, nunca a tabela inteira de nomes:
- `qsa_da_raiz`: o quadro de sócios vigente de uma empresa (`<pasta>/vigente/qsa/<xx>.parquet`), só com o
  `id_pessoa` do sócio pessoa física;
- `pessoas_da_raiz`: os nomes e o CPF mascarado dessa empresa no restrito (`<restrita>/pessoas/<xx>/`);
- `oposicoes`: a tabela de oposições dos titulares (`<restrita>/pessoas_oposicoes.parquet`), só ids e datas;
- `ids_no_restrito`: todo `id_pessoa` que está no restrito (para conferir que a lápide ficou).
"""

from collections.abc import Sequence
from pathlib import Path

import pandas as pd

PASTA_DAS_PESSOAS = "pessoas"
ARQUIVO_DAS_OPOSICOES = "pessoas_oposicoes.parquet"
PREFIXO = 2  # a carga reparte pelos 2 primeiros caracteres da raiz
COLUNAS_DE_PESSOAS = ("id_pessoa", "cnpj_basico", "nome", "cpf_mascarado")


def _da_raiz(arquivos: list[Path], raiz: str, colunas: Sequence[str]) -> pd.DataFrame:
    if not arquivos:
        return pd.DataFrame(columns=list(colunas))
    # o filtro vai ao Parquet: só os grupos de linhas que podem ter a raiz são lidos (a busca por CNPJ
    # lê uma empresa por pedido; a vista é ordenada pela raiz, `base/vista_do_cnpj.py`)
    filtro = [("cnpj_basico", "==", raiz)]
    tabela = pd.concat(
        [pd.read_parquet(a, filters=filtro) for a in arquivos], ignore_index=True
    )
    return tabela[tabela["cnpj_basico"] == raiz].reset_index(drop=True)


def arquivos_de_pessoas(restrita: Path) -> list[Path]:
    """Os Parquets de `pessoas` no restrito (vazio antes da primeira carga)."""
    pasta = restrita / PASTA_DAS_PESSOAS
    return sorted(pasta.rglob("*.parquet")) if pasta.is_dir() else []


def pessoas_da_raiz(restrita: Path, raiz: str) -> pd.DataFrame:
    """Nome e CPF mascarado dos sócios pessoa física de uma empresa (raiz de 8 posições)."""
    pasta = restrita / PASTA_DAS_PESSOAS / raiz[:PREFIXO]
    arquivos = sorted(pasta.glob("*.parquet")) if pasta.is_dir() else []
    return _da_raiz(arquivos, raiz, COLUNAS_DE_PESSOAS)


def qsa_da_raiz(pasta: Path, raiz: str, colunas: Sequence[str]) -> pd.DataFrame:
    """O quadro de sócios vigente de uma empresa; `colunas` dá a forma da tabela vazia."""
    arquivo = pasta / "vigente" / "qsa" / f"{raiz[:PREFIXO]}.parquet"
    return _da_raiz([arquivo] if arquivo.is_file() else [], raiz, colunas)


def oposicoes(restrita: Path, colunas: Sequence[str]) -> pd.DataFrame:
    """A tabela de oposições (vazia, com `colunas`, antes do primeiro pedido)."""
    arquivo = restrita / ARQUIVO_DAS_OPOSICOES
    if not arquivo.is_file():
        return pd.DataFrame(columns=list(colunas))
    return pd.read_parquet(arquivo)


def ids_no_restrito(restrita: Path) -> pd.Series:
    """Todo `id_pessoa` de `pessoas` no restrito, com repetição (uma linha por papel)."""
    ids = [
        pd.read_parquet(a, columns=["id_pessoa"])["id_pessoa"]
        for a in arquivos_de_pessoas(restrita)
    ]
    return pd.concat(ids, ignore_index=True) if ids else pd.Series([], dtype=object)
