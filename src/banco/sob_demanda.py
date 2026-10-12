"""Ações dos EUA buscadas na hora (Research R4): registro e consultas.

Quando alguém abre uma ação dos EUA que não está no S&P 500, o app busca a empresa na SEC e grava:
o ticker no mapa (`tickers_dos_emissores`, com o CIK no lugar do CNPJ) e na lista das buscadas
sob demanda, que a coleta diária passa a incluir. Nada pessoal: não se guarda quem pediu.
"""

from datetime import UTC, datetime

import sqlalchemy as sa

from src.banco.modelo import tickers_dos_emissores, tickers_sob_demanda

VALOR_MOBILIARIO = "Ação (EUA)"


def registrar(
    conexao: sa.Connection, ticker: str, cik_com_prefixo: str, empresa: str
) -> None:
    """Põe a ação no mapa ticker → empresa e na lista das buscadas sob demanda."""
    agora = datetime.now(UTC)
    for tabela in (tickers_dos_emissores, tickers_sob_demanda):
        conexao.execute(sa.delete(tabela).where(tabela.c.ticker == ticker))
    conexao.execute(
        sa.insert(tickers_dos_emissores).values(
            ticker=ticker,
            codigo=ticker[:8],
            cnpj=cik_com_prefixo,
            empresa=empresa[:200],
            valor_mobiliario=VALOR_MOBILIARIO,
            atualizado_em=agora,
        )
    )
    conexao.execute(
        sa.insert(tickers_sob_demanda).values(
            ticker=ticker, cnpj=cik_com_prefixo, pedido_em=agora
        )
    )


def tickers(conexao: sa.Connection) -> set[str]:
    """Todos os tickers buscados sob demanda (a coleta diária inclui estes)."""
    return set(conexao.execute(sa.select(tickers_sob_demanda.c.ticker)).scalars())


def pedidos_desde(conexao: sa.Connection, desde: datetime) -> int:
    """Quantas buscas novas desde `desde` (para o limite por hora, que protege a SEC)."""
    consulta = sa.select(sa.func.count()).where(
        tickers_sob_demanda.c.pedido_em >= desde
    )
    return int(conexao.execute(consulta).scalar() or 0)
