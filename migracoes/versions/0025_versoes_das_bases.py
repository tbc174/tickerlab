"""Versões das demonstrações, negociações e detentores (Radar e base histórica, PR 4; ADR 0024)

Revisão: 0025

Uma tabela `<base>_versoes` ao lado de cada base que a fonte reapresenta (demonstrações e o índice
dos documentos, negociações de pessoas de dentro, detentores, maiores detentores e cobertura),
com as mesmas colunas, `registrado_em` e `substituido_em`. Só acréscimo; as bases vigentes não
mudam. O que já está no banco entra como a primeira versão conhecida (cópia dentro do banco, em
segundos: o deploy espera o app ficar saudável por pouco tempo).
"""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

CHAVES = {
    "demonstracoes": ("cnpj", "documento", "referencia"),
    "documentos_financeiros": ("cnpj", "documento", "referencia"),
    "negociacoes_internas": ("fonte", "documento"),
    "detentores_por_acao": ("fonte", "competencia"),
    "maiores_detentores": ("fonte", "competencia"),
    "cobertura_de_detentores": ("fonte", "competencia"),
}
CONTROLE = ("id", "ingerido_em", "coletado_em")
# de onde vem o `registrado_em` das linhas que já existem (sem horário próprio: o do documento
# ou da competência; senão, a hora da migração)
REGISTRADO_EM = {
    "documentos_financeiros": "o.coletado_em",
    "negociacoes_internas": "o.ingerido_em",
    "detentores_por_acao": "o.coletado_em",
    "cobertura_de_detentores": "o.coletado_em",
    "demonstracoes": (
        "(SELECT d.coletado_em FROM documentos_financeiros d WHERE d.cnpj = o.cnpj"
        " AND d.documento = o.documento AND d.referencia = o.referencia)"
    ),
    "maiores_detentores": (
        "(SELECT c.coletado_em FROM cobertura_de_detentores c WHERE c.fonte = o.fonte"
        " AND c.competencia = o.competencia)"
    ),
}


def _colunas(original: sa.Table) -> list[str]:
    return [c.name for c in original.columns if c.name not in CONTROLE]


def upgrade() -> None:
    conexao = op.get_bind()
    for nome, chave in CHAVES.items():
        original = sa.Table(nome, sa.MetaData(), autoload_with=conexao)
        colunas = _colunas(original)
        op.create_table(
            f"{nome}_versoes",
            sa.Column(
                "id_da_versao",
                sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
                primary_key=True,
                autoincrement=True,
            ),
            *[
                sa.Column(c, original.c[c].type, nullable=original.c[c].nullable)
                for c in colunas
            ],
            sa.Column(
                "registrado_em",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("substituido_em", sa.DateTime(timezone=True)),
        )
        op.create_index(f"ix_{nome}_versoes_chave", f"{nome}_versoes", list(chave))
        lista = ", ".join(colunas)
        com_o = ", ".join(f"o.{c}" for c in colunas)
        op.execute(
            f"INSERT INTO {nome}_versoes ({lista}, registrado_em)"
            f" SELECT {com_o}, COALESCE({REGISTRADO_EM[nome]}, CURRENT_TIMESTAMP)"
            f" FROM {nome} o"
        )


def downgrade() -> None:
    for nome in reversed(CHAVES):
        op.drop_index(f"ix_{nome}_versoes_chave", table_name=f"{nome}_versoes")
        op.drop_table(f"{nome}_versoes")
