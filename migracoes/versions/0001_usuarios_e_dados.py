"""usuários, preferências, favoritos e simulações

Revisão: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

JSON_PORTATIL = sa.JSON().with_variant(JSONB(), "postgresql")


def _momento(nome: str) -> sa.Column:
    return sa.Column(
        nome, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def _chave_estrangeira(tabela: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["usuario_id"],
        ["usuarios.id"],
        name=f"fk_{tabela}_usuario_id_usuarios",
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("google_sub", sa.String(64), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("nome", sa.String(200)),
        sa.Column("foto_url", sa.String(1000)),
        sa.Column("papel", sa.String(20), nullable=False, server_default="usuario"),
        sa.Column("plano", sa.String(20), nullable=False, server_default="gratuito"),
        _momento("criado_em"),
        sa.Column("ultimo_acesso", sa.DateTime(timezone=True)),
        sa.Column("excluido_em", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_usuarios"),
        sa.UniqueConstraint("google_sub", name="uq_usuarios_google_sub"),
        sa.CheckConstraint("papel IN ('usuario', 'admin')", name="ck_usuarios_papel"),
        sa.CheckConstraint("plano IN ('gratuito', 'pro')", name="ck_usuarios_plano"),
    )
    op.create_index("ix_usuarios_email", "usuarios", ["email"])

    op.create_table(
        "preferencias",
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.Column("dados", JSON_PORTATIL, nullable=False),
        _momento("atualizado_em"),
        sa.PrimaryKeyConstraint("usuario_id", name="pk_preferencias"),
        _chave_estrangeira("preferencias"),
    )

    op.create_table(
        "favoritos",
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("ordem", sa.Integer, nullable=False, server_default="0"),
        _momento("criado_em"),
        sa.PrimaryKeyConstraint("usuario_id", "ticker", name="pk_favoritos"),
        _chave_estrangeira("favoritos"),
    )

    op.create_table(
        "simulacoes",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("parametros", JSON_PORTATIL, nullable=False),
        sa.Column("resultado", JSON_PORTATIL, nullable=False),
        _momento("criada_em"),
        sa.PrimaryKeyConstraint("id", name="pk_simulacoes"),
        _chave_estrangeira("simulacoes"),
    )
    op.create_index("ix_simulacoes_usuario_id", "simulacoes", ["usuario_id"])


def downgrade() -> None:
    op.drop_index("ix_simulacoes_usuario_id", table_name="simulacoes")
    op.drop_table("simulacoes")
    op.drop_table("favoritos")
    op.drop_table("preferencias")
    op.drop_index("ix_usuarios_email", table_name="usuarios")
    op.drop_table("usuarios")
