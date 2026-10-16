"""Monta os painéis dos fundos por emissor e por empresa, a cobertura e o relatório de buracos (série 3
da base de ML, PR 5; `base/ligacoes.py`).

    python -m scripts.montar_painel_dos_fundos                 (a base do acervo)
    python -m scripts.montar_painel_dos_fundos --base <pasta>   (a pasta com cda/ e fca/)

Lê as tabelas que a base já tem (`cda/<ano>.parquet`, sem as versões `.v<N>`; `fca/emissores.parquet`)
e as tabelas conferidas (`base/conferidas/emissores_antigos.csv` e `emissores_sem_ligacao.csv`, com o
motivo de quem fica sem empresa), um ano por vez, e grava em
`fundos/`: `painel_emissor/<ano>`, `painel_empresa/<ano>`, `cobertura` e `buracos`, com manifesto e
versões (`base/parquet.py::gravar_com_versoes`). As origens de cada tabela são as tabelas de entrada
(com o SHA-256 do conteúdo anotado no manifesto delas) e a tabela conferida. Não baixa nada. Recusa
rodar sem a versão do código (exigência 13 da ADR 0055).
"""

import argparse
import hashlib
import json
import logging
import re
import sys
from pathlib import Path

import pandas as pd

from base import ligacoes
from base.parquet import gravar_com_versoes, ler_tabela
from src import acervo
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.painel_dos_fundos")
ANO = re.compile(r"\d{4}")
META_DE_COBERTURA = 0.95  # decisão do Tiago em 14/10/2026
COLUNAS_DO_CDA = [
    "competencia", "cnpj_fundo", "tipo", "emissor", "descricao", "valor", "quantidade", "compras",
    "vendas", "disponivel_em",
]  # fmt: skip


def _origem_de_tabela(arquivo: Path, raiz: Path) -> dict[str, str]:
    manifesto = json.loads(arquivo.with_suffix(".json").read_text(encoding="utf-8"))
    return {
        "url": arquivo.relative_to(raiz).as_posix(),
        "sha256": manifesto["sha256_da_tabela"],
    }


def _origem_da_conferida(arquivo: Path) -> dict[str, str]:
    return {
        "url": f"base/conferidas/{arquivo.name}",
        "sha256": hashlib.sha256(arquivo.read_bytes()).hexdigest(),
    }


PASTA_DO_BLOCO_8 = "cda_bloco_8"  # a mesma de `scripts/carga_cda.py`


def anos_do_cda(raiz: Path) -> list[Path]:
    """Os Parquet de ano do CDA (`2008.parquet`), sem as versões anteriores (`2008.v1.parquet`)."""
    return sorted(p for p in (raiz / "cda").glob("*.parquet") if ANO.fullmatch(p.stem))


def _juntar_buracos(partes: list[pd.DataFrame]) -> pd.DataFrame:
    tabela = pd.concat(partes, ignore_index=True)
    return (
        tabela.groupby("emissor")
        .agg(valor=("valor", "sum"), primeira=("primeira", "min"), ultima=("ultima", "max"),
             descricao=("descricao", "first"), motivo=("motivo", "first"))
        .sort_values("valor", ascending=False)
        .reset_index()
    )  # fmt: skip


def montar(raiz: Path) -> int:
    """Monta tudo; devolve quantos anos entraram."""
    emissores = raiz / "fca" / "emissores.parquet"
    ligacao = ligacoes.ligacao_dos_emissores(
        ler_tabela(emissores), ligacoes.tabela_conferida()
    )
    motivos = ligacoes.emissores_sem_ligacao()
    comuns = [
        _origem_de_tabela(emissores, raiz),
        _origem_da_conferida(ligacoes.TABELA_CONFERIDA),
        _origem_da_conferida(ligacoes.SEM_LIGACAO),
    ]
    saida = raiz / "fundos"
    coberturas, buracos, origens_de_todos = [], [], list(comuns)
    for arquivo in anos_do_cda(raiz):
        origens = [_origem_de_tabela(arquivo, raiz), *comuns]
        origens_de_todos.append(origens[0])
        posicoes = pd.read_parquet(arquivo, columns=COLUNAS_DO_CDA)
        gravar_com_versoes(
            lambda p=posicoes: ligacoes.painel_por_emissor(p),
            saida / "painel_emissor" / arquivo.stem, origens, ["competencia", "emissor", "tipo"],
        )  # fmt: skip
        bloco_8 = raiz / PASTA_DO_BLOCO_8 / arquivo.name
        da_empresa = origens
        acoes_do_bloco_8 = None
        if (
            bloco_8.is_file()
        ):  # o bloco 8 do ano (achado da série 4), se a carga do CDA já gravou
            da_empresa = [*origens, _origem_de_tabela(bloco_8, raiz)]
            acoes_do_bloco_8 = pd.read_parquet(bloco_8)
        gravar_com_versoes(
            lambda p=posicoes, b=acoes_do_bloco_8: ligacoes.painel_por_empresa(p, ligacao, b),
            saida / "painel_empresa" / arquivo.stem, da_empresa, ["competencia", "cnpj", "tipo"],
        )  # fmt: skip
        cobertura = ligacoes.cobertura(posicoes, ligacao)
        coberturas.append(cobertura)
        buracos.append(ligacoes.buracos(posicoes, ligacao, motivos))
        ultima = cobertura.iloc[-1]
        aviso = (
            ""
            if ultima["fracao_com_cnpj"] >= META_DE_COBERTURA
            else " (abaixo da meta de 95%)"
        )
        log.info(
            "%s: %.1f%% do valor com CNPJ no último mês%s",
            arquivo.stem,
            100 * ultima["fracao_com_cnpj"],
            aviso,
        )
    if not coberturas:
        return 0
    gravar_com_versoes(
        lambda: pd.concat(coberturas, ignore_index=True), saida / "cobertura", origens_de_todos,
        ["competencia"],
    )  # fmt: skip
    gravar_com_versoes(
        lambda: _juntar_buracos(buracos),
        saida / "buracos",
        origens_de_todos,
        ["emissor"],
    )
    return len(coberturas)


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--base", type=Path, default=None)
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    raiz_do_acervo = acervo.pasta_do_acervo()
    raiz = opcoes.base or (None if raiz_do_acervo is None else raiz_do_acervo / "base")
    if raiz is None:
        argumentos.error("acervo desligado: informe --base")
    anos = montar(raiz)
    if not anos:
        log.error("Nenhum ano do CDA na base: nada a montar")
        return 1
    log.info("Painéis montados para %s anos", anos)
    return 0


if __name__ == "__main__":
    sys.exit(main())
