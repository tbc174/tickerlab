"""quem tem cada ação: fundos da CVM (CDA) e gestores da SEC (13F)

Revisão: 0012

Dados públicos. Nomes de fundos e gestores são de pessoas jurídicas.
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "detentores_por_acao",
        sa.Column("fonte", sa.String(20), nullable=False),
        sa.Column("competencia", sa.Date, nullable=False),
        sa.Column("codigo", sa.String(12), nullable=False),
        sa.Column("detentores", sa.Integer, nullable=False),
        sa.Column("valor", sa.Float, nullable=False),
        sa.Column("quantidade", sa.Float, nullable=False),
        sa.Column("vendidos", sa.Integer, nullable=False),
        sa.Column("valor_vendido", sa.Float, nullable=False),
        sa.Column("valor_emprestado", sa.Float, nullable=False),
        sa.Column("compras_no_mes", sa.Float, nullable=False),
        sa.Column("vendas_no_mes", sa.Float, nullable=False),
        sa.Column(
            "coletado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint(
            "fonte", "competencia", "codigo", name="pk_detentores_por_acao"
        ),
    )
    op.create_table(
        "maiores_detentores",
        sa.Column("fonte", sa.String(20), nullable=False),
        sa.Column("competencia", sa.Date, nullable=False),
        sa.Column("codigo", sa.String(12), nullable=False),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("posicao", sa.Integer, nullable=False),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("documento", sa.String(20), nullable=False),
        sa.Column("valor", sa.Float, nullable=False),
        sa.Column("quantidade", sa.Float, nullable=False),
        sa.PrimaryKeyConstraint(
            "fonte", "competencia", "codigo", "tipo", "posicao", name="pk_maiores_detentores"
        ),
    )


    op.create_table(
        "cobertura_de_detentores",
        sa.Column("fonte", sa.String(20), nullable=False),
        sa.Column("competencia", sa.Date, nullable=False),
        sa.Column("informantes", sa.Integer, nullable=False),
        sa.Column(
            "coletado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("fonte", "competencia", name="pk_cobertura_de_detentores"),
    )


def downgrade() -> None:
    op.drop_table("cobertura_de_detentores")
    op.drop_table("maiores_detentores")
    op.drop_table("detentores_por_acao")
