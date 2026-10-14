"""Diário de Teses: anotações datadas da pessoa sobre cada ativo (onda 3, PR F; ADR 0046)

Revisão: 0032

Duas tabelas novas: `teses` (uma linha por anotação; não se edita, só se apaga) e
`teses_estrategias` (os backtests salvos que sustentam cada anotação). Dado do usuário: apagado
junto com a conta (chave estrangeira em cascata) e incluído na exportação dos dados. Apagar um
backtest apaga só a ligação, nunca a anotação. Nada do que existe muda.
"""

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

TAMANHO_MAXIMO_DA_TESE = 2000


def upgrade() -> None:
    op.create_table(
        "teses",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("texto", sa.Text, nullable=False),
        sa.Column(
            "criada_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_teses"),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name="fk_teses_usuario_id_usuarios",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"length(texto) BETWEEN 1 AND {TAMANHO_MAXIMO_DA_TESE}",
            name="ck_teses_texto",
        ),
    )
    op.create_index("ix_teses_usuario_id_ticker", "teses", ["usuario_id", "ticker"])
    op.create_table(
        "teses_estrategias",
        sa.Column("tese_id", sa.Uuid, nullable=False),
        sa.Column("simulacao_id", sa.Uuid, nullable=False),
        sa.PrimaryKeyConstraint("tese_id", "simulacao_id", name="pk_teses_estrategias"),
        sa.ForeignKeyConstraint(
            ["tese_id"],
            ["teses.id"],
            name="fk_teses_estrategias_tese_id_teses",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["simulacao_id"],
            ["simulacoes.id"],
            name="fk_teses_estrategias_simulacao_id_simulacoes",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_teses_estrategias_simulacao_id", "teses_estrategias", ["simulacao_id"]
    )


def downgrade() -> None:
    op.drop_table("teses_estrategias")
    op.drop_table("teses")
