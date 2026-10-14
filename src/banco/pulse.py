"""O Pulse de cada pessoa: quando ela o abriu pela última vez e os vereditos que viu (onda 3, PR E).

Dado da pessoa: toda consulta filtra por `usuario_id`, sai na exportação dos dados e é apagado
junto com a conta (cascata).
"""

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite

from src.banco.modelo import pulse

_INSERT_DO_BANCO = {"postgresql": postgresql.insert, "sqlite": sqlite.insert}
TAMANHO_MAXIMO_DO_ID = 64  # id da simulação salva (UUID em texto)
TAMANHO_MAXIMO_DO_VEREDITO = 40


def _com_fuso(momento: datetime) -> datetime:
    # o SQLite devolve a hora sem fuso: ela foi gravada em UTC
    return momento if momento.tzinfo is not None else momento.replace(tzinfo=UTC)


def ultima_visita(conexao: sa.Connection, usuario_id: uuid.UUID) -> datetime | None:
    """Quando a pessoa abriu o Pulse pela última vez (None: nunca abriu)."""
    visto_em = conexao.execute(
        sa.select(pulse.c.visto_em).where(pulse.c.usuario_id == usuario_id)
    ).scalar_one_or_none()
    return None if visto_em is None else _com_fuso(visto_em)


def marcar_visita(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    quando: datetime,
    vereditos: Mapping[str, str] | None = None,
) -> None:
    """Guarda a visita; uma mais velha (outra aba que abriu antes) não volta o relógio.

    `vereditos` (id da simulação salva → veredito da ficha visto agora) substitui os guardados
    junto com a hora; sem ele, os guardados ficam como estão.
    """
    if quando.tzinfo is None:
        raise ValueError("A hora da visita precisa ter fuso.")
    novos: dict = {"visto_em": quando}
    if vereditos is not None:
        novos["vereditos"] = dict(vereditos)
    inserir = _INSERT_DO_BANCO[conexao.dialect.name]
    conexao.execute(
        inserir(pulse)
        .values({"usuario_id": usuario_id, "vereditos": {}, **novos})
        .on_conflict_do_update(
            index_elements=[pulse.c.usuario_id],
            set_=novos,
            where=pulse.c.visto_em < quando,
        )
    )


def vereditos_vistos(conexao: sa.Connection, usuario_id: uuid.UUID) -> dict[str, str]:
    """Os vereditos que a pessoa viu na última visita. Vêm do banco: só texto curto volta."""
    guardados = conexao.execute(
        sa.select(pulse.c.vereditos).where(pulse.c.usuario_id == usuario_id)
    ).scalar_one_or_none()
    if not isinstance(guardados, Mapping):
        return {}
    return {
        chave: valor
        for chave, valor in guardados.items()
        if isinstance(chave, str)
        and isinstance(valor, str)
        and len(chave) <= TAMANHO_MAXIMO_DO_ID
        and len(valor) <= TAMANHO_MAXIMO_DO_VEREDITO
    }


def dados_para_exportar(conexao: sa.Connection, usuario_id: uuid.UUID) -> dict | None:
    """O Pulse da pessoa para a exportação dos dados (None: nunca abriu)."""
    linha = conexao.execute(
        sa.select(pulse.c.visto_em, pulse.c.vereditos).where(
            pulse.c.usuario_id == usuario_id
        )
    ).first()
    if linha is None:
        return None
    return {
        "visto_em": _com_fuso(linha.visto_em).isoformat(),
        "vereditos": dict(linha.vereditos),
    }
