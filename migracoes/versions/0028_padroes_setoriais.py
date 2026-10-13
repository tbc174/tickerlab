"""Padrões por setor das notas (série 2 da base de ML, PR 4; ADR 0033 do autor)

Revisão: 0028

Os percentis de cada indicador por grupo de setores, numa data de corte, calculados só com o que era
público até ela (`src/padroes.py`). Dado derivado e público. Só cria uma tabela nova: nada do que
existe muda.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "padroes_setoriais",
        sa.Column("data_de_corte", sa.Date, primary_key=True),
        sa.Column("grupo", sa.String(30), primary_key=True),
        sa.Column("indicador", sa.String(40), primary_key=True),
        sa.Column("versao", sa.String(10), primary_key=True),
        sa.Column("empresas", sa.Integer, nullable=False),
        sa.Column(
            "percentis", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("calculado_em", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("padroes_setoriais")
