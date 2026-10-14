"""Origem do cadastro para medir a campanha de lançamento (plano da campanha, PR 1; ADR 0051)

Revisão: 0035

Era a 0029 e depois a 0033 reservada; a 0034 (compartilhamentos) entrou em produção antes e aponta
para a 0032, por isso esta vem depois dela e o número 0033 fica sem uso.

Uma linha por usuário com as UTMs, o `ref` do criador e a data da primeira visita, lidos do cookie
próprio `tl_origem` no primeiro login. Só campos curtos sem dado pessoal (src/origem.py). Dado do
usuário: apagado junto com a conta (cascata) e incluído na exportação dos dados. Só cria uma tabela
nova: nada do que existe muda.
"""

import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

TABELA = "origens_do_cadastro"


def upgrade() -> None:
    op.create_table(
        TABELA,
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.Column("utm_source", sa.String(60)),
        sa.Column("utm_medium", sa.String(60)),
        sa.Column("utm_campaign", sa.String(60)),
        sa.Column("utm_content", sa.String(60)),
        sa.Column("ref", sa.String(60)),
        sa.Column("primeira_visita", sa.Date),
        sa.Column(
            "gravada_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("usuario_id", name="pk_origens_do_cadastro"),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name="fk_origens_do_cadastro_usuario_id_usuarios",
            ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table(TABELA)
