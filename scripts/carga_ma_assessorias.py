"""Carga dos fatos dos posts das assessorias de M&A (ADR 0082, série 5 do plano de M&A, passo 2;
`base/ma_assessorias.py`).

    python -m scripts.carga_ma_assessorias                     (a base do acervo)
    python -m scripts.carga_ma_assessorias --base <pasta>

Lê as páginas que o arquivista já guardou (fonte `assessoria-<id>`; não baixa nada) e grava uma linha
por negócio em `<base>/ma/assessorias/<id>.parquet`, com manifesto e versões (`gravar_com_versoes`:
com as mesmas páginas, nada é lido de novo). No fim, imprime quantos negócios saíram com alvo e
comprador, com tipo e sem tipo, para a conferência. Recusa rodar sem a versão do código (exigência 13
da ADR 0055). O esquema `ma` no banco só vem na série 1 do plano: até lá, Parquet no servidor de casa.
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from base import ma_assessorias
from base.arquivo.assessorias import ASSESSORIAS, Assessoria
from base.parquet import GRAVADO, gravar_com_versoes, ler_tabela
from src import acervo
from src.banco.coletas import originais_mais_recentes
from src.banco.conexao import criar_engine, migrar_para
from src.configuracao import url_do_banco
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_ma_assessorias")
ORDEM = ["assessoria", "url"]


def montar(conexao: sa.Connection, assessoria: Assessoria) -> pd.DataFrame:
    linhas = []
    for guardada in originais_mais_recentes(conexao, f"assessoria-{assessoria.id}"):
        conteudo = acervo.ler_original(guardada.caminho_do_original)
        if conteudo is None:
            raise FileNotFoundError(f"original fora do acervo: {guardada.url}")
        linhas.append(
            ma_assessorias.extrair(
                conteudo,
                guardada.url,
                guardada.sha256,
                guardada.baixado_em,
                assessoria.id,
            )
        )
    return ma_assessorias.tabela(linhas)


def resumo(tabela: pd.DataFrame) -> str:
    """Os números da conferência: quantos negócios, com alvo e comprador, com tipo e sem."""
    com_partes = (tabela["alvo"].notna() & tabela["comprador"].notna()).sum()
    sem_tipo = (tabela["tipo"] == ma_assessorias.SEM_TIPO).sum()
    por_tipo = ", ".join(f"{t} {n}" for t, n in tabela["tipo"].value_counts().items())
    return (
        f"{len(tabela)} negócios; {com_partes} com alvo e comprador; "
        f"{len(tabela) - sem_tipo} com tipo, {sem_tipo} {ma_assessorias.SEM_TIPO} ({por_tipo})"
    )


def carregar(conexao: sa.Connection, base: Path) -> None:
    for assessoria in ASSESSORIAS:
        fonte = f"assessoria-{assessoria.id}"
        guardadas = originais_mais_recentes(conexao, fonte)
        if not guardadas:
            log.warning("%s: nenhuma página guardada", fonte)
            continue
        origens = [{"url": g.url, "sha256": g.sha256} for g in guardadas]
        destino = base / "ma" / "assessorias" / assessoria.id
        resultado = gravar_com_versoes(
            lambda a=assessoria: montar(conexao, a), destino, origens, ORDEM
        )
        log.info("%s: %s", fonte, resultado)
        if resultado == GRAVADO:
            print(f"{fonte}: {resumo(ler_tabela(destino.with_suffix('.parquet')))}")


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--base", type=Path, default=None)
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    raiz = acervo.pasta_do_acervo()
    base = opcoes.base or (None if raiz is None else raiz / "base")
    if base is None:
        argumentos.error("acervo desligado: informe --base")
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        with motor.connect() as conexao:
            carregar(conexao, base)
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
