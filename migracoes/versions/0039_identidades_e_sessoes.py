"""Entrar por mais de um provedor (Google, Microsoft, e-mail com código) e sessões de login

Revisão: 0039 (encadeada na 0037: a 0038 do Workspace ainda não entrou na `main`)

Até aqui a conta era achada só pelo `google_sub`. Agora cada forma de entrar é uma identidade
(provedor + identificador do provedor) ligada a uma conta, e a conta criada pela Microsoft ou por
e-mail não tem `google_sub` (a coluna passa a aceitar vazio). Cada `google_sub` existente vira uma
identidade do Google, com o e-mail confirmado (o Google só entrega e-mail verificado ao login).

A sessão do app novo fica num cookie com um código aleatório; o banco guarda só o hash dele, então
quem lê o banco não consegue entrar por ninguém. Os códigos de entrada por e-mail também ficam só em
hash (do e-mail e do código), sem chave para a conta: o primeiro acesso ainda não tem conta.

Identidades e sessões são dados do usuário: apagados com a conta (chave estrangeira em cascata). No
SQLite, mudar a coluna recria a tabela `usuarios`; com as chaves estrangeiras ligadas, apagar a
tabela antiga apagaria em cascata tudo o que é da conta. Por isso elas ficam desligadas durante a
troca (só vale se esta for a primeira migração da rodada, o caso de quem atualiza um banco com
dados; num banco novo não há o que perder).
"""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0037"
branch_labels = None
depends_on = None

PROVEDORES = "provedor IN ('google', 'microsoft', 'email')"


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


def _google_sub_aceita_vazio(aceita: bool) -> None:
    conexao = op.get_bind()
    if conexao.dialect.name != "sqlite":
        op.alter_column(
            "usuarios", "google_sub", existing_type=sa.String(64), nullable=aceita
        )
        return
    op.execute("PRAGMA foreign_keys=OFF")
    # lida do banco, como na 0005: os nomes com que o SQLite devolve as regras variam
    tabela = sa.Table("usuarios", sa.MetaData(), autoload_with=conexao)
    with op.batch_alter_table(
        "usuarios", copy_from=tabela, recreate="always"
    ) as alteracao:
        alteracao.alter_column(
            "google_sub", existing_type=sa.String(64), nullable=aceita
        )
    op.execute("PRAGMA foreign_keys=ON")


def _identidades_do_google() -> None:
    conexao = op.get_bind()
    usuarios = sa.table(
        "usuarios",
        sa.column("id", sa.Uuid),
        sa.column("google_sub", sa.String),
        sa.column("email", sa.String),
    )
    identidades = sa.table(
        "identidades",
        sa.column("id", sa.Uuid),
        sa.column("usuario_id", sa.Uuid),
        sa.column("provedor", sa.String),
        sa.column("sub", sa.String),
        sa.column("email", sa.String),
        sa.column("email_confirmado", sa.Boolean),
    )
    linhas = conexao.execute(
        sa.select(usuarios.c.id, usuarios.c.google_sub, usuarios.c.email)
    ).all()
    if linhas:
        conexao.execute(
            sa.insert(identidades),
            [
                {
                    "id": uuid.uuid4(),
                    "usuario_id": id_,
                    "provedor": "google",
                    "sub": sub,
                    "email": email,
                    "email_confirmado": True,
                }
                for id_, sub, email in linhas
            ],
        )


def upgrade() -> None:
    _google_sub_aceita_vazio(True)
    op.create_table(
        "identidades",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.Column("provedor", sa.String(20), nullable=False),
        sa.Column("sub", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("email_confirmado", sa.Boolean, nullable=False),
        _momento("criada_em"),
        sa.Column("ultimo_uso", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_identidades"),
        sa.UniqueConstraint("provedor", "sub", name="uq_identidades_provedor"),
        sa.CheckConstraint(PROVEDORES, name="ck_identidades_provedor"),
        _usuario("identidades"),
    )
    op.create_index("ix_identidades_usuario_id", "identidades", ["usuario_id"])
    op.create_index("ix_identidades_email", "identidades", ["email"])
    op.create_table(
        "sessoes_de_login",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.Column("hash_do_token", sa.String(64), nullable=False),
        sa.Column("provedor", sa.String(20), nullable=False),
        _momento("criada_em"),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ultimo_uso", sa.DateTime(timezone=True)),
        sa.Column("encerrada_em", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_sessoes_de_login"),
        sa.UniqueConstraint("hash_do_token", name="uq_sessoes_de_login_hash_do_token"),
        sa.CheckConstraint(PROVEDORES, name="ck_sessoes_de_login_provedor"),
        _usuario("sessoes_de_login"),
    )
    op.create_index(
        "ix_sessoes_de_login_usuario_id", "sessoes_de_login", ["usuario_id"]
    )
    op.create_table(
        "codigos_de_entrada",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("hash_do_email", sa.String(64), nullable=False),
        sa.Column("hash_do_codigo", sa.String(64), nullable=False),
        _momento("criado_em"),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tentativas", sa.Integer, nullable=False, server_default="0"),
        sa.Column("usado_em", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_codigos_de_entrada"),
    )
    op.create_index(
        "ix_codigos_de_entrada_hash_do_email", "codigos_de_entrada", ["hash_do_email"]
    )
    _identidades_do_google()


def downgrade() -> None:
    sem_google = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM usuarios WHERE google_sub IS NULL")
    )
    if sem_google.scalar():
        # voltar exigiria apagar as contas criadas pela Microsoft ou por e-mail: isso é decisão de
        # uma pessoa, não de uma migração
        raise RuntimeError(
            "Há contas sem google_sub (criadas pela Microsoft ou por e-mail): "
            "a migração 0039 não volta sozinha."
        )
    op.drop_table("codigos_de_entrada")
    op.drop_table("sessoes_de_login")
    op.drop_table("identidades")
    _google_sub_aceita_vazio(False)
