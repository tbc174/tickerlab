"""assinaturas e eventos do Stripe

Revisão: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _momento(nome: str) -> sa.Column:
    return sa.Column(
        nome, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def upgrade() -> None:
    op.create_table(
        "assinaturas",
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.Column("stripe_customer_id", sa.String(64), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(64)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("periodo_fim", sa.DateTime(timezone=True)),
        sa.Column(
            "cancela_no_fim", sa.Boolean, nullable=False, server_default=sa.false()
        ),
        sa.Column("evento_em", sa.BigInteger, nullable=False, server_default="0"),
        _momento("atualizada_em"),
        sa.PrimaryKeyConstraint("usuario_id", name="pk_assinaturas"),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name="fk_assinaturas_usuario_id_usuarios",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "stripe_customer_id", name="uq_assinaturas_stripe_customer_id"
        ),
        sa.UniqueConstraint(
            "stripe_subscription_id", name="uq_assinaturas_stripe_subscription_id"
        ),
    )
    op.create_table(
        "eventos_stripe",
        sa.Column("id", sa.String(100), nullable=False),
        sa.Column("tipo", sa.String(100), nullable=False),
        _momento("processado_em"),
        sa.PrimaryKeyConstraint("id", name="pk_eventos_stripe"),
    )


def downgrade() -> None:
    op.drop_table("eventos_stripe")
    op.drop_table("assinaturas")
