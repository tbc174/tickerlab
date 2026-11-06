"""Números de uso da semana (ADR 0109, item 15), em JSON, para a Central TickerLab.

    python -m scripts.painel_de_uso               # últimas 12 semanas, a em curso por último
    python -m scripts.painel_de_uso --por-origem  # cadastros e ativos de cada origem, semana em curso

Só contagens (ativos por semana, relatórios gerados, PDFs entregues); nenhum e-mail aparece.
Roda no servidor, uma vez por semana; a sessão da Diretoria grava a saída na Central
(`ArtifactData`, ver `central-tickerlab.md`). Não mexe no banco (só lê).

Roda: cron do VPS pelo painel-de-uso.sh (toda segunda às 8h45).
"""

import argparse
import json
import logging
import sys
from datetime import UTC, datetime

import sqlalchemy as sa

from src import painel_de_uso
from src.banco.conexao import criar_engine
from src.configuracao import url_do_banco

log = logging.getLogger("tickerlab.painel_de_uso")


def _ler_argumentos() -> argparse.Namespace:
    leitor = argparse.ArgumentParser(description="Números de uso da semana, em JSON.")
    leitor.add_argument(
        "--por-origem",
        action="store_true",
        help="cadastros e ativos de cada origem do cadastro, na semana em curso",
    )
    return leitor.parse_args(sys.argv[1:])


def _numeros(conexao: sa.Connection, por_origem: bool) -> list[dict]:
    if por_origem:
        segunda = painel_de_uso.segunda_da_semana(datetime.now(UTC).date())
        return painel_de_uso.ativos_por_origem(conexao, segunda)
    return painel_de_uso.historico(conexao)


def main() -> int:
    argumentos = _ler_argumentos()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    motor = criar_engine(url_do_banco())
    try:
        with motor.connect() as conexao:
            numeros = _numeros(conexao, argumentos.por_origem)
    except sa.exc.SQLAlchemyError as erro:
        log.error("Painel de uso interrompido: %s", erro.__class__.__name__)
        return 1
    finally:
        motor.dispose()
    print(json.dumps(numeros, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
