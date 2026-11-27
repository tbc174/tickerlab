"""Coleta manual das edições 2022 a 2025 do Censo Escolar, só escolas privadas.

    python -m scripts.carga_censo_escolar --ano 2024
    python -m scripts.carga_censo_escolar --ano 2022 --ano 2023 --ano 2024 --ano 2025

ZIP temporário, MD5 dos CSVs usados, lista fechada de colunas e CNPJ com DV.
Parquet e manifesto em <acervo>/base/inep_censo_escolar/<ano>, versões .vN.
Não agenda coleta nem roda download no CI. Veja docs/coleta-censo-escolar.md.

Roda: manual pela Diretoria na máquina de casa; python -m scripts.carga_censo_escolar --ano 2024.
"""

import argparse
import hashlib
import logging
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

from base import inep_censo_escolar as censo
from base.arquivo.cliente_http import ClienteHttp
from base.arquivo.coleta import Cliente, FreioDeDisco, conferir_freio, espaco_do_disco
from base.parquet import (
    IGUAL,
    LINHAGEM,
    conferir_tabela,
    gravar_com_versoes,
    ler_tabela,
)
from src import acervo
from src.versao_do_codigo import exigir_versao_do_codigo, versao_do_codigo

log = logging.getLogger(__name__)


def carregar_edicao(ano: int, pasta: Path, quando: datetime, cliente: Cliente) -> str:
    """Baixa e grava uma edição com manifesto e versões."""
    url = censo.url_da_edicao(ano)
    pasta.mkdir(parents=True, exist_ok=True)
    conferir_freio(*espaco_do_disco(pasta))
    # O ZIP pode conter nomes e contatos: só existe temporariamente, nunca entra
    # no acervo bruto nem é extraído no disco. O manifesto guarda seu hash real.
    with tempfile.TemporaryDirectory(prefix="inep-", dir=pasta) as temporaria:
        zip_temporario = Path(temporaria) / "edicao.zip"
        cliente.baixar(url, zip_temporario)
        tabela = censo.ler_edicao(zip_temporario, ano)
        with zip_temporario.open("rb") as entrada:
            sha256 = hashlib.file_digest(entrada, "sha256").hexdigest()
    if tabela.empty:
        raise ValueError(
            "Censo Escolar: nenhuma escola privada com CNPJ válido; edição recusada"
        )
    tabela["origem_sha256"] = sha256
    tabela["origem_coletada_em"] = quando
    tabela["disponivel_em"] = quando.date()
    tabela["montado_em"] = quando
    tabela["versao_do_codigo"] = versao_do_codigo()
    return _gravar_edicao(tabela, pasta / censo.TABELA / str(ano), url, sha256)


def _gravar_edicao(tabela: pd.DataFrame, destino: Path, url: str, sha256: str) -> str:
    arquivo = destino.with_suffix(".parquet")
    if arquivo.exists() and conferir_tabela(arquivo):
        anterior = ler_tabela(arquivo)
        carimbos = [*LINHAGEM, "disponivel_em"]
        if anterior.drop(columns=carimbos).equals(tabela.drop(columns=carimbos)):
            return IGUAL
    # Uma edição é um retrato inteiro. Até revisão que só acrescenta escolas
    # guarda a anterior, pois a disponibilidade da edição também muda.
    return gravar_com_versoes(
        lambda: tabela,
        destino,
        [{"url": url, "sha256": sha256}],
        list(censo.CHAVE),
        forcar=True,
    )


def main(argv: list[str] | None = None) -> int:
    """Carga explícita por edição; falha sai com código 1 e preserva o publicado."""
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument(
        "--ano", type=int, choices=censo.ANOS, action="append", required=True
    )
    argumentos.add_argument("--pasta", type=Path)
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    pasta = opcoes.pasta or (acervo.pasta_do_acervo() or acervo.PASTA_PADRAO) / "base"
    cliente = ClienteHttp()
    try:
        for ano in dict.fromkeys(opcoes.ano):
            try:
                resultado = carregar_edicao(ano, pasta, datetime.now(UTC), cliente)
            except (
                ValueError,
                OSError,
                zipfile.BadZipFile,
                requests.RequestException,
                FreioDeDisco,
            ) as erro:
                # Não imprimir conteúdo da fonte nem a mensagem do parser (pode conter célula).
                log.error(
                    "Censo Escolar %s: coleta recusada (%s)", ano, type(erro).__name__
                )
                return 1
            log.info("Censo Escolar %s: %s", ano, resultado)
    finally:
        cliente.sessao.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
