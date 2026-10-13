"""Coleta as negociações de pessoas de dentro das empresas da B3 (VLMO da CVM) para o Research.

    python -m scripts.atualizar_negociacoes_cvm            (ano atual e anterior)
    python -m scripts.atualizar_negociacoes_cvm --anos 3

Roda fora do app (no servidor, uma vez por dia); o app só lê. Grava as negociações e um evento por
documento, cargo e operação (página Acontecimentos). Um arquivo que ainda não existe na CVM (o do
ano novo, em janeiro) é pulado; outras falhas param a coleta sem apagar nada.
"""

import argparse
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import sqlalchemy as sa

from src import negociacoes as ng
from src import negociacoes_cvm as vlmo
from src.banco.conexao import criar_engine, migrar_para
from src.banco.eventos import gravar_eventos
from src.banco.negociacoes import gravar_negociacoes
from src.configuracao import url_do_banco

log = logging.getLogger("tickerlab.negociacoes")
MAX_ANOS = 5
NAO_ENCONTRADO = 404


def baixar(url: str) -> bytes | None:
    """O arquivo da CVM, ou None se ele ainda não existe (404)."""
    resposta = requests.get(
        url, timeout=300, headers={"User-Agent": "TickerLab (tickerlab.com.br)"}
    )
    if resposta.status_code == NAO_ENCONTRADO:
        return None
    resposta.raise_for_status()
    return resposta.content


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument(
        "--anos", type=int, default=2, help=f"anos (1 a {MAX_ANOS})"
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    ano = datetime.now(ZoneInfo("America/Sao_Paulo")).year
    anos = max(1, min(opcoes.anos, MAX_ANOS))
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        for ano_do_arquivo in range(ano - anos + 1, ano + 1):
            conteudo = baixar(vlmo.URL_DO_VLMO.format(ano=ano_do_arquivo))
            if conteudo is None:
                log.info("VLMO %s ainda não existe na CVM: pulado", ano_do_arquivo)
                continue
            tabela = vlmo.ler_vlmo(conteudo)
            with motor.begin() as conexao:
                novos, atualizados = gravar_negociacoes(conexao, tabela)
                eventos = gravar_eventos(
                    conexao, ng.eventos_das_negociacoes(tabela), fonte=ng.FONTE_VLMO
                )
            log.info(
                "VLMO %s: %s negociações; documentos %s novos e %s atualizados; %s eventos novos",
                ano_do_arquivo, len(tabela), novos, atualizados, eventos[0],
            )  # fmt: skip
    except (requests.RequestException, ValueError, sa.exc.SQLAlchemyError) as erro:
        log.error("Coleta interrompida: %s", erro)
        return 1
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
