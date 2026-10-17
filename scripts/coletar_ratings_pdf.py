"""Coleta em gotas dos documentos de rating do IPE no sistema de documentos da CVM (RAD; `base/ratings.py`).

    python -m scripts.coletar_ratings_pdf                 (até 20 documentos, do mais novo ao mais velho)
    python -m scripts.coletar_ratings_pdf --maximo 5

A lista vem dos arquivos anuais do IPE já guardados no acervo (`cvm-hist-ipe`): os relatórios de
agência de rating e os documentos cujo assunto fala de rating (~5.900, desde 2003). Cada documento vai
para o acervo com registro (fonte `cvm-ipe-rating`, com SHA-256); o que já veio, ou que a CVM disse
não existir, não é pedido de novo.

A CVM limita os downloads por endereço: uma pausa entre os pedidos e, à primeira página no lugar do
documento, a coleta para sem erro e continua na próxima rodada. Roda de hora em hora fora dos minutos
da rotulagem por IA (que baixa do mesmo sistema). Recusa rodar sem a versão do código (exigência 13
da ADR 0055).
"""

import argparse
import logging
import sys
import time

import pandas as pd
import sqlalchemy as sa

from base import ratings
from src import rede
from src.banco.coletas import com_registro
from src.banco.conexao import criar_engine, migrar_para
from src.banco.modelo import coletas
from src.configuracao import url_do_banco
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.coletar_ratings_pdf")
PAUSA_ENTRE_DOWNLOADS = 60  # segundos: a CVM limita os downloads por endereço
MAXIMO_POR_RODADA = 20
NAO_ENCONTRADO = 404
JA_RESOLVIDO = ("ok", "nao_encontrado")
INICIO_DE_PAGINA = (b"<!doctype", b"<html", b"<head", b"<body", b"<?xml")


class LimiteDaCVM(Exception):
    """A CVM devolveu uma página no lugar do documento: parar e continuar na próxima rodada."""


def conferir_documento(conteudo: bytes | None) -> bytes | None:
    """O documento como veio (PDF, Word...); `None` (não existe) passa; página da web é o limite."""
    if conteudo is not None and conteudo.lstrip()[:16].lower().startswith(
        INICIO_DE_PAGINA
    ):
        raise LimiteDaCVM("a CVM devolveu uma página no lugar do documento")
    return conteudo


def _baixar_da_fonte(url: str) -> bytes | None:
    resposta = rede.obter(
        url, timeout=120, headers={"User-Agent": "TickerLab (contato@tickerlab.com.br)"}
    )
    if resposta.status_code == NAO_ENCONTRADO:
        return None
    resposta.raise_for_status()
    return conferir_documento(resposta.content)


baixar = com_registro(ratings.FONTE_DOS_PDFS, _baixar_da_fonte)


def alvos(conexao: sa.Connection) -> pd.DataFrame:
    """Os documentos com rating de todos os arquivos anuais do IPE guardados, do mais novo ao mais
    velho (o mais recente serve ao monitoramento antes; o resto vem nas rodadas seguintes)."""
    documentos, _ = ratings.documentos_guardados(conexao)
    return documentos.sort_values(
        ["publico_em", "protocolo", "versao"], ascending=False
    ).reset_index(drop=True)


def _ja_resolvidos(conexao: sa.Connection) -> set[str]:
    return set(
        conexao.execute(
            sa.select(coletas.c.url).where(
                coletas.c.fonte == ratings.FONTE_DOS_PDFS,
                coletas.c.situacao.in_(JA_RESOLVIDO),
            )
        ).scalars()
    )


def coletar(urls: list[str], maximo: int) -> int:
    """Baixa até `maximo` documentos, com pausa; para no limite da CVM. Devolve quantos pediu."""
    pedidos = 0
    for url in urls[:maximo]:
        if pedidos:
            time.sleep(PAUSA_ENTRE_DOWNLOADS)
        pedidos += 1
        try:
            baixar(url)
        except LimiteDaCVM:
            log.warning(
                "A CVM devolveu uma página no lugar do documento (limite): para aqui."
            )
            break
    return pedidos


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--maximo", type=int, default=MAXIMO_POR_RODADA)
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    log.info("Versão do código: %s", exigir_versao_do_codigo())
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        with motor.connect() as conexao:
            lista = alvos(conexao)
            feitos = _ja_resolvidos(conexao)
    finally:
        motor.dispose()
    faltam = [u for u in lista["link"] if u not in feitos]
    pedidos = coletar(faltam, opcoes.maximo)
    log.info(
        "Ratings do IPE: %s na lista, %s pedidos agora, faltavam %s",
        len(lista),
        pedidos,
        len(faltam),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
