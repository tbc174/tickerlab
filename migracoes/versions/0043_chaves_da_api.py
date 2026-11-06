"""Chaves da API externa por organização (N7; ADR 0108, linha 117)

Revisão: 0043 (reservada no quadro de sessões em 21/10; encadeada na última da `main` na hora do merge)

Quatro tabelas novas; nada do que existe muda. `organizacoes` é o cliente PJ da API externa (sem
e-mail, telefone ou nome de pessoa: o contato fica no CRM). `chaves_da_api` guarda o prefixo visível
e o SHA-256 da chave inteira, nunca a chave. `direitos_da_organizacao` é o contrato (conjunto ×
finalidade, com vigência). `consumo_da_api` conta pedidos por organização × chave × dia × canal ×
finalidade × conjunto, sem IP e sem o que foi buscado.

Travas no próprio banco, além do código: finalidade só `analise` ou `credito` (nunca `treino`); canal
do consumo só `api_externa`; consumo aponta para (chave, organização), então a chave de uma
organização não conta no consumo da outra; suspensa só com motivo da lista. O admin que criou fica
com `SET NULL` quando a conta dele é apagada: a organização e as chaves continuam.

Caminho de volta: o `downgrade` apaga as quatro tabelas. Vale só antes de haver cliente de verdade;
depois disso, a volta é o backup.
"""

import sqlalchemy as sa
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

PLANOS_DA_API = ("piloto",)
FINALIDADES = ("analise", "credito")
MOTIVOS_DA_SUSPENSAO = ("contrato", "pagamento", "abuso", "pedido_do_cliente", "fonte")


def _lista(valores: tuple[str, ...]) -> str:
    return ", ".join(f"'{valor}'" for valor in valores)


def _momento(nome: str) -> sa.Column:
    return sa.Column(
        nome, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def _quem_fez(tabela: str, coluna: str) -> list:
    return [
        sa.Column(coluna, sa.Uuid, nullable=True),
        sa.ForeignKeyConstraint(
            [coluna],
            ["usuarios.id"],
            name=f"fk_{tabela}_{coluna}_usuarios",
            ondelete="SET NULL",
        ),
    ]


def _da_organizacao(tabela: str) -> list:
    return [
        sa.Column("organizacao_id", sa.Uuid, nullable=False),
        sa.ForeignKeyConstraint(
            ["organizacao_id"],
            ["organizacoes.id"],
            name=f"fk_{tabela}_organizacao_id_organizacoes",
            ondelete="CASCADE",
        ),
    ]


def _criar_organizacoes() -> None:
    op.create_table(
        "organizacoes",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("cnpj", sa.String(14), nullable=True),
        sa.Column(
            "plano_da_api", sa.String(20), nullable=False, server_default="piloto"
        ),
        sa.Column("suspensa_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_da_suspensao", sa.String(30), nullable=True),
        _momento("criada_em"),
        *_quem_fez("organizacoes", "criada_por"),
        sa.PrimaryKeyConstraint("id", name="pk_organizacoes"),
        sa.UniqueConstraint("cnpj", name="uq_organizacoes_cnpj"),
        sa.CheckConstraint(
            f"plano_da_api IN ({_lista(PLANOS_DA_API)})",
            name="ck_organizacoes_plano_da_api",
        ),
        sa.CheckConstraint(
            "motivo_da_suspensao IS NULL OR motivo_da_suspensao IN "
            f"({_lista(MOTIVOS_DA_SUSPENSAO)})",
            name="ck_organizacoes_motivo_da_suspensao",
        ),
        sa.CheckConstraint(
            "(suspensa_em IS NULL) = (motivo_da_suspensao IS NULL)",
            name="ck_organizacoes_suspensao",
        ),
    )


def _criar_chaves() -> None:
    op.create_table(
        "chaves_da_api",
        sa.Column("id", sa.Uuid, nullable=False),
        *_da_organizacao("chaves_da_api"),
        sa.Column("prefixo", sa.String(8), nullable=False),
        sa.Column("hash_da_chave", sa.String(64), nullable=False),
        _momento("criada_em"),
        *_quem_fez("chaves_da_api", "criada_por"),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revogada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_uso", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_chaves_da_api"),
        sa.UniqueConstraint("prefixo", name="uq_chaves_da_api_prefixo"),
        sa.UniqueConstraint("hash_da_chave", name="uq_chaves_da_api_hash_da_chave"),
        sa.UniqueConstraint(
            "id", "organizacao_id", name="uq_chaves_da_api_organizacao"
        ),
    )
    op.create_index(
        "ix_chaves_da_api_organizacao_id", "chaves_da_api", ["organizacao_id"]
    )


def _criar_direitos() -> None:
    op.create_table(
        "direitos_da_organizacao",
        sa.Column("id", sa.Uuid, nullable=False),
        *_da_organizacao("direitos_da_organizacao"),
        sa.Column("conjunto", sa.String(80), nullable=False),
        sa.Column("finalidade", sa.String(12), nullable=False),
        sa.Column("vigente_desde", sa.Date, nullable=False),
        sa.Column("vigente_ate", sa.Date, nullable=True),
        sa.Column("suspenso_em", sa.DateTime(timezone=True), nullable=True),
        _momento("criado_em"),
        *_quem_fez("direitos_da_organizacao", "criado_por"),
        sa.PrimaryKeyConstraint("id", name="pk_direitos_da_organizacao"),
        sa.UniqueConstraint(
            "organizacao_id",
            "conjunto",
            "finalidade",
            name="uq_direitos_da_organizacao_conjunto",
        ),
        sa.CheckConstraint(
            f"finalidade IN ({_lista(FINALIDADES)})",
            name="ck_direitos_da_organizacao_finalidade",
        ),
        sa.CheckConstraint(
            "vigente_ate IS NULL OR vigente_ate >= vigente_desde",
            name="ck_direitos_da_organizacao_vigencia",
        ),
    )


def _criar_consumo() -> None:
    op.create_table(
        "consumo_da_api",
        sa.Column("organizacao_id", sa.Uuid, nullable=False),
        sa.Column("chave_id", sa.Uuid, nullable=False),
        sa.Column("dia", sa.Date, nullable=False),
        sa.Column("canal", sa.String(12), nullable=False),
        sa.Column("finalidade", sa.String(12), nullable=False),
        sa.Column("conjunto", sa.String(80), nullable=False),
        sa.Column("pedidos", sa.Integer, nullable=False, server_default="0"),
        sa.Column("linhas", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("negados", sa.Integer, nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint(
            "organizacao_id",
            "chave_id",
            "dia",
            "canal",
            "finalidade",
            "conjunto",
            name="pk_consumo_da_api",
        ),
        sa.ForeignKeyConstraint(
            ["chave_id", "organizacao_id"],
            ["chaves_da_api.id", "chaves_da_api.organizacao_id"],
            name="fk_consumo_da_api_chave",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("canal = 'api_externa'", name="ck_consumo_da_api_canal"),
        sa.CheckConstraint(
            f"finalidade IN ({_lista(FINALIDADES)})",
            name="ck_consumo_da_api_finalidade",
        ),
    )


def upgrade() -> None:
    _criar_organizacoes()
    _criar_chaves()
    _criar_direitos()
    _criar_consumo()


def downgrade() -> None:
    op.drop_table("consumo_da_api")
    op.drop_table("direitos_da_organizacao")
    op.drop_index("ix_chaves_da_api_organizacao_id", table_name="chaves_da_api")
    op.drop_table("chaves_da_api")
    op.drop_table("organizacoes")
