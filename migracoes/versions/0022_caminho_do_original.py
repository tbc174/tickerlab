"""Caminho do arquivo original no acervo, no registro de coletas (Radar, PR 2; ADR 0024 do autor)

Revisão: 0022

Cada coleta que baixou um arquivo passa a dizer onde o original ficou guardado
(`bruto/<fonte>/<ano>/<sha256>.<ext>`). Só acrescenta uma coluna que aceita vazio.
"""

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("coletas", sa.Column("caminho_do_original", sa.String(200)))


def downgrade() -> None:
    op.drop_column("coletas", "caminho_do_original")
