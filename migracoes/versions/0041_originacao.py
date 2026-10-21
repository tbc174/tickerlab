"""Originação: o funil das operações da sala de dados (B-33)

Revisão: 0041 (encadeada na 0040; reservada no quadro de sessões em 21/10)

Duas tabelas novas; nada do que existe muda. `negocios_da_originacao` guarda a fase, a origem, o
próximo passo e o responsável de cada operação (no máximo um negócio por operação) e
`contatos_do_negocio` guarda os contatos que a pessoa anotou à mão. Isolamento no próprio banco, como
na sala (0040): `usuario_id` em toda linha e chave composta (operacao_id, usuario_id) para a
operação, então o banco recusa uma linha de uma conta na operação de outra. Tudo sai com a operação
e com a conta (cascata). De propósito, nenhuma coluna de e-mail ou telefone: o registro não envia nada.

Caminho de volta: o `downgrade` apaga as duas tabelas. Vale só antes de haver negócio de verdade;
depois disso, a volta é o backup.
"""

import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

FASES = (
    "ideia",
    "qualificacao",
    "analise",
    "proposta",
    "negociacao",
    "fechado",
    "perdido",
)


def _momento(nome: str) -> sa.Column:
    return sa.Column(
        nome, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def _dono(tabela: str) -> list:
    return [
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=f"fk_{tabela}_usuario_id_usuarios",
            ondelete="CASCADE",
        ),
    ]


def _criar_negocios() -> None:
    lista = ", ".join(f"'{fase}'" for fase in FASES)
    op.create_table(
        "negocios_da_originacao",
        sa.Column("operacao_id", sa.Uuid, nullable=False),
        *_dono("negocios_da_originacao"),
        sa.Column("fase", sa.String(12), nullable=False, server_default="ideia"),
        sa.Column("origem", sa.String(300), nullable=False),
        sa.Column("alvo", sa.String(300), nullable=True),
        sa.Column("proximo_passo", sa.String(300), nullable=True),
        sa.Column("responsavel", sa.String(300), nullable=True),
        sa.Column("fase_desde", sa.Date, nullable=False),
        _momento("criado_em"),
        _momento("atualizado_em"),
        sa.PrimaryKeyConstraint("operacao_id", name="pk_negocios_da_originacao"),
        sa.ForeignKeyConstraint(
            ["operacao_id", "usuario_id"],
            ["operacoes.id", "operacoes.usuario_id"],
            name="fk_negocios_da_originacao_operacao_id_operacoes",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "operacao_id", "usuario_id", name="uq_negocios_da_originacao_operacao"
        ),
        sa.CheckConstraint(f"fase IN ({lista})", name="ck_negocios_da_originacao_fase"),
    )
    op.create_index(
        "ix_negocios_da_originacao_usuario_id",
        "negocios_da_originacao",
        ["usuario_id"],
    )


def _criar_contatos() -> None:
    op.create_table(
        "contatos_do_negocio",
        sa.Column("id", sa.Uuid, nullable=False),
        *_dono("contatos_do_negocio"),
        sa.Column("operacao_id", sa.Uuid, nullable=False),
        sa.Column("descricao", sa.String(500), nullable=False),
        sa.Column("ocorreu_em", sa.Date, nullable=False),
        _momento("registrado_em"),
        sa.PrimaryKeyConstraint("id", name="pk_contatos_do_negocio"),
        sa.ForeignKeyConstraint(
            ["operacao_id", "usuario_id"],
            [
                "negocios_da_originacao.operacao_id",
                "negocios_da_originacao.usuario_id",
            ],
            name="fk_contatos_do_negocio_negocio",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "length(descricao) BETWEEN 1 AND 500",
            name="ck_contatos_do_negocio_descricao",
        ),
    )
    op.create_index(
        "ix_contatos_do_negocio_negocio",
        "contatos_do_negocio",
        ["operacao_id", "usuario_id"],
    )
    op.create_index(
        "ix_contatos_do_negocio_usuario_id", "contatos_do_negocio", ["usuario_id"]
    )


def upgrade() -> None:
    _criar_negocios()
    _criar_contatos()


def downgrade() -> None:
    op.drop_table("contatos_do_negocio")
    op.drop_table("negocios_da_originacao")
