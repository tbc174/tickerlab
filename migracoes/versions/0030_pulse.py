"""Pulse: a última visita de cada pessoa (onda 3, PR E; ADR 0046, atualização 2)

Revisão: 0030

Uma linha por pessoa: quando ela abriu o Pulse pela última vez (o "desde a última visita") e o
veredito da ficha "Foi sorte?" que ela já viu em cada estratégia salva. Dado do usuário: apagado
junto com a conta (chave estrangeira em cascata) e incluído na exportação dos dados. Só cria uma
tabela nova: nada do que existe muda.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

TABELA = "pulse"
JSON_PORTATIL = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        TABELA,
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.Column("visto_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("vereditos", JSON_PORTATIL, nullable=False),
        sa.PrimaryKeyConstraint("usuario_id", name="pk_pulse"),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name="fk_pulse_usuario_id_usuarios",
            ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table(TABELA)
