"""Exporta, do banco do app, a entrada da análise escrita (ADR 0100) de cada empresa com ficha no dossiê.

A entrada é o que o modelo recebe em `scripts/escrever_analises.py` (`entrada_da_ficha`): a ficha do
relatório montada com e sem o dossiê. Ela precisa do banco do app e das fichas de `dossies/atual`,
que só existem no VPS, então este script roda lá **uma vez, só leitura**, e o lote em si roda em casa
(ADR 0100, item 9: nada de modelo roda no VPS):

    docker exec -i tickerlab python - --saida /tmp/entradas-analise < scripts/exportar_entradas_da_analise.py

Grava `<saida>/<cnpj>.json` por empresa e `<saida>/manifesto.json` (quantas saíram, quais ficaram de
fora e por quê). Falha numa empresa não derruba as outras. Fica de fora, com o motivo anotado: empresa
sem ticker no cadastro, sem demonstrações no banco, com a ficha do dossiê barrada ou ilegível, com
pessoa na entrada (LGPD: a entrada não sai do servidor) e com data depois do corte.
"""

import argparse
import dataclasses
import json
import logging
import os
import sys
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa

from src.analise_escrita import entrada as en
from src.banco.conexao import obter_engine
from src.banco.demonstracoes import PREFIXO_DO_CIK
from src.banco.relatorio_empresa import FUSO, entradas_do_relatorio, tickers_da_empresa
from src.dados import normalizar_ticker
from src.dossie import TAMANHO_DO_CNPJ, pasta_das_fichas
from src.relatorio_empresa import montar

log = logging.getLogger(__name__)

PLANO_DA_ANALISE = "pro"  # a análise é da ficha inteira; o que o grátis não vê fica marcado em `so_pro`
MANIFESTO = "manifesto.json"


class SemEntradaError(Exception):
    """A empresa fica de fora da exportação; a mensagem é o motivo anotado no manifesto."""


def cnpjs_com_ficha(pasta_dossies: Path) -> list[str]:
    """Os CNPJs (só dígitos) que têm ficha em `atual/`, em ordem; o manifesto do dossiê não conta."""
    atual = pasta_dossies / "atual"
    return sorted(
        caminho.stem
        for caminho in atual.glob("*.json")
        if caminho.stem.isdigit() and len(caminho.stem) == TAMANHO_DO_CNPJ
    )


def cnpj_com_mascara(digitos: str) -> str:
    """`02429144000193` vira `02.429.144/0001-93`, a forma guardada no banco."""
    return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"


def ticker_da_empresa(conexao: sa.Connection, cnpj: str) -> str | None:
    """Um ticker da empresa para montar o relatório (o primeiro código do cadastro, só como rótulo).

    Sem preço nem fechamentos na entrada, o código escolhido não muda nenhum número da ficha.
    """
    codigos = tickers_da_empresa(conexao, cnpj)
    if codigos.empty:
        return None
    return normalizar_ticker(str(codigos["codigo"].iloc[0]))


def entrada_da_empresa(
    conexao: sa.Connection, cnpj: str, corte: date
) -> dict[str, Any]:
    """A entrada da análise de uma empresa; `SemEntradaError` diz por que ela fica de fora."""
    if cnpj.startswith(PREFIXO_DO_CIK):
        raise SemEntradaError("empresa dos EUA (CIK)")
    ticker = ticker_da_empresa(conexao, cnpj)
    if ticker is None:
        raise SemEntradaError("sem ticker no cadastro")
    entradas = entradas_do_relatorio(conexao, ticker, hoje=corte)
    if entradas is None or entradas.dados.contas.empty:
        raise SemEntradaError("sem demonstrações no banco")
    if entradas.dossie is None:
        raise SemEntradaError("ficha do dossiê barrada ou ilegível")
    sem_dossie = dataclasses.replace(entradas, dossie=None)
    com = montar(entradas, plano=PLANO_DA_ANALISE)
    sem = montar(sem_dossie, plano=PLANO_DA_ANALISE)
    try:
        return en.entrada_da_ficha(com, corte, sem_dossie=sem)
    except en.PessoaNaEntradaError as erro:
        raise SemEntradaError(f"pessoa na entrada ({erro})") from erro
    except en.DataDepoisDoCorteError as erro:
        raise SemEntradaError(f"data depois do corte: {erro}") from erro


def _entradas(
    conexao: sa.Connection, cnpjs: list[str], corte: date
) -> Iterator[tuple[str, dict[str, Any] | None, str | None]]:
    """(cnpj, entrada, motivo) por empresa: entrada ou motivo, nunca os dois. Erro inesperado vira motivo."""
    for digitos in cnpjs:
        cnpj = cnpj_com_mascara(digitos)
        try:
            yield digitos, entrada_da_empresa(conexao, cnpj, corte), None
        except SemEntradaError as erro:
            yield digitos, None, str(erro)
        except Exception as erro:  # uma empresa com defeito não para as outras
            log.exception("erro inesperado na empresa %s", digitos)
            yield digitos, None, f"erro inesperado: {type(erro).__name__}"


def exportar(
    conexao: sa.Connection, pasta_dossies: Path, saida: Path, corte: date
) -> dict[str, Any]:
    """Grava uma entrada por empresa com ficha e o manifesto; devolve o manifesto."""
    saida.mkdir(parents=True, exist_ok=True)
    cnpjs = cnpjs_com_ficha(pasta_dossies)
    empresas: dict[str, dict[str, Any]] = {}
    de_fora: dict[str, str] = {}
    for digitos, entrada, motivo in _entradas(conexao, cnpjs, corte):
        if entrada is None:
            de_fora[digitos] = motivo or "sem motivo"
            log.info("de fora %s: %s", digitos, motivo)
            continue
        arquivo = saida / f"{digitos}.json"
        arquivo.write_text(
            json.dumps(entrada, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        empresas[digitos] = {
            "empresa": entrada["empresa"],
            "ticker": entrada["ticker"],
            "setor": entrada["setor"],
            "linhas": len(entrada["linhas"]),
            "arquivo": arquivo.name,
        }
        log.info(
            "entrada %s (%s): %d linhas",
            digitos,
            entrada["ticker"],
            len(entrada["linhas"]),
        )
    manifesto = {
        "corte": corte.isoformat(),
        "gerado_em": datetime.now(FUSO).isoformat(timespec="seconds"),
        "fichas": len(cnpjs),
        "exportadas": len(empresas),
        "empresas": empresas,
        "de_fora": de_fora,
    }
    (saida / MANIFESTO).write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return manifesto


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    analisador = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    analisador.add_argument(
        "--saida", type=Path, required=True, help="pasta das entradas"
    )
    analisador.add_argument(
        "--dossies",
        type=Path,
        default=None,
        help="pasta dos dossiês (com `atual/`); padrão: a do app (TICKERLAB_DOSSIES)",
    )
    analisador.add_argument(
        "--corte",
        type=date.fromisoformat,
        default=None,
        help="dia da análise (AAAA-MM-DD); padrão: hoje no Brasil",
    )
    return analisador.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _argumentos(argv)
    if args.dossies is not None:
        os.environ["TICKERLAB_DOSSIES"] = str(
            args.dossies
        )  # `ficha_do` lê a pasta daqui
    pasta_dossies = args.dossies or pasta_das_fichas()
    corte = args.corte or datetime.now(FUSO).date()
    with obter_engine().connect() as conexao:
        manifesto = exportar(conexao, pasta_dossies, args.saida, corte)
    print(
        f"{manifesto['exportadas']} de {manifesto['fichas']} fichas viraram entrada "
        f"({len(manifesto['de_fora'])} de fora); manifesto em {args.saida / MANIFESTO}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
