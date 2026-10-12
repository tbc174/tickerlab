"""Coleta as demonstrações financeiras da CVM (DFP e ITR), o setor de cada companhia e os alertas
de entrega fora do prazo (eventos do Research, `src/prazos.py`).

    python -m scripts.atualizar_fundamentos            (DFP e ITR do ano atual e do anterior)
    python -m scripts.atualizar_fundamentos --anos 6   (primeira carga: 6 anos de DFP)

Roda fora do app (no servidor, uma vez por dia); o app só lê. Usa o banco de
`TICKERLAB_DATABASE_URL` e aplica as migrações antes. Um arquivo que ainda não existe na CVM (o DFP
do ano corrente, antes de março) é pulado; outras falhas param a coleta sem apagar nada.
"""

import argparse
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import sqlalchemy as sa

from src import demonstracoes as dm
from src import prazos
from src.banco.conexao import criar_engine, migrar_para
from src.banco.demonstracoes import gravar_demonstracoes, gravar_setores
from src.banco.eventos import gravar_eventos
from src.configuracao import url_do_banco

log = logging.getLogger("tickerlab.fundamentos")
MAX_ANOS = 10  # o suficiente para crescimento de 5 a 10 anos
ANOS_DE_ITR = 2  # os 12 meses só precisam do ITR deste ano e do anterior
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
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument(
        "--anos", type=int, default=2, help=f"anos de DFP (1 a {MAX_ANOS})"
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
        cadastro = baixar(dm.URL_DO_CADASTRO)
        if cadastro:
            with motor.begin() as conexao:
                log.info(
                    "Setores: %s companhias",
                    gravar_setores(conexao, dm.ler_setores(cadastro)),
                )
        pedidos = [("DFP", a) for a in range(ano - anos, ano + 1)]
        pedidos += [("ITR", a) for a in range(ano - ANOS_DE_ITR + 1, ano + 1)]
        for documento, ano_do_arquivo in pedidos:
            modelo = dm.URL_DO_DFP if documento == "DFP" else dm.URL_DO_ITR
            conteudo = baixar(modelo.format(ano=ano_do_arquivo))
            if conteudo is None:
                log.info(
                    "%s %s ainda não existe na CVM: pulado", documento, ano_do_arquivo
                )
                continue
            contas, documentos = dm.ler_demonstracoes(conteudo, documento)
            atrasos = prazos.eventos_de_atraso(
                dm.ler_primeiras_entregas(conteudo, documento)
            )
            with motor.begin() as conexao:
                mudaram = gravar_demonstracoes(conexao, contas, documentos)
                alertas = gravar_eventos(conexao, atrasos, fonte=prazos.FONTE_PRAZO)[0]
            log.info(
                "%s %s: %s documentos lidos, %s novos ou atualizados, %s alertas de atraso novos",
                documento, ano_do_arquivo, len(documentos), mudaram, alertas,
            )  # fmt: skip
    except (requests.RequestException, ValueError, sa.exc.SQLAlchemyError) as erro:
        log.error("Coleta interrompida: %s", erro)
        return 1
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
