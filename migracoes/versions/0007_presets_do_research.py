"""presets do Research: parâmetros por usuário, escopo e versão

Revisão: 0007

Cada linha é uma versão. Mudar os parâmetros cria a versão seguinte; voltar a uma versão antiga
também cria uma nova (com os valores da antiga). Assim, todo resultado calculado com uma versão
continua reprodutível e o histórico mostra quando e o que mudou.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "presets",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.Column("escopo", sa.String(20), nullable=False),
        sa.Column("alvo", sa.String(40), nullable=False, server_default=""),
        sa.Column("versao", sa.Integer, nullable=False),
        sa.Column("nome", sa.String(80), nullable=False, server_default=""),
        sa.Column(
            "parametros", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("motivo", sa.String(200), nullable=False, server_default=""),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_presets"),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name="fk_presets_usuario_id_usuarios",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "escopo IN ('global', 'watchlist', 'ativo')", name="ck_presets_escopo"
        ),
        sa.CheckConstraint("versao >= 1", name="ck_presets_versao"),
        sa.UniqueConstraint(
            "usuario_id",
            "escopo",
            "alvo",
            "versao",
            name="uq_presets_usuario_id_escopo_alvo_versao",
        ),
    )


def downgrade() -> None:
    op.drop_table("presets")
