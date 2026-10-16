"""Carga das fontes setoriais para a base (série 4 da base de ML, PR 4; `base/setoriais/`): ANAC, ANP e
ONS, no formato de cada fonte, com a data desde quando cada número era público.

    python -m scripts.carga_setoriais                     (a base do acervo)
    python -m scripts.carga_setoriais --base <pasta>      (a pasta com empresa_serie/)

Lê os originais que o arquivista já guardou (não baixa nada) e grava, um ano por vez e uma fonte por
vez, `<base>/setoriais/<fonte>/<ano>.parquet` com manifesto e versões (`gravar_com_versoes`: com as
mesmas origens, o ano é pulado sem ler de novo). Os buracos da ligação pela B13 (o código da fonte sem
empresa, com o volume) vão para `<base>/setoriais/buracos.parquet`. Recusa rodar sem a versão do
código (exigência 13 da ADR 0055).
"""

import argparse
import json
import logging
import re
import sys
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from base.parquet import gravar_com_versoes
from base.setoriais import anac, anp, ligacao, ons
from src import acervo
from src.banco.coletas import originais_mais_recentes
from src.banco.conexao import criar_engine, migrar_para
from src.configuracao import url_do_banco
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_setoriais")
PASTA = "setoriais"
ANO_DO_ONS = re.compile(r"_(\d{4})(?:_\d{2})?\.parquet$")
GRUPO_DA_ANP = re.compile(r"/(liquidos|glp|aviacao)\.zip$")
# fonte → (pasta, colunas de ordem, coluna de tempo)
TABELAS = {
    anac.FONTE: ("anac", ["competencia", "empresa_sigla", "aeroporto_de_origem_sigla",
                          "aeroporto_de_destino_sigla"], "competencia"),
    anp.FONTE: ("anp", ["competencia", "grupo", "agente", "codigo_do_produto"], "competencia"),
    ons.FONTE: ("ons", ["instante", "id_ons"], "instante"),
}  # fmt: skip
# fonte → (coluna da chave na tabela, coluna do volume) para os buracos da ligação
CHAVES = {
    anac.FONTE: ("empresa_sigla", "passageiros_pagos"),
    anp.FONTE: ("agente", "quantidade"),
}


def _origem(linha: sa.Row) -> dict[str, str]:
    return {"url": linha.url, "sha256": linha.sha256}


def _ler(linha: sa.Row, ler: Callable[[bytes], pd.DataFrame]) -> pd.DataFrame:
    conteudo = acervo.ler_original(linha.caminho_do_original)
    if conteudo is None:
        raise FileNotFoundError(f"original fora do acervo: {linha.url}")
    return ler(conteudo)


def _leitor(fonte: str, linha: sa.Row) -> Callable[[bytes], pd.DataFrame] | None:
    if fonte == anac.FONTE and linha.url.endswith(".csv"):
        return anac.ler
    if fonte == anp.FONTE and (grupo := GRUPO_DA_ANP.search(linha.url)):
        return lambda conteudo: anp.ler(conteudo, grupo.group(1))
    if fonte == ons.FONTE and linha.url.endswith(".parquet"):
        return ons.ler
    return None


def carregar_fonte(conexao: sa.Connection, fonte: str, base: Path) -> pd.DataFrame:
    """Grava os anos da fonte e devolve a tabela inteira (para os buracos; vazia no ONS)."""
    pasta, ordem, tempo = TABELAS[fonte]
    linhas = [
        (linha, leitor)
        for linha in originais_mais_recentes(conexao, fonte)
        if (leitor := _leitor(fonte, linha)) is not None
    ]
    if fonte == ons.FONTE:  # um arquivo por ano ou por mês: lê só os do ano
        anos: dict[str, list] = {}
        for linha, leitor in linhas:
            if achado := ANO_DO_ONS.search(linha.url):
                anos.setdefault(achado.group(1), []).append((linha, leitor))
        for ano, do_ano in sorted(anos.items()):
            resultado = gravar_com_versoes(
                lambda d=do_ano: pd.concat([_ler(lin, ler) for lin, ler in d], ignore_index=True),
                base / PASTA / pasta / ano, [_origem(lin) for lin, _ in do_ano], ordem,
            )  # fmt: skip
            log.info("%s %s: %s", fonte, ano, resultado)
        return pd.DataFrame()
    tabela = pd.concat([_ler(lin, ler) for lin, ler in linhas], ignore_index=True)
    origens = [_origem(lin) for lin, _ in linhas]
    for ano, do_ano in tabela.groupby(tabela[tempo].dt.year):
        resultado = gravar_com_versoes(
            lambda t=do_ano: t.reset_index(drop=True), base / PASTA / pasta / str(ano),
            origens, ordem,
        )  # fmt: skip
        log.info("%s %s: %s", fonte, ano, resultado)
    return tabela


def gravar_buracos(tabelas: dict[str, pd.DataFrame], base: Path) -> None:
    arquivo = base / "empresa_serie" / "empresa_serie.parquet"
    if not arquivo.exists():
        log.warning("sem a empresa_serie (B13): buracos não montados")
        return
    empresa_serie = pd.read_parquet(arquivo)
    partes = [
        ligacao.buracos(tabelas[fonte], coluna, volume, fonte, empresa_serie)
        for fonte, (coluna, volume) in CHAVES.items()
        if not tabelas.get(fonte, pd.DataFrame()).empty
    ]
    if not partes:
        return
    manifesto = json.loads(arquivo.with_suffix(".json").read_text(encoding="utf-8"))
    origens = [
        {
            "url": "empresa_serie/empresa_serie.parquet",
            "sha256": manifesto["sha256_da_tabela"],
        }
    ]
    buracos = pd.concat(partes, ignore_index=True)
    resultado = gravar_com_versoes(
        lambda: buracos, base / PASTA / "buracos", origens, ["fonte", "chave"]
    )
    log.info("buracos da ligação: %s (%s chaves)", resultado, len(buracos))


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
            tabelas = {fonte: carregar_fonte(conexao, fonte, base) for fonte in TABELAS}
    finally:
        motor.dispose()
    gravar_buracos(tabelas, base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
