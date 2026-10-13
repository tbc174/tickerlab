"""Recalcula os padrões por setor das notas (série 2 da base de ML, PR 4; ADR 0033).

    python -m scripts.atualizar_padroes                       (o fim do mês passado)
    python -m scripts.atualizar_padroes --desde 2021-01       (todo fim de mês desde jan/2021)
    python -m scripts.atualizar_padroes --datas 2025-12-31    (cortes escolhidos)

Roda no VPS uma vez por mês, num contêiner próprio (carrega as versões de todas as empresas). Para
cada corte, usa só o que era público até ele (`src/padroes.py`). Os padrões publicados na página de
metodologia são os de 31/12 de cada ano.
"""

import argparse
import logging
import sys
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import sqlalchemy as sa

from src.banco.conexao import criar_engine, migrar_para
from src.banco.padroes import calcular_corte, entradas_para_padroes, gravar_padroes
from src.configuracao import url_do_banco

log = logging.getLogger("tickerlab.padroes")
FUSO = ZoneInfo("America/Sao_Paulo")


def fim_do_mes_passado(hoje: date) -> date:
    return hoje.replace(day=1) - timedelta(days=1)


def fins_de_mes(desde: str, ate: date) -> list[date]:
    """Todo último dia de mês de `desde` (AAAA-MM) até `ate`."""
    inicio = pd.Period(desde, freq="M")
    return [
        p.end_time.date()
        for p in pd.period_range(inicio, ate, freq="M")
        if p.end_time.date() <= ate
    ]


def _cortes(opcoes: argparse.Namespace, hoje: date) -> list[date]:
    if opcoes.datas:
        return sorted(date.fromisoformat(d) for d in opcoes.datas)
    ultimo = fim_do_mes_passado(hoje)
    return fins_de_mes(opcoes.desde, ultimo) if opcoes.desde else [ultimo]


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--datas", nargs="+", help="cortes AAAA-MM-DD")
    argumentos.add_argument("--desde", help="todo fim de mês desde AAAA-MM")
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    cortes = _cortes(opcoes, datetime.now(FUSO).date())
    url = url_do_banco()
    migrar_para("head", url=url)
    motor = criar_engine(url)
    try:
        with motor.connect() as conexao:
            entradas = entradas_para_padroes(conexao)
        log.info(
            "%s versões de contas, %s empresas com setor",
            len(entradas.contas),
            len(entradas.setores),
        )
        for corte in cortes:
            padroes = calcular_corte(entradas, corte)
            with motor.begin() as conexao:
                gravados = gravar_padroes(conexao, padroes, corte, datetime.now(UTC))
            log.info("Corte %s: %s padrões (grupo e indicador)", corte, gravados)
    except (sa.exc.SQLAlchemyError, ValueError) as erro:
        log.error("Padrões interrompidos: %s", erro)
        return 1
    finally:
        motor.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
