"""Membros da organização: a conta com login que é de uma organização (ADR 0128, Emenda 1; linha 808)

Revisão: 0047 (reservada no quadro de sessões em 10/11/2026; desce da 0045, a última da `main`)

Uma tabela nova; nada do que existe muda. `membros_da_organizacao` liga a conta de quem entra no app
à organização dela (uma conta, uma organização). É por esse vínculo que a tela dos analistas sabe a
quem perguntar se pode mostrar pessoa física do cadastro da Receita: a resposta continua no contrato
(`direitos_da_organizacao`, linha `pessoa_na_tela`), que nasce sem essa linha, ou seja, desligado.

Sem dado de pessoa novo: só os dois ids, a data do vínculo e o admin que vinculou. Apagar a conta ou
a organização leva o vínculo junto (CASCADE); apagar o admin deixa a linha (SET NULL).

Caminho de volta: o `downgrade` apaga a tabela nova; contas, organizações e contrato ficam como
estavam. Sem a tabela ninguém é membro, então nenhuma conta vê pessoa física (volta ao padrão).
"""

import sqlalchemy as sa
from alembic import op

revision = "0047"
down_revision = "0045"
branch_labels = None
depends_on = None

TABELA = "membros_da_organizacao"
INDICE = f"ix_{TABELA}_organizacao_id"


def upgrade() -> None:
    op.create_table(
        TABELA,
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.Column("organizacao_id", sa.Uuid, nullable=False),
        sa.Column(
            "vinculado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("vinculado_por", sa.Uuid, nullable=True),
        sa.PrimaryKeyConstraint("usuario_id", name=f"pk_{TABELA}"),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=f"fk_{TABELA}_usuario_id_usuarios",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organizacao_id"],
            ["organizacoes.id"],
            name=f"fk_{TABELA}_organizacao_id_organizacoes",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vinculado_por"],
            ["usuarios.id"],
            name=f"fk_{TABELA}_vinculado_por_usuarios",
            ondelete="SET NULL",
        ),
    )
    op.create_index(INDICE, TABELA, ["organizacao_id"])


def downgrade() -> None:
    op.drop_index(INDICE, table_name=TABELA)
    op.drop_table(TABELA)
