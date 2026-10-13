"""Séries macro com safras (Radar e base histórica, PR 5; ADR 0024 do autor)

Revisão: 0023

`series` (o catálogo: código, nome, unidade, frequência, licença e se é só de uso interno) e
`observacoes` (valor por data de referência e por safra, `divulgado_em`). Só acréscimo: uma
revisão oficial vira uma linha nova, e "como estava na data D" passa a ter resposta. Só dado
público. Só cria tabelas novas: nada do que existe muda.
"""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "series",
        sa.Column("codigo", sa.String(60), primary_key=True),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("unidade", sa.String(40), nullable=False),
        sa.Column("frequencia", sa.String(20), nullable=False),
        sa.Column("licenca", sa.String(80), nullable=False),
        sa.Column(
            "uso_interno", sa.Boolean, nullable=False, server_default=sa.false()
        ),
    )
    op.create_table(
        "observacoes",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "serie",
            sa.String(60),
            sa.ForeignKey("series.codigo", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("referencia", sa.Date, nullable=False),
        sa.Column("valor", sa.Float, nullable=False),
        sa.Column("divulgado_em", sa.Date, nullable=False),
        sa.Column(
            "registrado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_observacoes_serie_referencia",
        "observacoes",
        ["serie", "referencia", "divulgado_em"],
    )


def downgrade() -> None:
    op.drop_index("ix_observacoes_serie_referencia", table_name="observacoes")
    op.drop_table("observacoes")
    op.drop_table("series")
