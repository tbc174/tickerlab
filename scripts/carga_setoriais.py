"""Carga das fontes setoriais para a base (série 4 da base de ML, PRs 4 e 5; `base/setoriais/`): ANAC,
ANP, ONS, ANEEL (SAMP), Anatel, ANS e SUSEP, no formato de cada fonte, com a data desde quando cada número era
público.

    python -m scripts.carga_setoriais                     (a base do acervo)
    python -m scripts.carga_setoriais --base <pasta>      (a pasta com empresa_serie/)

Lê os originais que o arquivista já guardou (não baixa nada) e grava, um ano por vez e uma fonte por
vez, `<base>/setoriais/<fonte>/<ano>.parquet` com manifesto e versões (`gravar_com_versoes`: com as
mesmas origens, o ano é pulado sem ler de novo). Os buracos da ligação pela B13 (o código da fonte sem
empresa, com o volume) vão para `<base>/setoriais/buracos.parquet`. Recusa rodar sem a versão do
código (exigência 13 da ADR 0055).

ANEEL, Anatel, ANS e SUSEP republicam o arquivo inteiro e revisam meses passados (PRs 5 e 5b): cada baixada guardada
de um endereço entra como uma coleta (`base/setoriais/revisoes.py`), e a tabela guarda uma linha por
valor diferente, com o dia em que a revisão foi vista. Um Parquet por arquivo da fonte: o SAMP por ano
(`aneel/<ano>`), a Anatel por CSV (`anatel/<nome do CSV>`), a ANS e a SUSEP por ano da competência
(`ans/<ano>`, `susep/<ano>`).
"""

import argparse
import json
import logging
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pandas as pd
import sqlalchemy as sa

from base.commodities import cftc_cot
from base.parquet import gravar_com_versoes, gravar_se_mudou
from base.setoriais import anac, anatel, aneel, anp, ans, ligacao, ons, revisoes, susep
from src import acervo
from src.banco.coletas import coletas_guardadas, originais_mais_recentes
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
    cftc_cot.FONTE: ("cftc", ["relatorio", "contrato"], "relatorio"),
}  # fmt: skip
# fonte → (coluna da chave na tabela, coluna do volume) para os buracos da ligação
CHAVES = {
    anac.FONTE: ("empresa_sigla", "passageiros_pagos"),
    anp.FONTE: ("agente", "quantidade"),
}
ANO_DO_SAMP = re.compile(r"samp-(\d{4})\.parquet$")
CONSUMIDORES = (
    "número de consumidores"  # o volume do SAMP nos buracos (a ANEEL muda a caixa)
)


class Revisada(NamedTuple):
    """Uma fonte que revisa meses passados: onde grava, a chave, os carimbos, a ligação e o volume."""

    pasta: str
    chave: list[str]
    carimbos: tuple[str, ...]
    destino: Callable[
        [str], str | None
    ]  # o nome do Parquet de cada endereço (None: fica fora)
    ler: Callable[[bytes, str], pd.DataFrame]  # (conteúdo, endereço)
    fonte_da_ligacao: str
    coluna_da_ligacao: str
    volume: Callable[[pd.DataFrame], pd.Series]
    por_ano: bool = (
        False  # um arquivo com muitos anos: um Parquet por ano da competência
    )


def _ano_do_samp(url: str) -> str | None:
    return achado.group(1) if (achado := ANO_DO_SAMP.search(url)) else None


def _csv_da_anatel(url: str) -> str | None:
    arquivo = url.rpartition("#")[2]
    return arquivo.removesuffix(".csv") if arquivo.endswith("_Colunas.csv") else None


def _consumidores(tabela: pd.DataFrame) -> pd.Series:
    sao = tabela["detalhe_do_mercado"].fillna("").str.lower().eq(CONSUMIDORES)
    return tabela["valor"].where(sao, 0.0)


REVISADAS = {
    aneel.FONTE: Revisada(
        "aneel", aneel.CHAVE, aneel.CARIMBOS, _ano_do_samp, lambda c, _: aneel.ler(c),
        aneel.FONTE, "cnpj", _consumidores,
    ),
    anatel.FONTE: Revisada(
        "anatel", anatel.CHAVE, anatel.CARIMBOS, _csv_da_anatel,
        lambda c, url: anatel.ler(c, url.rpartition("#")[2]),
        anatel.FONTE, "cnpj", lambda t: t["acessos"],
    ),
    ans.FONTE: Revisada(
        "ans", ans.CHAVE, ans.CARIMBOS, lambda url: "ans" if url == ans.URL else None,
        lambda c, _: ans.ler(c), ans.FONTE_DA_LIGACAO, "cd_operadora",
        lambda t: t["beneficiarios"], por_ano=True,
    ),
    susep.FONTE: Revisada(
        "susep", susep.CHAVE, (), lambda url: "susep" if url.endswith("#" + susep.ARQUIVO) else None,
        lambda c, _: susep.ler(c), susep.FONTE, "coenti", lambda t: t["premio_direto"],
        por_ano=True,
    ),
}  # fmt: skip


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
    if fonte == cftc_cot.FONTE and linha.url.endswith(".zip"):
        return cftc_cot.ler_disaggregated
    return None


def carregar_fonte(conexao: sa.Connection, fonte: str, base: Path) -> pd.DataFrame:
    """Grava os anos da fonte e devolve a tabela inteira (para os buracos; vazia no ONS, que vai ano a
    ano: o ano de 2023 inteiro passa de 5 milhões de linhas)."""
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
    if not linhas:  # fonte ainda sem original no acervo
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


def _empresa_serie(base: Path) -> pd.DataFrame | None:
    arquivo = base / "empresa_serie" / "empresa_serie.parquet"
    if not arquivo.exists():
        log.warning("sem a empresa_serie (B13): buracos não montados")
        return None
    return pd.read_parquet(arquivo)


def buracos_da_fonte(
    tabela: pd.DataFrame, fonte: str, empresa_serie: pd.DataFrame | None
) -> pd.DataFrame | None:
    """Os buracos de uma fonte, montados logo depois dela: a tabela inteira não fica na memória."""
    if empresa_serie is None or fonte not in CHAVES or tabela.empty:
        return None
    coluna, volume = CHAVES[fonte]
    return ligacao.buracos(tabela, coluna, volume, fonte, empresa_serie)


def _coletas(
    conexao: sa.Connection, url: str, revisada: Revisada
) -> tuple[list[dict[str, str]], Callable[[], pd.DataFrame]]:
    """As origens (endereço e SHA-256 de cada baixada) e a função que lê e junta as coletas."""
    guardadas = coletas_guardadas(conexao, url)
    origens = [{"url": url, "sha256": sha256} for _, sha256, _ in guardadas]

    def montar() -> pd.DataFrame:
        coletas = [
            (
                pd.Timestamp(dia).tz_localize(None).normalize(),
                revisada.ler(conteudo, url),
            )
            for dia, _, conteudo in guardadas
        ]
        return revisoes.juntar_coletas(coletas, revisada.chave, revisada.carimbos)

    return origens, montar


def _buracos_da_revisada(
    tabela: pd.DataFrame,
    fonte: str,
    revisada: Revisada,
    empresa_serie: pd.DataFrame | None,
) -> pd.DataFrame | None:
    """Os buracos de um arquivo, sobre o valor mais novo de cada chave (a revisão não soma duas vezes)."""
    if empresa_serie is None or tabela.empty:
        return None
    atual = revisoes.como_era_em(tabela, pd.Timestamp.max, revisada.chave)
    atual = atual.assign(volume=revisada.volume(atual))
    buracos = ligacao.buracos(
        atual,
        revisada.coluna_da_ligacao,
        "volume",
        revisada.fonte_da_ligacao,
        empresa_serie,
    )
    return buracos.assign(fonte=fonte)


def _gravar_arquivo(
    montar: Callable[[], pd.DataFrame],
    destino: Path,
    origens: list[dict[str, str]],
    chave: list[str],
) -> tuple[str, pd.DataFrame]:
    """Grava um arquivo da fonte e devolve a tabela (lida do disco quando não mudou)."""
    montada: list[pd.DataFrame] = []

    def montar_e_guardar() -> pd.DataFrame:
        montada.append(montar())
        return montada[0]

    resultado = gravar_com_versoes(montar_e_guardar, destino, origens, chave)
    tabela = montada[0] if montada else pd.read_parquet(destino.with_suffix(".parquet"))
    return resultado, tabela


def _gravar_por_ano(
    montar: Callable[[], pd.DataFrame],
    pasta: Path,
    origens: list[dict[str, str]],
    chave: list[str],
) -> pd.DataFrame:
    """Um arquivo da fonte com muitos anos (a ANS): um Parquet por ano da competência."""
    tabela = montar()
    for ano, do_ano in tabela.groupby(tabela["competencia"].dt.year):
        resultado = gravar_com_versoes(
            lambda t=do_ano: t.reset_index(drop=True), pasta / str(ano), origens, chave
        )
        log.info("%s %s: %s", pasta.name, ano, resultado)
    return tabela


def carregar_revisada(
    conexao: sa.Connection, fonte: str, base: Path, empresa_serie: pd.DataFrame | None
) -> pd.DataFrame | None:
    """Grava cada arquivo da fonte com as revisões e devolve os buracos da ligação, somados."""
    revisada = REVISADAS[fonte]
    urls = sorted(
        {
            lin.url
            for lin in originais_mais_recentes(conexao, fonte)
            if revisada.destino(lin.url)
        }
    )
    pasta = base / PASTA / revisada.pasta
    partes = []
    for url in urls:
        origens, montar = _coletas(conexao, url, revisada)
        if revisada.por_ano:
            tabela = _gravar_por_ano(montar, pasta, origens, revisada.chave)
        else:
            nome = str(revisada.destino(url))
            resultado, tabela = _gravar_arquivo(
                montar, pasta / nome, origens, revisada.chave
            )
            log.info("%s %s: %s", fonte, nome, resultado)
        if (
            buracos := _buracos_da_revisada(tabela, fonte, revisada, empresa_serie)
        ) is not None:
            partes.append(buracos)
        del tabela
    if not partes:
        return None
    juntos = pd.concat(partes, ignore_index=True).groupby(
        ["fonte", "chave"], as_index=False
    )
    return (
        juntos.agg(
            valor=("valor", "sum"),
            primeira=("primeira", "min"),
            ultima=("ultima", "max"),
        )
        .sort_values("valor", ascending=False)
        .reset_index(drop=True)
    )


def gravar_buracos(partes: list[pd.DataFrame], base: Path) -> None:
    if not partes:
        return
    arquivo = base / "empresa_serie" / "empresa_serie.parquet"
    manifesto = json.loads(arquivo.with_suffix(".json").read_text(encoding="utf-8"))
    origens = [
        {
            "url": "empresa_serie/empresa_serie.parquet",
            "sha256": manifesto["sha256_da_tabela"],
        }
    ]
    buracos = pd.concat(partes, ignore_index=True)
    # pelo conteúdo, não pelas origens: a B13 igual com uma fonte nova (ou um mês novo) muda os
    # buracos, e com as mesmas origens eles ficavam como antes (achado na carga do PR 5, 16/10/2026).
    # É uma lista de trabalho refeita a cada carga: sem versões guardadas
    resultado = gravar_se_mudou(
        buracos, base / PASTA / "buracos", origens, ["fonte", "chave"], versoes=False
    )
    log.info("buracos da ligação: %s (%s chaves)", resultado, len(buracos))


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--base", type=Path, default=None)
    argumentos.add_argument(
        "--fonte",
        choices=list(TABELAS),
        help="carrega só esta fonte (o café usa cftc-cot-disaggregated); sem ela, todas",
    )
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
    empresa_serie = _empresa_serie(base)
    partes = []
    try:
        with motor.connect() as conexao:
            for fonte in [opcoes.fonte] if opcoes.fonte else TABELAS:
                tabela = carregar_fonte(conexao, fonte, base)
                if (
                    buracos := buracos_da_fonte(tabela, fonte, empresa_serie)
                ) is not None:
                    partes.append(buracos)
                del tabela
            revisadas = (
                carregar_revisada(conexao, fonte, base, empresa_serie)
                for fonte in ([] if opcoes.fonte else REVISADAS)
            )
            partes.extend(b for b in revisadas if b is not None)
    finally:
        motor.dispose()
    if (
        not opcoes.fonte
    ):  # a lista de buracos é de todas as fontes: parcial, apagaria as outras
        gravar_buracos(partes, base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
