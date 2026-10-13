"""Tentativas do backtest para a ficha "Foi sorte?" (ADR 0037, D2; ADR 0046 do autor)

Revisão: 0027

Uma linha por configuração diferente que a pessoa rodou no backtest de um ativo, guardada só pela
impressão SHA-256 (nunca a configuração em si). Serve para contar as tentativas e descontá-las no
veredito. Dado do usuário: apagado junto com a conta (chave estrangeira em cascata) e incluído na
exportação dos dados. Só cria uma tabela nova: nada do que existe muda.
"""

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

TABELA = "tentativas"


def upgrade() -> None:
    op.create_table(
        TABELA,
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("impressao", sa.String(64), nullable=False),
        sa.Column(
            "criada_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint(
            "usuario_id", "ticker", "impressao", name="pk_tentativas"
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name="fk_tentativas_usuario_id_usuarios",
            ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table(TABELA)
