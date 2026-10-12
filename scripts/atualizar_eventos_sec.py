"""Coleta os eventos das empresas dos EUA na SEC (8-K, 10-K, 10-Q...) para o Research.

    python -m scripts.atualizar_eventos_sec            (últimos 400 dias)
    python -m scripts.atualizar_eventos_sec --dias 730

Empresas: as ações dos EUA do catálogo do app (o S&P 500). Regras de acesso da SEC: cada consulta
diz quem é e um e-mail de contato (`TICKERLAB_CONTATO`, no .env, fora do Git) e no máximo 10
consultas por segundo (aqui, ~8). Sem o contato, não consulta nada e sai com erro. Uma empresa que
falhar é pulada; as outras seguem. Não apaga nada.
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
import sqlalchemy as sa

from src import catalogo
from src import eventos_sec as sec
from src.banco.conexao import criar_engine, migrar_para
from src.banco.eventos import ORIGEM_SEC, gravar_eventos, gravar_tickers
from src.configuracao import contato, url_do_banco

log = logging.getLogger("tickerlab.sec")
PAUSA_ENTRE_CONSULTAS = 0.125  # 8 por segundo, abaixo do limite de 10 da SEC
DIAS_PADRAO = 400
SEM_CONTATO = 2  # código de saída: falta configurar o e-mail


def baixar(url: str, agente: str) -> bytes:
    resposta = requests.get(
        url,
        timeout=60,
        headers={"User-Agent": agente, "Accept-Encoding": "gzip, deflate"},
    )
    resposta.raise_for_status()
    return resposta.content


def tickers_dos_eua() -> set[str]:
    tabela = catalogo.carregar()
    return set(tabela.index[tabela["bolsa"] == "EUA"])


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument(
        "--dias", type=int, default=DIAS_PADRAO, help="janela em dias"
    )
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    email = contato()
    if email is None:
        log.error(
            "Falta TICKERLAB_CONTATO (a SEC exige um e-mail de contato): nada consultado."
        )
        return SEM_CONTATO
    agente = f"TickerLab {email}"
    desde = datetime.now(ZoneInfo("America/Sao_Paulo")).date() - timedelta(
        days=opcoes.dias
    )
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        mapa = sec.ler_tickers(baixar(sec.URL_DOS_TICKERS, agente), tickers_dos_eua())
        with motor.begin() as conexao:
            log.info(
                "Mapa ticker → CIK: %s empresas",
                gravar_tickers(conexao, mapa, origem=ORIGEM_SEC),
            )
        novos = falhas = 0
        for cnpj in sorted(set(mapa["cnpj"])):
            time.sleep(PAUSA_ENTRE_CONSULTAS)
            try:
                conteudo = baixar(
                    sec.URL_DOS_DOCUMENTOS.format(
                        cik=int(cnpj.removeprefix(sec.PREFIXO_DO_CIK))
                    ),
                    agente,
                )
                tabela = sec.ler_documentos(conteudo, desde)
            except (requests.RequestException, ValueError, KeyError) as erro:
                falhas += 1
                log.warning("%s pulada: %s", cnpj, erro.__class__.__name__)
                continue
            with motor.begin() as conexao:
                novos += gravar_eventos(conexao, tabela, fonte=sec.FONTE_SEC)[0]
        log.info(
            "SEC: %s empresas, %s eventos novos, %s falhas",
            len(set(mapa["cnpj"])),
            novos,
            falhas,
        )
    except (requests.RequestException, ValueError, sa.exc.SQLAlchemyError) as erro:
        log.error("Coleta interrompida: %s", erro)
        return 1
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
