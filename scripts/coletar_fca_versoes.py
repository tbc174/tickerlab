"""Coleta em gotas das versões antigas do FCA no sistema de documentos da CVM (RAD; achado da série 4
da base de ML; `base/fca.py`).

    python -m scripts.coletar_fca_versoes                     (até 3 documentos, FCA de 2018 em diante)
    python -m scripts.coletar_fca_versoes --maximo 1 --desde 2021 --ate 2021

A CVM publica nos dados abertos os valores mobiliários só da versão mais nova de cada formulário; as
anteriores (e os códigos de negociação que elas traziam) estão no documento de cada versão. A lista do
que buscar vem dos FCA já guardados no acervo (`fca.versoes_a_buscar`: as versões substituídas nos anos
em que o código da empresa mudou). Cada documento vai para o acervo com registro (fonte
`cvm-fca-versao`); o que já veio, ou que a CVM disse não existir, não é pedido de novo.

A CVM limita os downloads por endereço (a rotulagem por IA mede de 1 a 3 documentos por hora): uma
pausa entre os pedidos e, à primeira página no lugar do zip, a coleta para sem erro e continua na
próxima rodada. Roda de madrugada, fora das janelas da carga do ENET e da rotulagem. Recusa rodar sem
a versão do código (exigência 13 da ADR 0055).
"""

import argparse
import logging
import sys
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import sqlalchemy as sa

from base import fca
from src import rede
from src.banco.coletas import com_registro, original_mais_recente
from src.banco.conexao import criar_engine, migrar_para
from src.banco.modelo import coletas
from src.configuracao import url_do_banco
from src.versao_do_codigo import exigir_versao_do_codigo

log = logging.getLogger("tickerlab.coletar_fca_versoes")
PAUSA_ENTRE_DOWNLOADS = 60  # segundos: a CVM limita os downloads por endereço
MAXIMO_POR_RODADA = 3
NAO_ENCONTRADO = 404
ASSINATURA_DO_ZIP = b"PK"
JA_RESOLVIDO = ("ok", "nao_encontrado")


def _hoje() -> date:
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


class LimiteDaCVM(Exception):
    """A CVM devolveu uma página no lugar do documento: parar e continuar na próxima rodada."""


def conferir_documento(conteudo: bytes | None) -> bytes | None:
    """O documento, se é um zip; `None` (não existe) passa; página no lugar do zip é o limite."""
    if conteudo is not None and not conteudo.startswith(ASSINATURA_DO_ZIP):
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


baixar = com_registro(fca.FONTE_DAS_VERSOES, _baixar_da_fonte)


def alvos(conexao: sa.Connection, anos: range) -> pd.DataFrame:
    """As versões a buscar nos anos pedidos. A troca de código é medida com todos os FCA do acervo
    (de 2018 até hoje): um ano sozinho não mostra se o código mudou em relação ao vizinho."""
    zips = [
        conteudo
        for ano in range(fca.PRIMEIRO_ANO_COM_TICKER, _hoje().year + 1)
        if (conteudo := original_mais_recente(conexao, fca.URL_DO_ANO.format(ano=ano)))
    ]
    if not zips:
        return pd.DataFrame(columns=[*fca.COLUNAS_DOS_DOCUMENTOS, "url"])
    documentos = pd.concat([fca.documentos(z) for z in zips], ignore_index=True)
    valores = pd.concat(
        [fca.ler_valores_mobiliarios(z) for z in zips], ignore_index=True
    )
    alvo = fca.versoes_a_buscar(documentos, valores)
    return alvo[alvo["referencia"].dt.year.isin(anos)].reset_index(drop=True)


def _ja_resolvidos(conexao: sa.Connection) -> set[str]:
    return set(
        conexao.execute(
            sa.select(coletas.c.url).where(
                coletas.c.fonte == fca.FONTE_DAS_VERSOES,
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
    hoje = _hoje()
    argumentos.add_argument("--desde", type=int, default=fca.PRIMEIRO_ANO_COM_TICKER)
    argumentos.add_argument("--ate", type=int, default=hoje.year)
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
            lista = alvos(conexao, range(opcoes.desde, opcoes.ate + 1))
            feitos = _ja_resolvidos(conexao)
    finally:
        motor.dispose()
    faltam = [u for u in lista["url"] if u not in feitos]
    pedidos = coletar(faltam, opcoes.maximo)
    log.info(
        "Versões do FCA: %s na lista, %s pedidas agora, faltavam %s",
        len(lista),
        pedidos,
        len(faltam),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
