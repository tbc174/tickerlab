"""Monta a amostra integrada (ADR 0058; plano `2026-10-16-amostra-integrada-v1.md`): o painel companhia ×
fim de mês "como era na data", das tabelas que já estão na base (não baixa nada).

    python -m scripts.montar_amostra                     (a base do acervo, até o último mês fechado)
    python -m scripts.montar_amostra --base <pasta> --fim 2026-09-30

Grava `<base>/amostra/v1/painel/<ano>.parquet` com manifesto, versões e linhagem: as origens são as
tabelas de entrada (e o cadastro da CVM, um original), e a linhagem segue delas até os originais. Por
enquanto o painel tem o bloco "universo" (quem está, desde quando e com que tickers); os outros entram
um por PR. Recusa rodar sem a versão do código (exigência 13 da ADR 0055).
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from base.amostra import universo
from base.cadastro import ler_cadastro
from base.parquet import gravar_com_versoes, origem_de_tabela
from src import acervo
from src.banco.coletas import originais_mais_recentes
from src.banco.conexao import criar_engine, migrar_para
from src.configuracao import url_do_banco
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.montar_amostra")
PASTA = Path("amostra") / "v1" / "painel"
FONTE_DO_CADASTRO, ARQUIVO_DO_CADASTRO = "cvm-cadastros", "cad_cia_aberta.csv"
ROTULOS_ATRASO = Path("rotulos_atraso") / "rotulos_atraso.parquet"
TICKERS = Path("fca") / "tickers.parquet"
ORDEM = ["cnpj", "data"]


def ultimo_mes_fechado(hoje: pd.Timestamp) -> pd.Timestamp:
    """O último dia do mês anterior ao de `hoje` (em 01/10 e em 31/10, 30/09)."""
    primeiro_dia = pd.Timestamp(year=hoje.year, month=hoje.month, day=1)
    return pd.Timestamp(primeiro_dia - pd.Timedelta(days=1))


def _cadastro(conexao: sa.Connection) -> tuple[pd.DataFrame, dict[str, str]]:
    for original in originais_mais_recentes(conexao, FONTE_DO_CADASTRO):
        if original.url.rsplit("/", 1)[-1] != ARQUIVO_DO_CADASTRO:
            continue
        conteudo = acervo.ler_original(original.caminho_do_original)
        if conteudo is not None:
            return ler_cadastro(conteudo), {
                "url": original.url,
                "sha256": original.sha256,
            }
    raise FileNotFoundError(f"sem o {ARQUIVO_DO_CADASTRO} no acervo")


def entradas_e_origens(
    conexao: sa.Connection, base: Path
) -> tuple[dict[str, pd.DataFrame], list[dict[str, str]]]:
    """As entradas do painel (já preparadas) e as origens para o manifesto."""
    cadastro, origem_do_cadastro = _cadastro(conexao)
    entregas = pd.read_parquet(
        base / ROTULOS_ATRASO, columns=["cnpj", "primeira_entrega"]
    )
    tickers = pd.read_parquet(base / TICKERS)
    origens = [
        origem_do_cadastro,
        origem_de_tabela(base / ROTULOS_ATRASO, base),
        origem_de_tabela(base / TICKERS, base),
    ]
    return universo.preparar(cadastro, entregas, tickers), origens


def gravar(painel: pd.DataFrame, base: Path, origens: list[dict[str, str]]) -> None:
    for ano, do_ano in painel.groupby(painel["data"].dt.year):
        resultado = gravar_com_versoes(
            lambda t=do_ano: t.reset_index(drop=True),
            base / PASTA / str(ano),
            origens,
            ORDEM,
        )
        log.info("amostra %s: %s (%s linhas)", ano, resultado, len(do_ano))


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--base", type=Path, default=None)
    argumentos.add_argument("--fim", type=pd.Timestamp, default=None)
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    raiz = acervo.pasta_do_acervo()
    base = opcoes.base or (None if raiz is None else raiz / "base")
    if base is None:
        argumentos.error("acervo desligado: informe --base")
    fim = opcoes.fim or ultimo_mes_fechado(pd.Timestamp.now())
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        with motor.connect() as conexao:
            entradas, origens = entradas_e_origens(conexao, base)
    finally:
        motor.dispose()
    painel = universo.montar(entradas, fim)
    log.info(
        "universo: %s companhias, %s linhas, %s com ticker",
        painel["cnpj"].nunique(), len(painel), int(painel["com_ticker_na_data"].sum()),
    )  # fmt: skip
    gravar(painel, base, origens)
    return 0


if __name__ == "__main__":
    sys.exit(main())
