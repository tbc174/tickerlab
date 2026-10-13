"""Registro de coletas das fontes oficiais (Radar e base histórica, PR 1; ADR 0024 do autor)

Revisão: 0021

Uma linha por arquivo baixado pelas coletas (CVM e SEC): fonte, endereço, horário, tamanho,
SHA-256, licença e situação (ok, não encontrado, falhou). É a "nota fiscal" de cada número do
acervo. Só dado público. Só cria uma tabela nova: nada do que existe muda.
"""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "coletas",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("fonte", sa.String(40), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("situacao", sa.String(20), nullable=False),
        sa.Column("bytes", sa.BigInteger),
        sa.Column("sha256", sa.String(64)),
        sa.Column("licenca", sa.String(80), nullable=False),
        sa.Column("detalhe", sa.String(300)),
        sa.Column(
            "baixado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "situacao IN ('ok', 'nao_encontrado', 'falhou')", name="ck_coletas_situacao"
        ),
    )
    op.create_index("ix_coletas_fonte_baixado_em", "coletas", ["fonte", "baixado_em"])


def downgrade() -> None:
    op.drop_index("ix_coletas_fonte_baixado_em", table_name="coletas")
    op.drop_table("coletas")
