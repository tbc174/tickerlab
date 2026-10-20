"""Expurgo diário do login: apaga sessões e códigos de entrada já inúteis (LGPD, minimização).

    python -m scripts.expurgar_login

Sessões vencidas ou encerradas há mais de 90 dias e códigos de entrada vencidos há mais de 1 dia
(eles não têm `usuario_id`, então a exclusão da conta não os alcança). Pensado para rodar uma vez
por dia (cron). Nenhum e-mail aparece nos registros (logs): só as contagens.
"""

import logging
import sys

import sqlalchemy as sa

from src import codigo_de_entrada
from src.banco.conexao import criar_engine, migrar_para
from src.configuracao import url_do_banco

log = logging.getLogger("tickerlab.expurgo")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        with motor.begin() as conexao:
            apagados = codigo_de_entrada.expurgar(conexao)
        log.info("Expurgo do login: %s", apagados)
    except sa.exc.SQLAlchemyError as erro:
        log.error("Expurgo interrompido: %s", erro.__class__.__name__)
        return 1
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
