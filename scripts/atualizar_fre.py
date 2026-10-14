"""Carga dos proventos e eventos de capital do FRE da CVM (série 2 da base de ML, PR 6).

    python -m scripts.atualizar_fre                        (FRE de 2010 a 2022)
    python -m scripts.atualizar_fre --desde 2020 --ate 2022

As tabelas de dividendos, desdobramentos, grupamentos, bonificações e aumentos de capital só existem
no FRE aberto até o de 2022 (Resolução CVM 59): é uma carga de uma vez, sem cron. Cada arquivo vai
para o acervo e o registro de coletas (fonte `cvm-fre`). Um ano que não existe na CVM é pulado.
"""

import argparse
import logging
import sys
from datetime import UTC, datetime

import requests
import sqlalchemy as sa

from base.fre import ULTIMO_ANO_COM_AS_TABELAS, ler_eventos_de_capital, ler_proventos
from src.banco.coletas import com_registro
from src.banco.conexao import criar_engine, migrar_para
from src.banco.fre import gravar_eventos, gravar_proventos
from src.configuracao import url_do_banco

log = logging.getLogger("tickerlab.fre")
URL_DO_FRE = (
    "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FRE/DADOS/fre_cia_aberta_{ano}.zip"
)
PRIMEIRO_ANO = 2010
NAO_ENCONTRADO = 404


def _baixar_da_fonte(url: str) -> bytes | None:
    resposta = requests.get(
        url, timeout=300, headers={"User-Agent": "TickerLab (tickerlab.com.br)"}
    )
    if resposta.status_code == NAO_ENCONTRADO:
        return None
    resposta.raise_for_status()
    return resposta.content


baixar = com_registro("cvm-fre", _baixar_da_fonte)


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--desde", type=int, default=PRIMEIRO_ANO)
    argumentos.add_argument("--ate", type=int, default=ULTIMO_ANO_COM_AS_TABELAS)
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        for ano in range(opcoes.desde, opcoes.ate + 1):
            conteudo = baixar(URL_DO_FRE.format(ano=ano))
            if conteudo is None:
                log.info("FRE %s não existe na CVM: pulado", ano)
                continue
            proventos = ler_proventos(conteudo)
            eventos = ler_eventos_de_capital(conteudo)
            agora = datetime.now(UTC)
            with motor.begin() as conexao:
                novos_proventos = gravar_proventos(conexao, proventos, agora)
                novos_eventos = gravar_eventos(conexao, eventos, agora)
            log.info(
                "FRE %s: %s proventos e %s eventos de capital novos ou atualizados",
                ano, novos_proventos, novos_eventos,
            )  # fmt: skip
    except (requests.RequestException, ValueError, sa.exc.SQLAlchemyError) as erro:
        log.error("Carga do FRE interrompida: %s", erro)
        return 1
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
