"""relatórios em PDF gerados (para o limite do plano)

Revisão: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "relatorios",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_relatorios"),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name="fk_relatorios_usuario_id_usuarios",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "tipo IN ('ativo', 'comparacao', 'backtest', 'carteira', 'minha_carteira')",
            name="ck_relatorios_tipo",
        ),
    )
    op.create_index(
        "ix_relatorios_usuario_id_criado_em", "relatorios", ["usuario_id", "criado_em"]
    )


def downgrade() -> None:
    op.drop_index("ix_relatorios_usuario_id_criado_em", table_name="relatorios")
    op.drop_table("relatorios")
