"""Compartilhamento seguro: links secretos, com prazo e revogáveis (onda 4 da ADR 0046)

Revisão: 0034

Uma tabela nova, `compartilhamentos`: cada linha é um link para a ficha "Foi sorte?" congelada
(coluna `ficha`) ou para um PDF original da biblioteca (`relatorio_id`). O banco guarda só o hash
SHA-256 do código do link, nunca o código. Dado do usuário: apagado junto com a conta, e o link de
PDF some junto com o PDF guardado (chaves estrangeiras em cascata). Nada do que existe muda.

O número 0033 é da migração da "Campanha" (ainda fora da `main` quando esta foi escrita): se ela
entrar antes, o `down_revision` daqui passa a ser "0033".
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0034"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "compartilhamentos",
        sa.Column("id", sa.Uuid, nullable=False),
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.Column("codigo_hash", sa.String(64), nullable=False),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("relatorio_id", sa.Uuid, nullable=True),
        sa.Column(
            "ficha", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=True
        ),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revogado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("visitas", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ultima_visita_em", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_compartilhamentos"),
        sa.UniqueConstraint("codigo_hash", name="uq_compartilhamentos_codigo_hash"),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name="fk_compartilhamentos_usuario_id_usuarios",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["relatorio_id"],
            ["pdfs_originais.relatorio_id"],
            name="fk_compartilhamentos_relatorio_id_pdfs_originais",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "(tipo = 'ficha' AND ficha IS NOT NULL AND relatorio_id IS NULL) OR "
            "(tipo = 'pdf' AND relatorio_id IS NOT NULL AND ficha IS NULL)",
            name="ck_compartilhamentos_tipo",
        ),
        sa.CheckConstraint("expira_em > criado_em", name="ck_compartilhamentos_prazo"),
        sa.CheckConstraint("visitas >= 0", name="ck_compartilhamentos_visitas"),
        sa.CheckConstraint("length(titulo) >= 1", name="ck_compartilhamentos_titulo"),
    )
    op.create_index(
        "ix_compartilhamentos_usuario_id_criado_em",
        "compartilhamentos",
        ["usuario_id", "criado_em"],
    )
    op.create_index(
        "ix_compartilhamentos_relatorio_id", "compartilhamentos", ["relatorio_id"]
    )


def downgrade() -> None:
    op.drop_table("compartilhamentos")
