"""Base histórica (série B1): as tabelas da CVM de todos os anos, lidas dos originais do acervo.

O arquivista (`base/arquivo/`) guarda os arquivos anuais da CVM desde 2003 (`cvm-hist-*`). Aqui cada
arquivo é lido com o **mesmo leitor do app** (`src/eventos.ler_ipe`, `src/negociacoes_cvm.ler_vlmo`,
`base/fre.py`) e vira `<pasta>/<tabela>/<ano>.parquet`. O banco de produção continua com poucos
anos (ADR 0031): o histórico longo é da base de ML, no servidor de casa.

Cada linha leva a **origem**: o SHA-256 do arquivo da CVM de onde saiu, quando ele foi coletado e quando
a tabela foi montada. Nada é baixado: sem original no acervo, o ano não entra.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from base import fre, rotulos
from src import acervo
from src.banco.coletas import originais_mais_recentes
from src.eventos import ler_ipe
from src.negociacoes_cvm import ler_vlmo

ANO_NO_NOME = re.compile(r"_(\d{4})\.(?:zip|csv)$")


@dataclass(frozen=True)
class Tabela:
    fonte: str  # a fonte do arquivista que guarda os arquivos anuais
    ler: Callable[[bytes], pd.DataFrame]


TABELAS = {
    "eventos": Tabela("cvm-hist-ipe", ler_ipe),  # desde 2003
    "negociacoes": Tabela("cvm-hist-vlmo", ler_vlmo),  # desde 2018
    "proventos": Tabela(
        "cvm-hist-fre", fre.ler_proventos
    ),  # 2010 a 2022 (o FRE novo não tem a tabela)
    "eventos_de_capital": Tabela("cvm-hist-fre", fre.ler_eventos_de_capital),
    # série B2: rótulos de recuperação judicial, falência e liquidação (base/rotulos.py)
    "insolvencia": Tabela("cvm-hist-ipe", rotulos.ler_insolvencia_do_ipe),
}


class ArquivoIlegivel(Exception):
    """Um original do acervo não abre com o leitor da tabela (formato mudou ou arquivo quebrado)."""


def ano_do_arquivo(url: str) -> int | None:
    """2024 em `..._2024.zip`; None para arquivos mensais (`_202609.zip`) ou sem ano."""
    achado = ANO_NO_NOME.search(url)
    return int(achado.group(1)) if achado else None


def _gravar(tabela: pd.DataFrame, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".parcial")
    tabela.to_parquet(parcial, index=False)
    parcial.replace(destino)


def montar(
    nome: str, conexao: sa.Connection, pasta: Path, agora: datetime
) -> dict[int, int]:
    """Monta `<pasta>/<nome>/<ano>.parquet` para cada arquivo anual guardado; devolve linhas por ano.

    Levanta `KeyError` (tabela desconhecida) e `ArquivoIlegivel` (original que não abre: nada é
    gravado para aquele ano, e a falha aparece em vez de virar um ano vazio).
    """
    tabela = TABELAS[nome]
    linhas_por_ano: dict[int, int] = {}
    for original in originais_mais_recentes(conexao, tabela.fonte):
        ano = ano_do_arquivo(original.url)
        conteudo = acervo.ler_original(original.caminho_do_original)
        if ano is None or conteudo is None:
            continue
        try:
            dados = tabela.ler(conteudo)
        except Exception as erro:  # zip quebrado, CSV com formato novo
            raise ArquivoIlegivel(
                f"{nome} {ano}: {type(erro).__name__}: {erro}"
            ) from erro
        if dados.empty:
            linhas_por_ano[ano] = 0
            continue
        dados = dados.assign(
            ano_do_arquivo=ano,
            origem_sha256=original.sha256,
            origem_coletada_em=pd.Timestamp(original.baixado_em).isoformat(),
            montado_em=agora.isoformat(),
        )
        _gravar(dados, pasta / nome / f"{ano}.parquet")
        linhas_por_ano[ano] = len(dados)
    return linhas_por_ano
