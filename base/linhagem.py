"""Linhagem para auditoria (série 3 da base de ML, PR 1; ADR 0055, exigência 13).

De qualquer linha de uma base em Parquet (`base/ponto_no_tempo.py::gravar_parquet`), refaz o caminho:
o `<ano>.json` ao lado do Parquet dá o hash da base, a versão do código e as origens (endereço e
SHA-256 de cada original); o registro de coletas dá a data da coleta e onde o original está no acervo;
o acervo confirma que o arquivo guardado ainda tem aquele SHA-256. A linhagem é "completa" só se
todos os elos existem e conferem.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from base.parquet import conferir_tabela
from base.ponto_no_tempo import SEM_DATA, conferir_pasta
from src import acervo
from src.banco.modelo import coletas


@dataclass(frozen=True)
class Origem:
    url: str
    sha256: str
    baixado_em: datetime | None  # None: nenhuma coleta registrada com este arquivo
    caminho_do_original: str | None
    original_confere: bool  # o arquivo do acervo ainda tem o SHA-256


@dataclass(frozen=True)
class Linhagem:
    ano: str  # o ano do Parquet, ou o nome da tabela
    versao_do_codigo: str | None  # None: manifesto gravado antes da exigência 13
    base_confere: bool  # o Parquet do ano ainda tem o hash anotado no manifesto
    origens: list[Origem]

    @property
    def completa(self) -> bool:
        return (
            self.versao_do_codigo is not None
            and self.base_confere
            and bool(self.origens)
            and all(
                o.baixado_em is not None and o.original_confere for o in self.origens
            )
        )


def _ano_da_linha(linha: pd.Series) -> str:
    fim = linha.get("fim")
    return SEM_DATA if fim is None or pd.isna(fim) else str(pd.Timestamp(fim).year)


def _origem(conexao: sa.Connection, url: str, sha256: str) -> Origem:
    coleta = conexao.execute(
        sa.select(coletas.c.baixado_em, coletas.c.caminho_do_original)
        .where(coletas.c.sha256 == sha256, coletas.c.situacao == "ok")
        .order_by(coletas.c.baixado_em)
        .limit(1)
    ).first()
    if coleta is None:
        return Origem(url, sha256, None, None, False)
    caminho = coleta.caminho_do_original
    confere = caminho is not None and acervo.confere_com_o_registro(caminho, sha256)
    return Origem(url, sha256, coleta.baixado_em, caminho, confere)


def _linhagem(
    conexao: sa.Connection, nome: str, manifesto: Path, confere: bool
) -> Linhagem:
    anotado = json.loads(manifesto.read_text(encoding="utf-8"))
    return Linhagem(
        ano=nome,
        versao_do_codigo=anotado.get("versao_do_codigo"),
        base_confere=confere,
        origens=[
            _origem(conexao, o["url"], o["sha256"]) for o in anotado.get("origens", [])
        ],
    )


def linhagem_da_linha(
    conexao: sa.Connection, pasta: Path, linha: pd.Series
) -> Linhagem:
    """O caminho de uma linha da base "por ano" até os originais, a coleta e a versão do código."""
    ano = _ano_da_linha(linha)
    return _linhagem(
        conexao, ano, pasta / f"{ano}.json", conferir_pasta(pasta).get(ano, False)
    )


def linhagem_da_tabela(conexao: sa.Connection, arquivo: Path) -> Linhagem:
    """O mesmo para uma tabela gravada por `base/parquet.py::gravar_tabela` (todas as linhas)."""
    return _linhagem(
        conexao, arquivo.stem, arquivo.with_suffix(".json"), conferir_tabela(arquivo)
    )
