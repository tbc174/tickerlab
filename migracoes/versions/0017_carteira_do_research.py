"""carteira do Research (etapa 5): a fotografia dos pesos de cada usuário, com consentimento

Revisão: 0017

Dado do usuário, guardado só com consentimento próprio (decisão 0020): o código de cada ativo e
o peso em %, nunca quantidades nem valores. Apagado ao revogar e junto com a conta (chave
estrangeira em cascata); incluído na exportação dos dados.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "carteiras_do_research",
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.Column(
            "pesos", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("enviada_em", sa.Date, nullable=False),
        sa.Column("versao_do_consentimento", sa.String(20), nullable=False),
        sa.Column(
            "consentido_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("usuario_id", name="pk_carteiras_do_research"),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name="fk_carteiras_do_research_usuario_id_usuarios",
            ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("carteiras_do_research")
