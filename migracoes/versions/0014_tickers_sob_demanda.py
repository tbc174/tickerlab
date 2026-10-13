"""ações dos EUA buscadas na hora (Research R4), que passam a entrar na coleta diária da SEC

Revisão: 0014

Sem dado pessoal: só o ticker, o CIK e quando foi pedido.
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tickers_sob_demanda",
        sa.Column("ticker", sa.String(12), nullable=False),
        sa.Column("cnpj", sa.String(18), nullable=False),
        sa.Column(
            "pedido_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("ticker", name="pk_tickers_sob_demanda"),
    )


def downgrade() -> None:
    op.drop_table("tickers_sob_demanda")
