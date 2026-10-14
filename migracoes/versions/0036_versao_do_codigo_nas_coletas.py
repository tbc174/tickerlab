"""Versão do código no registro de coletas (série 3 da base de ML, PR 3; ADR 0055, exigência 13)

Revisão: 0036

Cada arquivo baixado passa a dizer qual commit do TickerLab o baixou (`src/versao_do_codigo.py`), para
a linhagem de qualquer número chegar à versão do código. Só acrescenta uma coluna que aceita vazio:
as linhas antigas ficam sem versão (gravadas antes da exigência) e nada do que existe muda.
"""

import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("coletas") as tabela:
        tabela.add_column(sa.Column("versao_do_codigo", sa.String(60)))


def downgrade() -> None:
    with op.batch_alter_table("coletas") as tabela:
        tabela.drop_column("versao_do_codigo")
