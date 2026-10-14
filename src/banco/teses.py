"""O Diário de Teses de cada pessoa no banco (onda 3, PR F).

Dado da pessoa: toda consulta filtra por `usuario_id`, sai na exportação dos dados e é apagado
junto com a conta (cascata). Uma anotação não se edita; apagar um backtest apaga só a ligação.
As regras (texto, ativo, tetos, o que pode ser ligado) ficam em `src/diario_de_teses.py`.
"""

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

import sqlalchemy as sa

from src import diario_de_teses as diario
from src.banco.modelo import simulacoes, teses, teses_estrategias


def _com_fuso(momento: datetime) -> datetime:
    # o SQLite devolve a hora sem fuso: ela foi gravada em UTC
    return momento if momento.tzinfo is not None else momento.replace(tzinfo=UTC)


def contar(conexao: sa.Connection, usuario_id: uuid.UUID) -> int:
    return conexao.execute(
        sa.select(sa.func.count())
        .select_from(teses)
        .where(teses.c.usuario_id == usuario_id)
    ).scalar_one()


def _conferir_estrategias(
    conexao: sa.Connection, usuario_id: uuid.UUID, ticker: str, ids: Iterable[uuid.UUID]
) -> tuple[uuid.UUID, ...]:
    """Os ids sem repetir, se todos forem backtests salvos desta pessoa e deste ativo."""
    unicos = tuple(sorted(set(ids)))  # a mesma ordem em que `listar` as lê
    if len(unicos) > diario.MAXIMO_DE_ESTRATEGIAS:
        raise diario.TeseInvalidaError(
            f"Ligue no máximo {diario.MAXIMO_DE_ESTRATEGIAS} backtests a uma anotação."
        )
    if not unicos:
        return ()
    salvas = conexao.execute(
        sa.select(simulacoes.c.tipo, simulacoes.c.parametros).where(
            simulacoes.c.id.in_(unicos), simulacoes.c.usuario_id == usuario_id
        )
    ).all()
    if len(salvas) != len(unicos) or len(
        diario.backtests_que_podem_ser_ligados(ticker, salvas)
    ) != len(unicos):
        raise diario.TeseInvalidaError(
            f"Só dá para ligar backtests que você salvou de {ticker.removesuffix('.SA')}."
        )
    return unicos


def escrever(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    ticker: str,
    texto: str,
    estrategias: Iterable[uuid.UUID] = (),
) -> diario.Anotacao:
    """Guarda uma anotação nova (e as ligações com os backtests). Recusa o que as regras recusam."""
    ticker = diario.ticker_da_tese(ticker)
    texto = diario.limpar_texto(texto)
    ligadas = _conferir_estrategias(conexao, usuario_id, ticker, estrategias)
    if contar(conexao, usuario_id) >= diario.MAXIMO_DE_ANOTACOES:
        raise diario.TeseInvalidaError(
            f"O diário guarda até {diario.MAXIMO_DE_ANOTACOES} anotações. "
            "Apague as que não servem mais para escrever outras."
        )
    anotacao = diario.Anotacao(uuid.uuid4(), ticker, texto, datetime.now(UTC), ligadas)
    conexao.execute(
        sa.insert(teses).values(
            id=anotacao.id,
            usuario_id=usuario_id,
            ticker=ticker,
            texto=texto,
            criada_em=anotacao.criada_em,
        )
    )
    if ligadas:
        conexao.execute(
            sa.insert(teses_estrategias),
            [{"tese_id": anotacao.id, "simulacao_id": s} for s in ligadas],
        )
    return anotacao


def listar(conexao: sa.Connection, usuario_id: uuid.UUID) -> list[diario.Anotacao]:
    """As anotações da pessoa, da mais nova para a mais antiga, com os backtests ligados."""
    linhas = conexao.execute(
        sa.select(teses)
        .where(teses.c.usuario_id == usuario_id)
        .order_by(teses.c.criada_em.desc(), teses.c.id)
    ).all()
    ligadas: dict[uuid.UUID, list[uuid.UUID]] = {}
    for tese_id, simulacao_id in conexao.execute(
        sa.select(teses_estrategias.c.tese_id, teses_estrategias.c.simulacao_id)
        .join(teses, teses.c.id == teses_estrategias.c.tese_id)
        .where(teses.c.usuario_id == usuario_id)
        .order_by(teses_estrategias.c.simulacao_id)
    ):
        ligadas.setdefault(tese_id, []).append(simulacao_id)
    return [
        diario.Anotacao(
            l.id,
            l.ticker,
            l.texto,
            _com_fuso(l.criada_em),
            tuple(ligadas.get(l.id, ())),
        )
        for l in linhas
    ]


def apagar(conexao: sa.Connection, usuario_id: uuid.UUID, tese_id: uuid.UUID) -> bool:
    """Apaga a anotação se for desta pessoa. Devolve se havia o que apagar."""
    resultado = conexao.execute(
        sa.delete(teses).where(teses.c.id == tese_id, teses.c.usuario_id == usuario_id)
    )
    return resultado.rowcount > 0


def dados_para_exportar(conexao: sa.Connection, usuario_id: uuid.UUID) -> list[dict]:
    """O diário para a exportação dos dados: texto, data e o nome dos backtests ligados."""
    nomes = dict(
        conexao.execute(
            sa.select(simulacoes.c.id, simulacoes.c.nome).where(
                simulacoes.c.usuario_id == usuario_id
            )
        ).all()
    )
    return [
        {
            "ticker": a.ticker,
            "texto": a.texto,
            "criada_em": a.criada_em.isoformat(),
            "estrategias": sorted(nomes[s] for s in a.estrategias if s in nomes),
        }
        for a in listar(conexao, usuario_id)
    ]
