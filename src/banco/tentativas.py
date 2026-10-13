"""As tentativas de cada pessoa no backtest: quantas configurações diferentes ela rodou num ativo.

Alimenta o contador da ficha "Foi sorte?" (ADR 0037, D2). Dado da pessoa: toda consulta filtra
por `usuario_id`, sai na exportação dos dados e é apagado junto com a conta (cascata).
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite

from src.banco.modelo import tentativas
from src.tentativas import TETO_POR_PESSOA

_INSERT_DO_BANCO = {"postgresql": postgresql.insert, "sqlite": sqlite.insert}


def _total_da_pessoa(conexao: sa.Connection, usuario_id: uuid.UUID) -> int:
    return conexao.execute(
        sa.select(sa.func.count())
        .select_from(tentativas)
        .where(tentativas.c.usuario_id == usuario_id)
    ).scalar_one()


def registrar_tentativa(
    conexao: sa.Connection, usuario_id: uuid.UUID, ticker: str, impressao: str
) -> None:
    """Guarda a configuração, se for nova para a pessoa neste ativo e o teto não tiver chegado.

    Repetida não conta de novo, nem com duas abas gravando ao mesmo tempo (ON CONFLICT DO NOTHING).
    """
    if _total_da_pessoa(conexao, usuario_id) >= TETO_POR_PESSOA:
        return
    inserir = _INSERT_DO_BANCO[conexao.dialect.name]
    conexao.execute(
        inserir(tentativas)
        .values(usuario_id=usuario_id, ticker=ticker, impressao=impressao)
        .on_conflict_do_nothing()
    )


def contar_tentativas(
    conexao: sa.Connection, usuario_id: uuid.UUID, ticker: str
) -> int:
    """Quantas configurações diferentes a pessoa já rodou neste ativo."""
    return conexao.execute(
        sa.select(sa.func.count())
        .select_from(tentativas)
        .where(tentativas.c.usuario_id == usuario_id, tentativas.c.ticker == ticker)
    ).scalar_one()


def contar_por_ativo(conexao: sa.Connection, usuario_id: uuid.UUID) -> dict[str, int]:
    """A contagem de cada ativo da pessoa (para a exportação dos dados)."""
    linhas = conexao.execute(
        sa.select(tentativas.c.ticker, sa.func.count())
        .where(tentativas.c.usuario_id == usuario_id)
        .group_by(tentativas.c.ticker)
        .order_by(tentativas.c.ticker)
    )
    return {ticker: total for ticker, total in linhas}
