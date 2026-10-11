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
PLANOS = ("gratuito", "plus", "pro")
TIPOS_DE_RELATORIO = ("ativo", "comparacao", "backtest", "carteira", "minha_carteira")

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
    # versão dos termos de uso e da política de privacidade que a pessoa aceitou, e quando
    sa.Column("termos_versao", sa.String(20)),
    sa.Column("termos_aceitos_em", sa.DateTime(timezone=True)),
    sa.CheckConstraint("papel IN ('usuario', 'admin')", name="papel"),
    sa.CheckConstraint("plano IN ('gratuito', 'plus', 'pro')", name="plano"),
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

assinaturas = sa.Table(
    "assinaturas",
    metadata,
    _chave_do_usuario(primaria=True),
    sa.Column("stripe_customer_id", sa.String(64), nullable=False, unique=True),
    sa.Column("stripe_subscription_id", sa.String(64), unique=True),
    sa.Column("status", sa.String(30), nullable=False),
    sa.Column("periodo_fim", sa.DateTime(timezone=True)),
    sa.Column("cancela_no_fim", sa.Boolean, nullable=False, server_default=sa.false()),
    # momento (do Stripe) do último evento aplicado: eventos mais velhos que isso são ignorados
    sa.Column("evento_em", sa.BigInteger, nullable=False, server_default="0"),
    _momento("atualizada_em"),
)

# um registro por evento do Stripe já processado: o Stripe repete entregas, e isto evita aplicar
# o mesmo evento duas vezes (idempotência)
eventos_stripe = sa.Table(
    "eventos_stripe",
    metadata,
    sa.Column("id", sa.String(100), primary_key=True),
    sa.Column("tipo", sa.String(100), nullable=False),
    _momento("processado_em"),
)

# registro do que aconteceu de importante (ações de administrador, aceite dos termos, conta
# apagada). Guarda ids, nunca e-mail nem nome: assim sobrevive à exclusão da conta sem manter
# dados pessoais. O ator vira nulo se a conta dele for apagada.
auditoria = sa.Table(
    "auditoria",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("ator_id", sa.Uuid, sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
    sa.Column("acao", sa.String(60), nullable=False),
    sa.Column("alvo_id", sa.Uuid),
    sa.Column("detalhes", JSON_PORTATIL, nullable=False),
    _momento("criado_em"),
)
sa.Index("ix_auditoria_criado_em", auditoria.c.criado_em)


# Relatórios em PDF gerados: só o tipo e a hora, para contar o limite do plano (o PDF não é
# guardado). Apagados junto com a conta.
relatorios = sa.Table(
    "relatorios",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    _chave_do_usuario(),
    sa.Column("tipo", sa.String(20), nullable=False),
    _momento("criado_em"),
    # biblioteca (0006): título e parâmetros para reabrir; ao excluir, só tipo e hora ficam
    sa.Column("titulo", sa.String(200)),
    sa.Column("parametros", JSON_PORTATIL),
    sa.Column("apagado_em", sa.DateTime(timezone=True)),
    sa.CheckConstraint(
        "tipo IN ('ativo', 'comparacao', 'backtest', 'carteira', 'minha_carteira')",
        name="tipo",
    ),
)
sa.Index(
    "ix_relatorios_usuario_id_criado_em",
    relatorios.c.usuario_id,
    relatorios.c.criado_em,
)
