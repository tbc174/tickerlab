"""PDF original dos relatórios na biblioteca (Master v3, Fase C.4; ADR 0021 do autor)

Revisão: 0019

Além de "reabrir com os dados de hoje", a biblioteca guarda o PDF como foi entregue, com o hash
SHA-256 e as versões das fórmulas e dos dados. Dado do usuário: apagado junto com a conta e com o
relatório (chaves estrangeiras em cascata), ao excluir da biblioteca, depois de 1 ano e quando
passa da cota do plano; incluído na exportação dos dados. O relatório "Minha carteira" nunca é
guardado.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pdfs_originais",
        sa.Column("relatorio_id", sa.Uuid, nullable=False),
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.Column("pdf", sa.LargeBinary, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("tamanho", sa.Integer, nullable=False),
        sa.Column(
            "versoes", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False
        ),
        sa.Column(
            "gerado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("relatorio_id", name="pk_pdfs_originais"),
        sa.ForeignKeyConstraint(
            ["relatorio_id"],
            ["relatorios.id"],
            name="fk_pdfs_originais_relatorio_id_relatorios",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name="fk_pdfs_originais_usuario_id_usuarios",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_pdfs_originais_usuario_id_gerado_em",
        "pdfs_originais",
        ["usuario_id", "gerado_em"],
    )


def downgrade() -> None:
    op.drop_index("ix_pdfs_originais_usuario_id_gerado_em", "pdfs_originais")
    op.drop_table("pdfs_originais")
