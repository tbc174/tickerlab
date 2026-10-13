"""Plano de antes do Pro, para voltar a ele quando a assinatura termina (N-02 do Master v3)

Revisão: 0020

Quem tinha o Plus (hoje dado pelo administrador) e assina o Pro voltava ao Gratuito quando o Pro
terminava. A assinatura passa a guardar o plano que o usuário tinha ao ganhar o Pro; quando a
assinatura deixa de dar o Pro, ele volta a esse plano (ou ao Gratuito, se não houver).
Só acrescenta uma coluna que aceita vazio: nada do que já existe muda.
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assinaturas", sa.Column("plano_sem_o_pro", sa.String(20)))


def downgrade() -> None:
    op.drop_column("assinaturas", "plano_sem_o_pro")
