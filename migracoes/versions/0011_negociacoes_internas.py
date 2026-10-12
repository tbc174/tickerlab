"""negociações de pessoas de dentro (CVM VLMO e SEC Form 4) e documentos já lidos

Revisão: 0011

Dados públicos. Das pessoas guardamos só o cargo, nunca o nome (decisão 0018).
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "negociacoes_internas",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("fonte", sa.String(20), nullable=False),
        sa.Column("documento", sa.String(60), nullable=False),
        sa.Column("versao", sa.Integer, nullable=False),
        sa.Column("cnpj", sa.String(18), nullable=False),
        sa.Column("empresa", sa.String(200), nullable=False),
        sa.Column("cargo", sa.String(20), nullable=False),
        sa.Column("cargo_descricao", sa.String(120), nullable=False, server_default=""),
        sa.Column("operacao", sa.String(10), nullable=False),
        sa.Column("ativo", sa.String(80), nullable=False, server_default=""),
        sa.Column("data", sa.Date),
        sa.Column("referencia", sa.Date, nullable=False),
        sa.Column("entregue_em", sa.Date, nullable=False),
        sa.Column("quantidade", sa.Float, nullable=False),
        sa.Column("preco", sa.Float),
        sa.Column("valor", sa.Float),
        sa.Column("moeda", sa.String(3), nullable=False),
        sa.Column("plano_10b5_1", sa.Boolean),
        sa.Column("link", sa.String(500), nullable=False),
        sa.Column(
            "ingerido_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_negociacoes_internas"),
    )
    op.create_index(
        "ix_negociacoes_internas_cnpj_data",
        "negociacoes_internas",
        ["cnpj", "entregue_em"],
    )
    op.create_index(
        "ix_negociacoes_internas_documento",
        "negociacoes_internas",
        ["fonte", "documento"],
    )
    op.create_table(
        "documentos_lidos",
        sa.Column("fonte", sa.String(20), nullable=False),
        sa.Column("documento", sa.String(60), nullable=False),
        sa.Column(
            "lido_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("fonte", "documento", name="pk_documentos_lidos"),
    )


def downgrade() -> None:
    op.drop_table("documentos_lidos")
    op.drop_index("ix_negociacoes_internas_documento", "negociacoes_internas")
    op.drop_index("ix_negociacoes_internas_cnpj_data", "negociacoes_internas")
    op.drop_table("negociacoes_internas")
