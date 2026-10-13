"""Histórico das versões dos eventos (Radar e base histórica, PR 3; ADR 0024 do autor)

Revisão: 0024

`eventos_versoes`: cada versão de cada evento (CVM IPE e SEC), só acréscimo. Quando a fonte
reapresenta um documento, a versão anterior ganha `substituido_em` em vez de sumir. A tabela
`eventos` continua sendo a vigente; nada do que existe muda. Os eventos que já estão no banco
entram como a primeira versão conhecida, com `registrado_em` = quando foram gravados.
"""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

COLUNAS = [
    "fonte", "protocolo", "versao", "cnpj", "empresa", "categoria", "tipo", "assunto",
    "rotulo", "tema", "materialidade", "referencia", "publicado_em", "link",
]  # fmt: skip
LOTE = 2000


def _copiar_os_eventos_atuais(versoes: sa.Table) -> None:
    conexao = op.get_bind()
    # com os tipos: o SQLite devolve datas como texto, e a gravação abaixo exige date/datetime
    tipos = {
        "versao": sa.Integer(),
        "materialidade": sa.Integer(),
        "referencia": sa.Date(),
        "publicado_em": sa.Date(),
        "ingerido_em": sa.DateTime(timezone=True),
    }
    eventos = sa.table(
        "eventos",
        *[sa.column(c, tipos.get(c)) for c in [*COLUNAS, "ingerido_em"]],
    )
    resultado = conexao.execute(sa.select(eventos))
    while lote := resultado.fetchmany(LOTE):
        conexao.execute(
            sa.insert(versoes),
            [
                {
                    "id": uuid.uuid4(),
                    **{c: getattr(linha, c) for c in COLUNAS},
                    "registrado_em": linha.ingerido_em,
                }
                for linha in lote
            ],
        )


def upgrade() -> None:
    versoes = op.create_table(
        "eventos_versoes",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("fonte", sa.String(20), nullable=False),
        sa.Column("protocolo", sa.String(60), nullable=False),
        sa.Column("versao", sa.Integer, nullable=False),
        sa.Column("cnpj", sa.String(18), nullable=False),
        sa.Column("empresa", sa.String(200), nullable=False),
        sa.Column("categoria", sa.String(160), nullable=False),
        sa.Column("tipo", sa.String(300), nullable=False, server_default=""),
        sa.Column("assunto", sa.Text, nullable=False, server_default=""),
        sa.Column("rotulo", sa.String(60), nullable=False),
        sa.Column("tema", sa.String(20), nullable=False),
        sa.Column("materialidade", sa.Integer, nullable=False),
        sa.Column("referencia", sa.Date),
        sa.Column("publicado_em", sa.Date, nullable=False),
        sa.Column("link", sa.String(500), nullable=False),
        sa.Column(
            "registrado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("substituido_em", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("fonte", "protocolo", "versao", name="uq_eventos_versoes"),
    )
    assert versoes is not None
    _copiar_os_eventos_atuais(versoes)


def downgrade() -> None:
    op.drop_table("eventos_versoes")
