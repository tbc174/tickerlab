"""Newsletter por e-mail (Research, etapa 5c): a inscrição de cada usuário e cada envio

Revisão: 0018

A inscrição é opt-in, com consentimento próprio (decisão 0020) e um código para descadastrar
sem login. O registro dos envios impede mandar a mesma edição duas vezes. Os dois são dados do
usuário: apagados com a conta (chave estrangeira em cascata) e incluídos na exportação.
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
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
        "inscricoes_da_newsletter",
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.Column("lista", sa.String(60), nullable=False),
        sa.Column("cadencia", sa.String(20), nullable=False),
        sa.Column("versao_do_consentimento", sa.String(20), nullable=False),
        sa.Column("codigo_para_sair", sa.String(64), nullable=False),
        _momento("inscrito_em"),
        sa.PrimaryKeyConstraint("usuario_id", name="pk_inscricoes_da_newsletter"),
        sa.UniqueConstraint(
            "codigo_para_sair", name="uq_inscricoes_da_newsletter_codigo_para_sair"
        ),
        sa.CheckConstraint(
            "cadencia IN ('diaria', 'semanal')",
            name="ck_inscricoes_da_newsletter_cadencia",
        ),
        _usuario("inscricoes_da_newsletter"),
    )
    op.create_table(
        "envios_da_newsletter",
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.Column(
            "periodo", sa.String(20), nullable=False
        ),  # "2026-10-12" ou "2026-W42"
        sa.Column("situacao", sa.String(20), nullable=False),
        sa.Column("detalhe", sa.String(200), nullable=False, server_default=""),
        _momento("registrado_em"),
        sa.PrimaryKeyConstraint(
            "usuario_id", "periodo", name="pk_envios_da_newsletter"
        ),
        sa.CheckConstraint(
            "situacao IN ('enviado', 'retido', 'falhou')",
            name="ck_envios_da_newsletter_situacao",
        ),
        _usuario("envios_da_newsletter"),
    )


def downgrade() -> None:
    op.drop_table("envios_da_newsletter")
    op.drop_table("inscricoes_da_newsletter")
