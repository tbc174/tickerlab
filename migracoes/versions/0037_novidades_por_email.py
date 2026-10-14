"""Novidades e ofertas do TickerLab por e-mail: a inscrição de cada usuário e cada envio

Revisão: 0037

O e-mail do login serve só para a conta (política de privacidade); para receber novidades e ofertas
a pessoa marca um consentimento próprio, separado dos termos e da Newsletter, com um código para
sair sem login. O registro dos envios impede mandar a mesma campanha duas vezes. Os dois são dados
do usuário: apagados com a conta (chave estrangeira em cascata) e incluídos na exportação. Só cria
tabelas novas: nada do que existe muda.
"""

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def _usuario(tabela: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["usuario_id"],
        ["usuarios.id"],
        name=f"fk_{tabela}_usuario_id_usuarios",
        ondelete="CASCADE",
    )


def _momento(nome: str) -> sa.Column:
    return sa.Column(
        nome,
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


def upgrade() -> None:
    op.create_table(
        "inscricoes_de_novidades",
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.Column("versao_do_consentimento", sa.String(20), nullable=False),
        sa.Column("codigo_para_sair", sa.String(64), nullable=False),
        _momento("inscrito_em"),
        sa.PrimaryKeyConstraint("usuario_id", name="pk_inscricoes_de_novidades"),
        sa.UniqueConstraint(
            "codigo_para_sair", name="uq_inscricoes_de_novidades_codigo_para_sair"
        ),
        _usuario("inscricoes_de_novidades"),
    )
    op.create_table(
        "envios_de_novidades",
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.Column("campanha", sa.String(80), nullable=False),  # "2026-11-lancamento"
        sa.Column("situacao", sa.String(20), nullable=False),
        sa.Column("detalhe", sa.String(200), nullable=False, server_default=""),
        _momento("registrado_em"),
        sa.PrimaryKeyConstraint(
            "usuario_id", "campanha", name="pk_envios_de_novidades"
        ),
        sa.CheckConstraint(
            "situacao IN ('enviado', 'retido', 'falhou')",
            name="ck_envios_de_novidades_situacao",
        ),
        _usuario("envios_de_novidades"),
    )


def downgrade() -> None:
    op.drop_table("envios_de_novidades")
    op.drop_table("inscricoes_de_novidades")
