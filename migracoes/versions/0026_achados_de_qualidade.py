"""Achados das regras de qualidade (série 1 da base de ML, PR 3; ADRs 0027 e 0028 do autor)

Revisão: 0026

Uma linha por achado das regras fixas do selo "dado em conferência" (`base/regras.py`): regra,
empresa, documento, conta, os valores, o porquê em português, a versão das regras, desde quando a
informação existe e quando foi calculado. O achado que some numa rodada nova é fechado, nunca
apagado. Só dado público. Só cria uma tabela nova: nada do que existe muda.
"""

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

TABELA = "achados_de_qualidade"
INDICES = {
    "ix_achados_de_qualidade_cnpj_referencia": ["cnpj", "referencia"],
    "ix_achados_de_qualidade_documento_referencia": ["documento", "referencia"],
}


def upgrade() -> None:
    op.create_table(
        TABELA,
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("regra", sa.String(4), nullable=False),
        sa.Column("cnpj", sa.String(18), nullable=False),
        sa.Column("documento", sa.String(3), nullable=False),
        sa.Column("referencia", sa.Date, nullable=False),
        sa.Column("grupo", sa.String(3), nullable=False, server_default=""),
        sa.Column("conta", sa.String(20), nullable=False, server_default=""),
        sa.Column("valor", sa.Float),
        sa.Column("valor_esperado", sa.Float),
        sa.Column("porque", sa.Text, nullable=False),
        sa.Column("versao_das_regras", sa.String(10), nullable=False),
        sa.Column("valido_desde", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fechado_em", sa.DateTime(timezone=True)),
    )
    for nome, colunas in INDICES.items():
        op.create_index(nome, TABELA, colunas)


def downgrade() -> None:
    for nome in INDICES:
        op.drop_index(nome, table_name=TABELA)
    op.drop_table(TABELA)
