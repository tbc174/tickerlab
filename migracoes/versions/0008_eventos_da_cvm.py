"""eventos públicos da CVM (IPE) e o mapa ticker → CNPJ (FCA) para o Research

Revisão: 0008

Dados públicos, iguais para todos os usuários: nenhuma coluna pessoal. Cada evento guarda a data
em que ficou público, a data de referência, a versão da entrega e o link do documento original.
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tickers_dos_emissores",
        sa.Column("ticker", sa.String(12), nullable=False),
        sa.Column("codigo", sa.String(8), nullable=False),
        sa.Column("cnpj", sa.String(18), nullable=False),
        sa.Column("empresa", sa.String(200), nullable=False),
        sa.Column("valor_mobiliario", sa.String(80), nullable=False, server_default=""),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("ticker", name="pk_tickers_dos_emissores"),
    )
    op.create_index("ix_tickers_dos_emissores_cnpj", "tickers_dos_emissores", ["cnpj"])
    op.create_table(
        "eventos",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("fonte", sa.String(20), nullable=False),
        sa.Column("protocolo", sa.String(60), nullable=False),
        sa.Column("versao", sa.Integer, nullable=False, server_default="1"),
        sa.Column("cnpj", sa.String(18), nullable=False),
        sa.Column("empresa", sa.String(200), nullable=False),
        sa.Column("categoria", sa.String(160), nullable=False),
        sa.Column("tipo", sa.String(300), nullable=False, server_default=""),
        sa.Column("assunto", sa.Text, nullable=False, server_default=""),
        sa.Column("rotulo", sa.String(60), nullable=False),
        sa.Column("tema", sa.String(20), nullable=False),
        sa.Column("materialidade", sa.Integer, nullable=False),
        sa.Column("referencia", sa.Date),
        sa.Column("publicado_em", sa.Date, nullable=False),
        sa.Column("link", sa.String(500), nullable=False),
        sa.Column(
            "ingerido_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_eventos"),
        sa.UniqueConstraint("fonte", "protocolo", name="uq_eventos_fonte_protocolo"),
    )
    op.create_index("ix_eventos_cnpj_publicado_em", "eventos", ["cnpj", "publicado_em"])


def downgrade() -> None:
    op.drop_index("ix_eventos_cnpj_publicado_em", table_name="eventos")
    op.drop_table("eventos")
    op.drop_index("ix_tickers_dos_emissores_cnpj", table_name="tickers_dos_emissores")
    op.drop_table("tickers_dos_emissores")
