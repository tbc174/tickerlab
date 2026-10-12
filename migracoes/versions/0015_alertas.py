"""alertas compostos do Research: as regras de cada usuário

Revisão: 0015

Dado do usuário (apagado junto com a conta, pela chave estrangeira em cascata, e incluído na
exportação dos dados).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alertas",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.Column("nome", sa.String(80), nullable=False),
        sa.Column(
            "regra", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False
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
        sa.PrimaryKeyConstraint("id", name="pk_alertas"),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name="fk_alertas_usuario_id_usuarios",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("usuario_id", "nome", name="uq_alertas_usuario_id_nome"),
    )


def downgrade() -> None:
    op.drop_table("alertas")
