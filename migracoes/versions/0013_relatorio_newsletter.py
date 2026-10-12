"""relatório em PDF da Newsletter do Research (tipo novo na tabela de relatórios)

Revisão: 0013

Muda a regra que aceita os tipos de relatório. Mesmo método da 0005: no PostgreSQL apaga e recria
a regra; no SQLite recria a tabela com as regras certas.
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

TIPOS_ANTES = "'ativo', 'comparacao', 'backtest', 'carteira', 'minha_carteira'"
TIPOS_DEPOIS = TIPOS_ANTES + ", 'newsletter'"


def _trocar_regra_do_tipo(tipos: str) -> None:
    regra = f"tipo IN ({tipos})"
    conexao = op.get_bind()
    if conexao.dialect.name == "sqlite":
        tabela = sa.Table("relatorios", sa.MetaData(), autoload_with=conexao)
        for antiga in [
            c for c in tabela.constraints if isinstance(c, sa.CheckConstraint)
        ]:
            tabela.constraints.discard(antiga)
        tabela.append_constraint(sa.CheckConstraint(regra, name="ck_relatorios_tipo"))
        with op.batch_alter_table("relatorios", copy_from=tabela, recreate="always"):
            pass
        return
    for antiga in sa.inspect(conexao).get_check_constraints("relatorios"):
        if "tipo" in antiga["sqltext"]:
            op.drop_constraint(op.f(antiga["name"]), "relatorios", type_="check")
    op.create_check_constraint(op.f("ck_relatorios_tipo"), "relatorios", regra)


def upgrade() -> None:
    _trocar_regra_do_tipo(TIPOS_DEPOIS)


def downgrade() -> None:
    op.execute("DELETE FROM relatorios WHERE tipo = 'newsletter'")
    _trocar_regra_do_tipo(TIPOS_ANTES)
