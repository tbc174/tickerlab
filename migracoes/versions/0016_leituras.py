"""leitura dos documentos (Research R5): resumos de fatos relevantes e fatores de risco dos 10-K

Revisão: 0016

Dados públicos, produzidos pelo algoritmo próprio de `src/leitura.py` (sem IA).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leituras",
        sa.Column("fonte", sa.String(20), nullable=False),
        sa.Column("documento", sa.String(60), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("cnpj", sa.String(18), nullable=False),
        sa.Column("referencia", sa.Date),
        sa.Column(
            "resultado", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("versao", sa.String(10), nullable=False),
        sa.Column(
            "lido_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("fonte", "documento", "tipo", name="pk_leituras"),
    )
    op.create_index("ix_leituras_cnpj", "leituras", ["cnpj"])


def downgrade() -> None:
    op.drop_index("ix_leituras_cnpj", "leituras")
    op.drop_table("leituras")
