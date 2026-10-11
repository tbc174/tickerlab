"""auditoria e aceite dos termos de uso

Revisão: 0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

JSON_PORTATIL = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column("usuarios", sa.Column("termos_versao", sa.String(20)))
    op.add_column(
        "usuarios", sa.Column("termos_aceitos_em", sa.DateTime(timezone=True))
    )
    op.create_table(
        "auditoria",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("ator_id", sa.Uuid),
        sa.Column("acao", sa.String(60), nullable=False),
        sa.Column("alvo_id", sa.Uuid),
        sa.Column("detalhes", JSON_PORTATIL, nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_auditoria"),
        sa.ForeignKeyConstraint(
            ["ator_id"],
            ["usuarios.id"],
            name="fk_auditoria_ator_id_usuarios",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_auditoria_criado_em", "auditoria", ["criado_em"])


def downgrade() -> None:
    op.drop_index("ix_auditoria_criado_em", table_name="auditoria")
    op.drop_table("auditoria")
    op.drop_column("usuarios", "termos_aceitos_em")
    op.drop_column("usuarios", "termos_versao")
