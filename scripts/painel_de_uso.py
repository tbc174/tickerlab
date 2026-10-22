"""Números de uso da semana (ADR 0109, item 15), em JSON, para a Central TickerLab.

    python -m scripts.painel_de_uso            # últimas 12 semanas, a em curso por último

Só contagens (ativos por semana, relatórios gerados, PDFs entregues); nenhum e-mail aparece.
Roda no servidor, uma vez por semana; a sessão da Diretoria grava a saída na Central
(`ArtifactData`, ver `central-tickerlab.md`). Não mexe no banco (só lê).
"""

import json
import logging
import sys

import sqlalchemy as sa

from src import painel_de_uso
from src.banco.conexao import criar_engine
from src.configuracao import url_do_banco

log = logging.getLogger("tickerlab.painel_de_uso")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    motor = criar_engine(url_do_banco())
    try:
        with motor.connect() as conexao:
            semanas = painel_de_uso.historico(conexao)
    except sa.exc.SQLAlchemyError as erro:
        log.error("Painel de uso interrompido: %s", erro.__class__.__name__)
        return 1
    finally:
        motor.dispose()
    print(json.dumps(semanas, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
