"""Registro do que aconteceu de importante: ações de administrador, aceite dos termos, contas apagadas.

Só guarda ids e dados técnicos, nunca e-mail, nome ou foto. Assim o registro pode continuar
existindo depois que a conta da pessoa é apagada, sem manter dado pessoal.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa

from src.banco.modelo import auditoria

ACAO_PLANO_ALTERADO = "plano_alterado"
ACAO_PAPEL_ALTERADO = "papel_alterado"
ACAO_TERMOS_ACEITOS = "termos_aceitos"
ACAO_CONTA_APAGADA = "conta_apagada"
ACAO_DADOS_EXPORTADOS = "dados_exportados"
ACAO_CARTEIRA_CONSENTIDA = "carteira_consentida"  # Research, etapa 5 (decisão 0020)
ACAO_CARTEIRA_REVOGADA = "carteira_revogada"


@dataclass(frozen=True)
class Registro:
    id: uuid.UUID
    ator_id: uuid.UUID | None
    acao: str
    alvo_id: uuid.UUID | None
    detalhes: dict
    criado_em: datetime


def registrar(
    conexao: sa.Connection,
    ator_id: uuid.UUID | None,
    acao: str,
    alvo_id: uuid.UUID | None = None,
    detalhes: dict | None = None,
) -> None:
    conexao.execute(
        sa.insert(auditoria).values(
            id=uuid.uuid4(),
            ator_id=ator_id,
            acao=acao,
            alvo_id=alvo_id,
            detalhes=detalhes or {},
            criado_em=datetime.now(UTC),
        )
    )


def listar_recentes(conexao: sa.Connection, limite: int = 50) -> list[Registro]:
    linhas = conexao.execute(
        sa.select(auditoria).order_by(auditoria.c.criado_em.desc()).limit(limite)
    )
    return [
        Registro(
            id=l.id,
            ator_id=l.ator_id,
            acao=l.acao,
            alvo_id=l.alvo_id,
            detalhes=dict(l.detalhes),
            criado_em=l.criado_em,
        )
        for l in linhas
    ]
