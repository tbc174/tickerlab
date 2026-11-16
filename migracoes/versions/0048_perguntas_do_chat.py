"""Perguntas do chat: a cota de cada conta e o gasto do mês do chat de IA do app (linha 903)

Revisão: 0048 (a próxima livre no quadro de sessões; desce da 0047, a última da `main`)

Uma tabela nova; nada do que existe muda. Cada pergunta ao chat vira uma linha antes de o modelo ser
chamado (é ela que conta na cota de 50 por mês e 10 por dia da conta) e, no fim, recebe os tokens, o custo
e a latência. A soma do custo do mês é o que pausa o chat no teto (`src/planos.py`, `LIMITES_DO_CHAT`).

Sem dado de pessoa novo e sem texto: nem a pergunta nem a resposta são guardadas, só ids e números. Apagar
a conta solta a linha da conta (SET NULL), que fica só com números: o gasto do mês continua certo, e a linha
não diz mais de quem era. O mesmo vale para a organização.

Caminho de volta: o `downgrade` apaga a tabela nova. Sem ela a rota do chat não tem como contar a cota,
mas o chat nasce desligado (`TICKERLAB_CHAT`), e desligado ele não lê a tabela.
"""

import sqlalchemy as sa
from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None

TABELA = "perguntas_do_chat"
INDICE_DA_CONTA = f"ix_{TABELA}_usuario_id"
INDICE_DO_MES = f"ix_{TABELA}_feita_em"


def upgrade() -> None:
    op.create_table(
        TABELA,
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("usuario_id", sa.Uuid, nullable=True),
        sa.Column("organizacao_id", sa.Uuid, nullable=True),
        sa.Column("feita_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("modelo", sa.String(64), nullable=False),
        sa.Column("estado", sa.String(16), nullable=False),
        sa.Column("tokens_de_entrada", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_de_saida", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "tokens_lidos_do_cache", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column(
            "tokens_gravados_no_cache", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column(
            "custo_em_microdolares", sa.BigInteger, nullable=False, server_default="0"
        ),
        sa.Column("latencia_ms", sa.Integer, nullable=True),
        sa.Column(
            "chamadas_de_ferramenta", sa.Integer, nullable=False, server_default="0"
        ),
        sa.PrimaryKeyConstraint("id", name=f"pk_{TABELA}"),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=f"fk_{TABELA}_usuario_id_usuarios",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organizacao_id"],
            ["organizacoes.id"],
            name=f"fk_{TABELA}_organizacao_id_organizacoes",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "estado IN ('em_curso', 'respondida', 'recusada', 'erro')",
            name=f"ck_{TABELA}_estado",
        ),
    )
    op.create_index(INDICE_DA_CONTA, TABELA, ["usuario_id", "feita_em"])
    op.create_index(INDICE_DO_MES, TABELA, ["feita_em"])


def downgrade() -> None:
    op.drop_index(INDICE_DO_MES, table_name=TABELA)
    op.drop_index(INDICE_DA_CONTA, table_name=TABELA)
    op.drop_table(TABELA)
