"""Proventos e eventos de capital do FRE (série 2 da base de ML, PR 6)

Revisão: 0029

Dividendos e JCP por exercício e desdobramentos, grupamentos, bonificações e aumentos de capital,
das tabelas do FRE aberto da CVM (do FRE de 2010 ao de 2022). Só dado público. Só cria duas tabelas
novas: nada do que existe muda.
"""

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def _momento(nome: str) -> sa.Column:
    return sa.Column(
        nome, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def upgrade() -> None:
    op.create_table(
        "fre_proventos",
        sa.Column("cnpj", sa.String(18), primary_key=True),
        sa.Column("exercicio", sa.Date, primary_key=True),
        sa.Column("referencia", sa.Date, nullable=False),
        sa.Column("versao", sa.Integer, nullable=False),
        sa.Column("lucro_ajustado", sa.Float),
        sa.Column("dividendo_total", sa.Float),
        sa.Column("payout", sa.Float),
        sa.Column("dividendos", sa.Float),
        sa.Column("jcp", sa.Float),
        _momento("coletado_em"),
    )
    op.create_table(
        "fre_eventos_de_capital",
        sa.Column("cnpj", sa.String(18), primary_key=True),
        sa.Column("tipo", sa.String(30), primary_key=True),
        sa.Column("data", sa.Date, primary_key=True),
        sa.Column("quantidade", sa.BigInteger, primary_key=True),
        sa.Column("referencia", sa.Date, nullable=False),
        sa.Column("versao", sa.Integer, nullable=False),
        sa.Column("acoes_antes", sa.Float),
        sa.Column("acoes_depois", sa.Float),
        sa.Column("fator", sa.Float),
        sa.Column("acoes_novas", sa.Float),
        sa.Column("valor", sa.Float),
        _momento("coletado_em"),
    )


def downgrade() -> None:
    op.drop_table("fre_eventos_de_capital")
    op.drop_table("fre_proventos")
