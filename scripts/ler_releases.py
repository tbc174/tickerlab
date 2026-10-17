"""Os press-releases de resultado das companhias abertas (vitrine, ideia 2; plano de 17/10/2026).

    python -m scripts.ler_releases medir [--base PASTA] [--desde 2024]

`medir` (sem API, sem gasto) conta os press-releases do IPE guardado no acervo por ano de entrega e
quantos têm ITR ou DFP do mesmo período em `demonstracoes_como_era`. Os outros passos (baixar,
estimar, piloto, enviar, conferir) entram nos PRs 2 e 3 do plano.
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from base import releases
from base.ratings import FONTE_DO_IPE, ler_ipe_bruto
from src import acervo
from src.banco.coletas import originais_mais_recentes
from src.banco.conexao import criar_engine, migrar_para
from src.configuracao import url_do_banco

log = logging.getLogger("tickerlab.ler_releases")
PRIMEIRO_ANO = 2024


def _so_digitos(cnpj: pd.Series) -> pd.Series:
    return cnpj.astype(str).str.replace(r"\D", "", regex=True)


def medir(achados: pd.DataFrame, demonstracoes: pd.DataFrame) -> pd.DataFrame:
    """Por ano de entrega: releases, empresas e quantos têm ITR/DFP do mesmo período (CNPJ e data)."""
    entregues = set(
        zip(
            _so_digitos(demonstracoes["cnpj"]),
            pd.to_datetime(demonstracoes["referencia"]),
            strict=True,
        )
    )
    chaves = zip(_so_digitos(achados["cnpj"]), achados["referencia"], strict=True)
    tem = pd.Series([c in entregues for c in chaves], index=achados.index, dtype=bool)
    por_ano = achados.assign(
        com_itr_dfp=tem, ano=achados["data_entrega"].dt.year
    ).groupby("ano")
    medida = por_ano.agg(
        releases=("protocolo", "size"),
        empresas=("cnpj", "nunique"),
        com_itr_dfp=("com_itr_dfp", "sum"),
    ).reset_index()
    medida["percentual_com_itr_dfp"] = (
        100 * medida["com_itr_dfp"] / medida["releases"]
    ).round(1)
    return medida


def _releases_do_acervo(desde: int) -> pd.DataFrame:
    motor = criar_engine(url_do_banco())
    try:
        with motor.connect() as conexao:
            anuais = [
                o
                for o in originais_mais_recentes(conexao, FONTE_DO_IPE)
                if "ipe_cia_aberta_" in o.url
            ]
    finally:
        motor.dispose()
    partes = []
    for original in anuais:
        conteudo = acervo.ler_original(original.caminho_do_original)
        if conteudo:
            partes.append(releases.releases_de_resultado(ler_ipe_bruto(conteudo)))
    if not partes:
        return pd.DataFrame(columns=list(releases.COLUNAS))
    todos = pd.concat(partes, ignore_index=True).drop_duplicates("protocolo")
    return todos[todos["data_entrega"].dt.year >= desde].reset_index(drop=True)


def _demonstracoes(pasta_da_base: Path) -> pd.DataFrame:
    arquivos = sorted((pasta_da_base / "demonstracoes").glob("*.parquet"))
    colunas = ["cnpj", "documento", "referencia"]
    return pd.concat(
        [pd.read_parquet(a, columns=colunas).drop_duplicates() for a in arquivos],
        ignore_index=True,
    ).drop_duplicates()


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    sub = argumentos.add_subparsers(dest="passo", required=True)
    medir_ = sub.add_parser(
        "medir", help="conta os releases e os que têm ITR/DFP (sem API)"
    )
    medir_.add_argument("--base", type=Path, default=None)
    medir_.add_argument("--desde", type=int, default=PRIMEIRO_ANO)
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    migrar_para("head", url=url_do_banco())
    base = (
        opcoes.base
        or (acervo.pasta_do_acervo() or Path("dados_locais/acervo")) / "base"
    )
    achados = _releases_do_acervo(opcoes.desde)
    medida = medir(achados, _demonstracoes(base))
    print(medida.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
