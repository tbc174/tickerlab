"""Histórico das versões dos eventos (Radar e base histórica, PR 3; ADR 0024 do autor)

Revisão: 0024

`eventos_versoes`: cada versão de cada evento (CVM IPE e SEC), só acréscimo. Quando a fonte
reapresenta um documento, a versão anterior ganha `substituido_em` em vez de sumir. A tabela
`eventos` continua sendo a vigente; nada do que existe muda. Os eventos que já estão no banco
entram como a primeira versão conhecida, com `registrado_em` = quando foram gravados (cópia
dentro do banco, em segundos: o deploy espera o app ficar saudável por pouco tempo).
"""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

COLUNAS = (
    "fonte, protocolo, versao, cnpj, empresa, categoria, tipo, assunto, rotulo, tema,"
    " materialidade, referencia, publicado_em, link"
)


def upgrade() -> None:
    op.create_table(
        "eventos_versoes",
        sa.Column("fonte", sa.String(20), primary_key=True),
        sa.Column("protocolo", sa.String(60), primary_key=True),
        sa.Column("versao", sa.Integer, primary_key=True),
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
    )
    op.execute(
        f"INSERT INTO eventos_versoes ({COLUNAS}, registrado_em)"
        f" SELECT {COLUNAS}, ingerido_em FROM eventos"
    )


def downgrade() -> None:
    op.drop_table("eventos_versoes")
