"""De onde veio cada cadastro: as UTMs e o `ref` lidos do cookie `tl_origem` (src/origem.py).

Mede a campanha de lançamento sem pixel de terceiros (ADR 0051; `campanha-medicao.md`). Só a
**primeira** origem de cada pessoa fica guardada. Dado da pessoa: toda consulta filtra por
`usuario_id`, sai na exportação dos dados e é apagado junto com a conta (cascata).
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite

from src.banco.modelo import origens_do_cadastro
from src.origem import Origem

_INSERT_DO_BANCO = {"postgresql": postgresql.insert, "sqlite": sqlite.insert}


def gravar_origem(
    conexao: sa.Connection, usuario_id: uuid.UUID, origem: Origem
) -> bool:
    """Guarda a origem se a pessoa ainda não tiver uma. Devolve se gravou.

    Nunca sobrescreve, nem com duas abas gravando ao mesmo tempo (ON CONFLICT DO NOTHING).
    """
    inserir = _INSERT_DO_BANCO[conexao.dialect.name]
    resultado = conexao.execute(
        inserir(origens_do_cadastro)
        .values(
            usuario_id=usuario_id,
            utm_source=origem.source,
            utm_medium=origem.medium,
            utm_campaign=origem.campaign,
            utm_content=origem.content,
            ref=origem.ref,
            primeira_visita=origem.primeira_visita,
        )
        .on_conflict_do_nothing()
    )
    return resultado.rowcount > 0


def buscar_linha(conexao: sa.Connection, usuario_id: uuid.UUID) -> sa.Row | None:
    """A linha guardada da pessoa, com `gravada_em` (para a exportação dos dados)."""
    return conexao.execute(
        sa.select(origens_do_cadastro).where(
            origens_do_cadastro.c.usuario_id == usuario_id
        )
    ).first()


def buscar_origem(conexao: sa.Connection, usuario_id: uuid.UUID) -> Origem | None:
    """A origem do cadastro da pessoa, ou `None` se ela não veio por um link marcado."""
    linha = buscar_linha(conexao, usuario_id)
    if linha is None:
        return None
    return Origem(
        source=linha.utm_source,
        medium=linha.utm_medium,
        campaign=linha.utm_campaign,
        content=linha.utm_content,
        ref=linha.ref,
        primeira_visita=linha.primeira_visita,
    )
