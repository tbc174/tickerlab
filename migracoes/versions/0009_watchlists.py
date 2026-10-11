"""watchlists do Research: listas com nome de cada usuário

Revisão: 0009
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlists",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.Column("nome", sa.String(60), nullable=False),
        sa.Column(
            "tickers", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False
        ),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_watchlists"),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name="fk_watchlists_usuario_id_usuarios",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("usuario_id", "nome", name="uq_watchlists_usuario_id_nome"),
    )


def downgrade() -> None:
    op.drop_table("watchlists")
