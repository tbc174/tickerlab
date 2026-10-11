"""biblioteca de relatórios (Report Studio): título, parâmetros e exclusão

Revisão: 0006

Cada relatório passa a guardar o título e os parâmetros com que foi montado (tipo, ativos,
período, estilo, seções), para a pessoa reabrir e gerar uma nova versão. O PDF continua não
sendo guardado. Excluir da biblioteca apaga o título e os parâmetros e marca `apagado_em`; a
linha (só tipo e hora) fica, porque é ela que conta o limite de relatórios do plano: apagar não
devolve o relatório gasto.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # colunas que aceitam vazio: o SQLite as acrescenta sem recriar a tabela
    op.add_column("relatorios", sa.Column("titulo", sa.String(200), nullable=True))
    op.add_column(
        "relatorios",
        sa.Column(
            "parametros", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=True
        ),
    )
    op.add_column(
        "relatorios",
        sa.Column("apagado_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("relatorios") as tabela:
        tabela.drop_column("apagado_em")
        tabela.drop_column("parametros")
        tabela.drop_column("titulo")
