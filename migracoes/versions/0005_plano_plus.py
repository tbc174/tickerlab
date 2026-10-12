"""plano Plus (entre o Gratuito e o Pro)

Revisão: 0005

Muda a regra que aceita os planos. No PostgreSQL (produção) basta apagar e recriar a regra. No
SQLite (testes e modo local) mudar uma regra exige recriar a tabela; como o nome com que a regra
antiga é lida varia, a tabela é lida do banco, perde TODAS as regras de verificação e ganha só as
duas certas (papel e plano), sem depender desses nomes.
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

REGRA_DO_PAPEL = "papel IN ('usuario', 'admin')"


def _trocar_regra_do_plano(regra: str) -> None:
    conexao = op.get_bind()
    if conexao.dialect.name == "sqlite":
        tabela = sa.Table("usuarios", sa.MetaData(), autoload_with=conexao)
        antigas = [c for c in tabela.constraints if isinstance(c, sa.CheckConstraint)]
        for regra_antiga in antigas:
            tabela.constraints.discard(regra_antiga)
        tabela.append_constraint(
            sa.CheckConstraint(REGRA_DO_PAPEL, name="ck_usuarios_papel")
        )
        tabela.append_constraint(sa.CheckConstraint(regra, name="ck_usuarios_plano"))
        with op.batch_alter_table("usuarios", copy_from=tabela, recreate="always"):
            pass
        return
    # no PostgreSQL o nome da regra antiga depende da convenção usada na 0001: apaga pela
    # definição (a que fala de "plano"), não pelo nome
    for antiga in sa.inspect(conexao).get_check_constraints("usuarios"):
        if "plano" in antiga["sqltext"]:
            op.drop_constraint(op.f(antiga["name"]), "usuarios", type_="check")
    op.create_check_constraint(op.f("ck_usuarios_plano"), "usuarios", regra)


def upgrade() -> None:
    _trocar_regra_do_plano("plano IN ('gratuito', 'plus', 'pro')")


def downgrade() -> None:
    op.execute("UPDATE usuarios SET plano = 'gratuito' WHERE plano = 'plus'")
    _trocar_regra_do_plano("plano IN ('gratuito', 'pro')")
