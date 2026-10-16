"""Carga do FCA da CVM para a base: código da ação, emissores e tickers no tempo (série 3 da base de
ML, PR 3; `base/fca.py`).

    python -m scripts.carga_fca                       (FCA de 2010 até o ano atual)
    python -m scripts.carga_fca --desde 2018 --pasta <acervo>/base/fca

Cada arquivo anual vem do acervo (`src/acervo.py`) e só é baixado da CVM se não estiver lá (fonte
`cvm-fca`, com registro e SHA-256). Grava quatro tabelas com manifesto (`base/parquet.py`):
`valores_mobiliarios` (todas as linhas, versão mais nova de cada documento, com a data de entrega),
`emissores` (emissor → CNPJ, com conflitos marcados), `tickers` (`base/cadastro.py::tickers_no_tempo`,
de quando a quando cada código valeu, pelas entregas do FCA; série 4, PR 1) e `codigos_invalidos`
(código de negociação fora do formato, para o relatório de buracos). Os tickers e os emissores levam
também a tabela conferida `base/conferidas/codigos_fora_do_fca.csv` (o BTG informa "000000"; série 3,
PR 8), com a coluna `origem`. Ano que não existe na CVM é pulado. Feita para o servidor de casa (ADR
0031); recusa rodar sem a versão do código (exigência 13 da ADR 0055).

Versões antigas (achado da série 4): a CVM publica os valores mobiliários só da versão mais nova de cada
formulário. A carga lê **todas** as baixadas guardadas de cada ano (cada uma com as versões que trazia)
e os documentos das versões que `scripts/coletar_fca_versoes.py` guardou do sistema de documentos da CVM;
`valores_mobiliarios` diz a origem de cada linha.
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
from base.cadastro import tickers_dos_valores
from base.parquet import gravar_tabela
from src import acervo
from src.banco.coletas import (
    com_registro,
    originais_guardados,
    originais_mais_recentes,
)
from src.banco.conexao import criar_engine, migrar_para
from src.configuracao import url_do_banco
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.carga_fca")
FONTE = "cvm-fca"
URL_DO_FCA = fca.URL_DO_ANO
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
    """(endereço, conteúdo) de cada FCA dos anos pedidos: todas as baixadas guardadas no acervo (da
    mais antiga à mais nova) ou, se nenhuma, a da CVM agora."""
    lidos = []
    for ano in anos:
        url = URL_DO_FCA.format(ano=ano)
        guardados = originais_guardados(conexao, url)
        if not guardados and (novo := baixar(url)) is not None:
            guardados = [novo]
        if not guardados:
            log.info("FCA de %s não existe na CVM: pulado", ano)
        lidos.extend((url, conteudo) for conteudo in guardados)
    return lidos


def ler_versoes(
    conexao: sa.Connection, documentos: pd.DataFrame
) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    """Os valores das versões antigas guardadas (`coletar_fca_versoes`) dos documentos dos anos lidos,
    com a origem de cada uma (endereço e SHA-256)."""
    por_numero = documentos.drop_duplicates("id_documento").set_index("id_documento")
    partes, origens = [], []
    for linha in originais_mais_recentes(conexao, fca.FONTE_DAS_VERSOES):
        numero = linha.url.split("numSequencia=")[1].split("&")[0]
        conteudo = acervo.ler_original(linha.caminho_do_original)
        if numero not in por_numero.index or conteudo is None:
            continue
        documento = por_numero.loc[numero].to_dict() | {"id_documento": numero}
        partes.append(fca.ler_documento_da_versao(conteudo, documento))
        origens.append({"url": linha.url, "sha256": linha.sha256})
    versoes = (
        pd.concat(partes, ignore_index=True)
        if partes
        else pd.DataFrame(columns=list(fca.COLUNAS))
    )
    return versoes, origens


def gravar(valores: pd.DataFrame, origens: list[dict[str, str]], pasta: Path) -> None:
    tickers, emissores = fca.com_codigos_conferidos(
        tickers_dos_valores(valores), fca.emissores(valores), fca.codigos_conferidos()
    )
    conferida = {
        "url": URL_DOS_CODIGOS_CONFERIDOS,
        "sha256": hashlib.sha256(fca.CODIGOS_CONFERIDOS.read_bytes()).hexdigest(),
    }
    tabelas = {
        "valores_mobiliarios": (
            valores,
            ["cnpj", "referencia", "versao", "id_documento", "valor_mobiliario"],
            origens,
        ),
        "emissores": (emissores, ["emissor", "cnpj"], [*origens, conferida]),
        "tickers": (
            tickers,
            ["codigo", "cnpj", "primeiro_visto"],
            [*origens, conferida],
        ),
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
            if not lidos:
                log.error("Nenhum FCA lido")
                return 1
            conteudos = [c for _, c in lidos]
            # da baixada mais nova para a mais antiga: cada documento vem de uma só
            abertos = fca.sem_documento_repetido(
                [fca.ler_valores_mobiliarios(c) for c in reversed(conteudos)]
            )
            documentos = pd.concat(
                [fca.documentos(c) for c in conteudos], ignore_index=True
            )
            versoes, origens_das_versoes = ler_versoes(conexao, documentos)
    finally:
        motor.dispose()
    origens = [{"url": u, "sha256": hashlib.sha256(c).hexdigest()} for u, c in lidos]
    log.info("Versões antigas do RAD: %s documentos", len(origens_das_versoes))
    gravar(
        fca.juntar_versoes(abertos, versoes), [*origens, *origens_das_versoes], pasta
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
