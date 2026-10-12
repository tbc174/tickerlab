"""demonstrações financeiras da CVM (DFP e ITR) para os fundamentos do Research

Revisão: 0010

Dados públicos (nada pessoal): as contas-chave de cada documento, o índice dos documentos (data
de entrega e link) e o setor de cada companhia.
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demonstracoes",
        sa.Column("cnpj", sa.String(18), nullable=False),
        sa.Column("documento", sa.String(3), nullable=False),
        sa.Column("referencia", sa.Date, nullable=False),
        sa.Column("periodo", sa.String(20), nullable=False),
        sa.Column("fim", sa.Date, nullable=False),
        sa.Column("conta", sa.String(30), nullable=False),
        sa.Column("inicio", sa.Date),
        sa.Column("versao", sa.Integer, nullable=False),
        sa.Column("valor", sa.Float, nullable=False),
        sa.PrimaryKeyConstraint(
            "cnpj",
            "documento",
            "referencia",
            "periodo",
            "fim",
            "conta",
            name="pk_demonstracoes",
        ),
    )
    op.create_table(
        "documentos_financeiros",
        sa.Column("cnpj", sa.String(18), nullable=False),
        sa.Column("documento", sa.String(3), nullable=False),
        sa.Column("referencia", sa.Date, nullable=False),
        sa.Column("versao", sa.Integer, nullable=False),
        sa.Column("empresa", sa.String(200), nullable=False),
        sa.Column("recebido_em", sa.Date),
        sa.Column("link", sa.String(500), nullable=False),
        sa.Column(
            "coletado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint(
            "cnpj", "documento", "referencia", name="pk_documentos_financeiros"
        ),
    )
    op.create_table(
        "setores_cvm",
        sa.Column("cnpj", sa.String(18), nullable=False),
        sa.Column("setor", sa.String(120), nullable=False),
        sa.PrimaryKeyConstraint("cnpj", name="pk_setores_cvm"),
    )


def downgrade() -> None:
    op.drop_table("setores_cvm")
    op.drop_table("documentos_financeiros")
    op.drop_table("demonstracoes")
