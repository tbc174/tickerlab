"""Conjuntos suspensos da API externa, para todas as organizações (B-32a, PR 6)

Revisão: 0046 (reservada no quadro de sessões em 03/11; encadeada na última da `main` na hora do merge)

Uma tabela nova; nada do que existe muda. `conjuntos_suspensos` é o botão de parar um conjunto
inteiro (fonte que mudou a licença, dado que saiu errado): enquanto a linha tem `suspenso_em`, o
conjunto não sai para nenhuma organização, inclusive a que ganhar o contrato depois. Reativar limpa
`suspenso_em` e o motivo; o direito que foi suspenso sozinho em `direitos_da_organizacao` continua
suspenso. Quem suspendeu e quando fica na auditoria (só ids e códigos).

Travas no próprio banco: motivo só da mesma lista das organizações, e suspenso sempre com motivo.

Caminho de volta: o `downgrade` apaga a tabela nova; o contrato das organizações fica como estava. Um
conjunto suspenso volta a sair, então desça só depois de reativar (ou de suspender os direitos um a um).
"""

import sqlalchemy as sa
from alembic import op

revision = "0046"
down_revision = "0044"
branch_labels = None
depends_on = None

TABELA = "conjuntos_suspensos"
TAMANHO_MAXIMO_DO_CONJUNTO = 80
MOTIVOS_DA_SUSPENSAO = ("contrato", "pagamento", "abuso", "pedido_do_cliente", "fonte")


def _lista(valores: tuple[str, ...]) -> str:
    return ", ".join(f"'{valor}'" for valor in valores)


def upgrade() -> None:
    op.create_table(
        TABELA,
        sa.Column("conjunto", sa.String(TAMANHO_MAXIMO_DO_CONJUNTO), nullable=False),
        sa.Column("suspenso_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_da_suspensao", sa.String(30), nullable=True),
        sa.PrimaryKeyConstraint("conjunto", name=f"pk_{TABELA}"),
        sa.CheckConstraint(
            "motivo_da_suspensao IS NULL OR motivo_da_suspensao IN "
            f"({_lista(MOTIVOS_DA_SUSPENSAO)})",
            name=f"ck_{TABELA}_motivo_da_suspensao",
        ),
        sa.CheckConstraint(
            "(suspenso_em IS NULL) = (motivo_da_suspensao IS NULL)",
            name=f"ck_{TABELA}_suspensao",
        ),
    )


def downgrade() -> None:
    op.drop_table(TABELA)
