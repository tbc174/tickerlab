"""Garantias das operações da sala de dados (B-17)

Revisão: 0042 (encadeada na 0041; reservada no quadro de sessões em 21/10)

Duas tabelas novas; nada do que existe muda. `exposicoes_da_operacao` guarda a dívida a cobrir e
`garantias_da_operacao` guarda cada garantia (tipo, valor avaliado, haircut, ônus anteriores, validade,
laudo com a página). Isolamento no próprio banco, como na sala (0040): `usuario_id` em toda linha e chave
composta para a operação, para a exposição e para o laudo, então o banco recusa uma linha de uma conta
na operação de outra, e um laudo de outra sala. O titular entra só por id opaco (`titular_ref`): de
propósito, nenhuma coluna de nome, CPF ou endereço. Tudo sai com a operação e com a conta (cascata).

Caminho de volta: o `downgrade` apaga as duas tabelas. Vale só antes de haver garantia de verdade;
depois disso, a volta é o backup.
"""

import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

TIPOS = (
    "imovel",
    "recebiveis",
    "veiculo",
    "acoes",
    "fianca",
    "aval",
    "cessao_fiduciaria",
    "outro",
)
LIQUIDEZES = ("alta", "media", "baixa")


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


def _da_operacao(tabela: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["operacao_id", "usuario_id"],
        ["operacoes.id", "operacoes.usuario_id"],
        name=f"fk_{tabela}_operacao_id_operacoes",
        ondelete="CASCADE",
    )


def _da_mesma_sala(
    tabela: str, coluna: str, alvo: str, ondelete: str | None
) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [coluna, "operacao_id", "usuario_id"],
        [f"{alvo}.id", f"{alvo}.operacao_id", f"{alvo}.usuario_id"],
        name=f"fk_{tabela}_{coluna}_{alvo}",
        ondelete=ondelete,
    )


def _entre(tabela: str, coluna: str, valores: tuple[str, ...]) -> sa.CheckConstraint:
    lista = ", ".join(f"'{v}'" for v in valores)
    return sa.CheckConstraint(f"{coluna} IN ({lista})", name=f"ck_{tabela}_{coluna}")


def _criar_exposicoes() -> None:
    tabela = "exposicoes_da_operacao"
    op.create_table(
        tabela,
        sa.Column("id", sa.Uuid, nullable=False),
        *_dono(tabela),
        sa.Column("operacao_id", sa.Uuid, nullable=False),
        sa.Column("rotulo", sa.String(120), nullable=False),
        sa.Column("valor", sa.Numeric(28, 6), nullable=False),
        sa.Column("moeda", sa.String(3), nullable=False),
        sa.Column("vencimento", sa.Date, nullable=True),
        _momento("criada_em"),
        _momento("atualizada_em"),
        sa.PrimaryKeyConstraint("id", name=f"pk_{tabela}"),
        _da_operacao(tabela),
        sa.UniqueConstraint(
            "id", "operacao_id", "usuario_id", name="uq_exposicoes_da_operacao_id"
        ),
        sa.CheckConstraint("valor > 0", name=f"ck_{tabela}_valor"),
        sa.CheckConstraint(
            "length(rotulo) BETWEEN 1 AND 120", name=f"ck_{tabela}_rotulo"
        ),
    )
    op.create_index(f"ix_{tabela}_usuario_id", tabela, ["usuario_id"])
    op.create_index(f"ix_{tabela}_operacao", tabela, ["operacao_id", "usuario_id"])


def _criar_garantias() -> None:
    tabela = "garantias_da_operacao"
    op.create_table(
        tabela,
        sa.Column("id", sa.Uuid, nullable=False),
        *_dono(tabela),
        sa.Column("operacao_id", sa.Uuid, nullable=False),
        sa.Column("exposicao_id", sa.Uuid, nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("valor_avaliado", sa.Numeric(28, 6), nullable=False),
        sa.Column("moeda", sa.String(3), nullable=False),
        sa.Column("avaliado_em", sa.Date, nullable=False),
        sa.Column("haircut", sa.Numeric(7, 6), nullable=False),
        sa.Column("liquidez", sa.String(5), nullable=False),
        sa.Column("prioridade", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "onus_anteriores", sa.Numeric(28, 6), nullable=False, server_default="0"
        ),
        sa.Column("valido_ate", sa.Date, nullable=True),
        sa.Column("titular_ref", sa.String(60), nullable=True),
        sa.Column("laudo_id", sa.Uuid, nullable=True),
        sa.Column("laudo_pagina", sa.Integer, nullable=True),
        _momento("criada_em"),
        _momento("atualizada_em"),
        sa.PrimaryKeyConstraint("id", name=f"pk_{tabela}"),
        _da_operacao(tabela),
        _da_mesma_sala(tabela, "exposicao_id", "exposicoes_da_operacao", "CASCADE"),
        # sem cascata: apagar o documento solta o laudo antes (src/banco/sala.py)
        _da_mesma_sala(tabela, "laudo_id", "documentos_da_sala", None),
        _entre(tabela, "tipo", TIPOS),
        _entre(tabela, "liquidez", LIQUIDEZES),
        sa.CheckConstraint(
            "haircut >= 0 AND haircut <= 1", name=f"ck_{tabela}_haircut"
        ),
        sa.CheckConstraint("valor_avaliado >= 0", name=f"ck_{tabela}_valor_avaliado"),
        sa.CheckConstraint("onus_anteriores >= 0", name=f"ck_{tabela}_onus_anteriores"),
        sa.CheckConstraint("prioridade >= 1", name=f"ck_{tabela}_prioridade"),
        sa.CheckConstraint(
            "(laudo_id IS NULL) = (laudo_pagina IS NULL) "
            "AND (laudo_pagina IS NULL OR laudo_pagina >= 1)",
            name=f"ck_{tabela}_laudo",
        ),
    )
    op.create_index(f"ix_{tabela}_usuario_id", tabela, ["usuario_id"])
    op.create_index(
        f"ix_{tabela}_exposicao",
        tabela,
        ["exposicao_id", "operacao_id", "usuario_id"],
    )
    op.create_index(
        f"ix_{tabela}_laudo", tabela, ["laudo_id", "operacao_id", "usuario_id"]
    )


def upgrade() -> None:
    _criar_exposicoes()
    _criar_garantias()


def downgrade() -> None:
    op.drop_table("garantias_da_operacao")
    op.drop_table("exposicoes_da_operacao")
