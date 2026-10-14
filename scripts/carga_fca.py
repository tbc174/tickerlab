"""Carga do FCA da CVM para a base: código da ação, emissores e tickers no tempo (série 3 da base de
ML, PR 3; `base/fca.py`).

    python -m scripts.carga_fca                       (FCA de 2010 até o ano atual)
    python -m scripts.carga_fca --desde 2018 --pasta <acervo>/base/fca

Cada arquivo anual vem do acervo (`src/acervo.py`) e só é baixado da CVM se não estiver lá (fonte
`cvm-fca`, com registro e SHA-256). Grava quatro tabelas com manifesto (`base/parquet.py`):
`valores_mobiliarios` (todas as linhas, versão mais nova de cada documento), `emissores` (emissor →
CNPJ, com conflitos marcados), `tickers` (`base/cadastro.py::tickers_no_tempo`, da série 1) e `codigos_invalidos` (código de
negociação fora do formato, para o relatório de buracos). Os tickers e os emissores levam também a
tabela conferida `base/conferidas/codigos_fora_do_fca.csv` (o BTG informa "000000"; série 3, PR 8),
com a coluna `origem`. Ano que não existe na CVM é pulado. Feita
para o servidor de casa (ADR 0031); recusa rodar sem a versão do código (exigência 13 da ADR 0055).
"""

import argparse
import hashlib
import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import sqlalchemy as sa

from base import fca
from base.cadastro import tickers_no_tempo
from base.parquet import gravar_tabela
from src import acervo
from src.banco.coletas import com_registro, original_mais_recente
from src.banco.conexao import criar_engine, migrar_para
from src.configuracao import url_do_banco
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_fca")
FONTE = "cvm-fca"
URL_DO_FCA = (
    "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_{ano}.zip"
)
PRIMEIRO_ANO = 2010  # o 1º FCA aberto
NAO_ENCONTRADO = 404
SUBPASTA = Path("base") / "fca"
# a tabela conferida entra nas origens dos tickers e dos emissores pelo caminho no repositório
URL_DOS_CODIGOS_CONFERIDOS = "base/conferidas/codigos_fora_do_fca.csv"


def _baixar_da_fonte(url: str) -> bytes | None:
    resposta = requests.get(
        url, timeout=120, headers={"User-Agent": "TickerLab (contato@tickerlab.com.br)"}
    )
    if resposta.status_code == NAO_ENCONTRADO:
        return None
    resposta.raise_for_status()
    return resposta.content


baixar = com_registro(FONTE, _baixar_da_fonte)


def _pasta_padrao() -> Path | None:
    raiz = acervo.pasta_do_acervo()
    return None if raiz is None else raiz / SUBPASTA


def ler_anos(conexao: sa.Connection, anos: range) -> list[tuple[str, bytes]]:
    """(endereço, conteúdo) de cada FCA dos anos pedidos que existe na CVM."""
    lidos = []
    for ano in anos:
        url = URL_DO_FCA.format(ano=ano)
        conteudo = original_mais_recente(conexao, url) or baixar(url)
        if conteudo is None:
            log.info("FCA de %s não existe na CVM: pulado", ano)
            continue
        lidos.append((url, conteudo))
    return lidos


def gravar(
    valores: pd.DataFrame,
    conteudos: list[bytes],
    origens: list[dict[str, str]],
    pasta: Path,
) -> None:
    tickers, emissores = fca.com_codigos_conferidos(
        tickers_no_tempo(conteudos), fca.emissores(valores), fca.codigos_conferidos()
    )
    conferida = {
        "url": URL_DOS_CODIGOS_CONFERIDOS,
        "sha256": hashlib.sha256(fca.CODIGOS_CONFERIDOS.read_bytes()).hexdigest(),
    }
    tabelas = {
        "valores_mobiliarios": (
            valores,
            ["cnpj", "referencia", "valor_mobiliario"],
            origens,
        ),
        "emissores": (emissores, ["emissor", "cnpj"], [*origens, conferida]),
        "tickers": (tickers, ["codigo", "cnpj"], [*origens, conferida]),
        "codigos_invalidos": (
            fca.codigos_invalidos(valores),
            ["cnpj", "referencia"],
            origens,
        ),
    }
    for nome, (tabela, ordem, de_onde) in tabelas.items():
        gravar_tabela(tabela, pasta / nome, de_onde, ordem)
        log.info("%s: %s linhas", nome, len(tabela))


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    argumentos.add_argument("--desde", type=int, default=PRIMEIRO_ANO)
    argumentos.add_argument("--ate", type=int, default=hoje.year)
    argumentos.add_argument("--pasta", type=Path, default=None)
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    pasta = opcoes.pasta or _pasta_padrao()
    if pasta is None:
        argumentos.error("acervo desligado: informe --pasta")
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        with motor.connect() as conexao:
            lidos = ler_anos(conexao, range(opcoes.desde, opcoes.ate + 1))
    finally:
        motor.dispose()
    if not lidos:
        log.error("Nenhum FCA lido")
        return 1
    conteudos = [c for _, c in lidos]
    valores = pd.concat(
        [fca.ler_valores_mobiliarios(c) for c in conteudos], ignore_index=True
    )
    origens = [{"url": u, "sha256": hashlib.sha256(c).hexdigest()} for u, c in lidos]
    gravar(valores, conteudos, origens, pasta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
