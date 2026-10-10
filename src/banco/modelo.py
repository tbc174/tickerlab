"""As tabelas do banco de dados (SQLAlchemy Core).

O esquema é criado e alterado só pelas migrações (`migracoes/`). Este arquivo descreve as tabelas
para o código consultar; os tipos são portáteis, então os testes rodam em SQLite e em PostgreSQL.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

CONVENCAO_DE_NOMES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

PAPEIS = ("usuario", "admin")
PLANOS = ("gratuito", "pro")

metadata = sa.MetaData(naming_convention=CONVENCAO_DE_NOMES)

# JSON portátil: JSONB no PostgreSQL (permite índices e consultas), JSON comum no resto
JSON_PORTATIL = sa.JSON().with_variant(JSONB(), "postgresql")


def _chave_do_usuario(primaria: bool = False) -> sa.Column:
    return sa.Column(
        "usuario_id",
        sa.Uuid,
        sa.ForeignKey("usuarios.id", ondelete="CASCADE"),
        primary_key=primaria,
        nullable=False,
    )


def _momento(nome: str) -> sa.Column:
    return sa.Column(
        nome, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


usuarios = sa.Table(
    "usuarios",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("google_sub", sa.String(64), nullable=False, unique=True),
    sa.Column("email", sa.String(320), nullable=False),
    sa.Column("nome", sa.String(200)),
    sa.Column("foto_url", sa.String(1000)),
    sa.Column("papel", sa.String(20), nullable=False, server_default="usuario"),
    sa.Column("plano", sa.String(20), nullable=False, server_default="gratuito"),
    _momento("criado_em"),
    sa.Column("ultimo_acesso", sa.DateTime(timezone=True)),
    sa.Column("excluido_em", sa.DateTime(timezone=True)),
    sa.CheckConstraint("papel IN ('usuario', 'admin')", name="papel"),
    sa.CheckConstraint("plano IN ('gratuito', 'pro')", name="plano"),
)
sa.Index("ix_usuarios_email", usuarios.c.email)

preferencias = sa.Table(
    "preferencias",
    metadata,
    _chave_do_usuario(primaria=True),
    sa.Column("dados", JSON_PORTATIL, nullable=False),
    _momento("atualizado_em"),
)

favoritos = sa.Table(
    "favoritos",
    metadata,
    _chave_do_usuario(primaria=True),
    sa.Column("ticker", sa.String(20), primary_key=True),
    sa.Column("ordem", sa.Integer, nullable=False, server_default="0"),
    _momento("criado_em"),
)

simulacoes = sa.Table(
    "simulacoes",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    _chave_do_usuario(),
    sa.Column("tipo", sa.String(30), nullable=False),
    sa.Column("nome", sa.String(120), nullable=False),
    sa.Column("parametros", JSON_PORTATIL, nullable=False),
    sa.Column("resultado", JSON_PORTATIL, nullable=False),
    _momento("criada_em"),
)
sa.Index("ix_simulacoes_usuario_id", simulacoes.c.usuario_id)
