"""Monta a base de demonstrações "como era na data" e grava um Parquet por ano (série 1 da base de
ML, PR 6; `base/ponto_no_tempo.py`).

    python -m scripts.montar_base_como_era --anos 2023 2024 --pasta dados_locais/base_como_era
    python -m scripts.montar_base_como_era --anos 2023 --baixar-enet 50   (baixa até 50 versões antigas)

Para os fatos de um ano Y junta quatro arquivos dos dados abertos (DFP e ITR de Y e de Y+1: o ano
seguinte traz Y na coluna do ano anterior) e as versões antigas do ENET que já estiverem no acervo.
Cada arquivo vem do acervo (`src/acervo.py`) e só é baixado da CVM se não estiver lá. Com
`--baixar-enet N`, baixa antes até N versões antigas que faltam, um pedido por vez
(`base/enet_coleta.py`).

Versão antiga que falta não vaza o futuro: o documento só aparece a partir da versão que a base tem.
A base fica com um buraco, e o relatório conta quantas faltaram. Feita para o servidor de casa ou o
PC (ADR 0031): no ano inteiro, a memória passa de 1 GB.
"""

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests
import sqlalchemy as sa

from base.contas_cvm import ler_contas, ler_indice
from base.enet import DocumentoEnet, ler_xml_enet
from base.enet_coleta import Baixador, baixar_em_fila, guardar, ja_guardados
from base.ponto_no_tempo import (
    com_divulgacao,
    gravar_parquet,
    montar_ano,
    publicadas_do_enet,
    versoes_antigas,
)
from src import demonstracoes as dm
from src.banco.coletas import com_registro, original_mais_recente
from src.banco.conexao import criar_engine, migrar_para
from src.configuracao import url_do_banco

log = logging.getLogger("tickerlab.base_como_era")
FONTE = "cvm-dfp-itr"
PASTA_PADRAO = Path("dados_locais") / "base_como_era"
NAO_ENCONTRADO = 404
URLS = {"DFP": dm.URL_DO_DFP, "ITR": dm.URL_DO_ITR}


def _baixar_da_fonte(url: str) -> bytes | None:
    """O arquivo da CVM, ou None se ele ainda não existe (404)."""
    resposta = requests.get(
        url, timeout=300, headers={"User-Agent": "TickerLab (tickerlab.com.br)"}
    )
    if resposta.status_code == NAO_ENCONTRADO:
        return None
    resposta.raise_for_status()
    return resposta.content


baixar = com_registro(FONTE, _baixar_da_fonte)


def _conteudo(motor: sa.Engine, url: str) -> bytes | None:
    with motor.connect() as conexao:
        guardado = original_mais_recente(conexao, url)
    return guardado if guardado is not None else baixar(url)


def documentos_do_enet(
    conexao: sa.Connection, indice: pd.DataFrame
) -> tuple[list[DocumentoEnet], list[str]]:
    """As versões antigas do índice que estão no acervo, lidas; e os links das que faltam."""
    documentos, faltando = [], []
    for link in versoes_antigas(indice)["link"]:
        xml = original_mais_recente(conexao, link)
        if xml is None:
            faltando.append(link)
        else:
            documentos.append(ler_xml_enet(xml))
    return documentos, faltando


def _baixar_versoes_antigas(motor: sa.Engine, indice: pd.DataFrame, limite: int) -> int:
    """Baixa até `limite` versões antigas que faltam no acervo. Devolve quantas baixou."""
    with motor.connect() as conexao:
        feitos = ja_guardados(conexao)
    links = [l for l in versoes_antigas(indice)["link"] if l not in feitos][:limite]

    def ao_baixar(link: str, pacote: bytes) -> None:
        with motor.begin() as conexao:
            guardar(conexao, link, pacote, datetime.now(UTC))

    resultado = baixar_em_fila(links, Baixador().baixar, feitos, ao_baixar)
    for link, erro in resultado.falhas.items():
        log.warning("ENET: %s não veio (%s); fica para a próxima rodada", link, erro)
    return len(resultado.baixados)


def _publicadas_do_arquivo(
    motor: sa.Engine, documento: str, ano_do_arquivo: int, ano: int, limite_enet: int
) -> tuple[pd.DataFrame | None, int]:
    """As contas publicadas num arquivo anual (dados abertos + ENET) com fim em `ano`.

    Devolve também quantas versões antigas faltaram no acervo.
    """
    conteudo = _conteudo(motor, URLS[documento].format(ano=ano_do_arquivo))
    if conteudo is None:
        log.info("%s %s ainda não existe na CVM: pulado", documento, ano_do_arquivo)
        return None, 0
    indice = ler_indice(conteudo, documento)
    contas = ler_contas(conteudo, documento, so_as_das_regras=True).contas
    if limite_enet:
        baixadas = _baixar_versoes_antigas(motor, indice, limite_enet)
        log.info(
            "%s %s: %s versões antigas baixadas", documento, ano_do_arquivo, baixadas
        )
    with motor.connect() as conexao:
        documentos, faltando = documentos_do_enet(conexao, indice)
    partes = [com_divulgacao(contas, indice, "dados_abertos")]
    if documentos:  # tabela vazia na junção estragaria o tipo das datas
        partes.append(publicadas_do_enet(documentos, indice))
    publicadas = pd.concat(partes, ignore_index=True)
    return publicadas[publicadas["fim"].dt.year == ano], len(faltando)


def montar(motor: sa.Engine, ano: int, pasta: Path, limite_enet: int) -> pd.DataFrame:
    """A base dos fatos de `ano`, gravada em `<pasta>/<ano>.parquet`."""
    partes, faltando = [], 0
    for documento in URLS:
        for ano_do_arquivo in (ano, ano + 1):
            publicadas, faltas = _publicadas_do_arquivo(
                motor, documento, ano_do_arquivo, ano, limite_enet
            )
            faltando += faltas
            if publicadas is not None:
                partes.append(publicadas)
    if not partes:
        log.warning("%s: nenhum arquivo da CVM; nada gravado", ano)
        return pd.DataFrame()
    base = montar_ano(pd.concat(partes, ignore_index=True), ano)
    gravar_parquet(base, pasta)
    log.info(
        "%s: %s linhas, %s versões antigas ainda fora do acervo (rode com --baixar-enet)",
        ano, len(base), faltando,
    )  # fmt: skip
    return base


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--anos", type=int, nargs="+", required=True)
    argumentos.add_argument("--pasta", type=Path, default=PASTA_PADRAO)
    argumentos.add_argument(
        "--baixar-enet",
        type=int,
        default=0,
        help="máximo de versões antigas a baixar por arquivo",
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        for ano in opcoes.anos:
            montar(motor, ano, opcoes.pasta, opcoes.baixar_enet)
    except (requests.RequestException, ValueError, sa.exc.SQLAlchemyError) as erro:
        log.error("Montagem interrompida: %s", erro)
        return 1
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
