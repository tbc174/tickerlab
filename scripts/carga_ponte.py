"""Lê a ponte (cadastro da fonte) já gravada na base, para o CNPJ das tabelas de código (linha 904, lote 4).

Fica num montador (`scripts/carga_*`) porque relê Parquet que a própria carga gravou (ADR 0077, item 9).
Quem liga o código ao CNPJ é `base/cnpj_pela_ponte.py`.

Roda: outro script (importado por scripts/carga_setoriais.py e scripts/carga_bcb_credito.py; não roda sozinho).
"""

from pathlib import Path

import pandas as pd

from base.parquet import arquivos_atuais, ler_tabela, origem_de_tabela


def ler_ponte(
    pasta: Path, raiz: Path
) -> tuple[pd.DataFrame | None, list[dict[str, str]]]:
    """A ponte gravada em `pasta` (todos os Parquets atuais, sem as versões guardadas) e as origens dela.

    `None` e nenhuma origem quando a pasta ainda não existe (a ponte não foi montada). As origens são as
    tabelas da ponte (`origem_de_tabela`, caminho a partir de `raiz`): a tabela que usa a ponte se refaz quando
    a ponte muda, e a linhagem dela chega aos originais pela ponte (série 4)."""
    arquivos = arquivos_atuais(pasta) if pasta.is_dir() else []
    if not arquivos:
        return None, []
    ponte = pd.concat([ler_tabela(a) for a in arquivos], ignore_index=True)
    return ponte, [origem_de_tabela(arquivo, raiz) for arquivo in arquivos]
