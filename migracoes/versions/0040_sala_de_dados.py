"""Sala de dados por operação: operações, documentos, evidências, contradições e checklist (B-20, PR 1)

Revisão: 0040 (encadeada na 0039; reservada no quadro de sessões em 20/10)

Cinco tabelas novas; nada do que existe muda. Cada operação (M&A, dívida, crédito, FIDC) é uma sala.
Isolamento no próprio banco (D11 do plano): toda tabela tem `usuario_id` e se liga à operação pela
chave composta (operacao_id, usuario_id) -> operacoes(id, usuario_id), então uma linha de uma conta
não entra na sala de outra; evidência, contradição e item do checklist apontam o documento ou a
evidência pela chave composta com a operação, então não ligam duas salas. Tudo é dado do usuário:
sai com a conta e com a operação (cascata). O item do checklist só aponta o documento (sem cascata):
apagar o documento solta o item antes (`src/banco/sala.py`).

`chave_cifrada`, `versao_da_chave` e `nonce` ficam vazios até o PR 2 (arquivos cifrados).

Caminho de volta: o `downgrade` apaga as cinco tabelas. Vale só antes de haver sala de verdade;
depois disso, a volta é o backup.
"""

import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

TABELAS_DA_SALA = (
    "checklist_da_sala",
    "contradicoes_da_sala",
    "evidencias_da_sala",
    "documentos_da_sala",
    "operacoes",
)


def _momento(nome: str) -> sa.Column:
    return sa.Column(
        nome, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def _dono(tabela: str) -> list:
    """A coluna `usuario_id` com a chave para a conta, apagada junto com ela."""
    return [
        sa.Column("usuario_id", sa.Uuid, nullable=False),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=f"fk_{tabela}_usuario_id_usuarios",
            ondelete="CASCADE",
        ),
    ]


def _da_operacao(tabela: str) -> list:
    """A coluna `operacao_id` com a chave composta para a operação da mesma conta."""
    return [
        sa.Column("operacao_id", sa.Uuid, nullable=False),
        sa.ForeignKeyConstraint(
            ["operacao_id", "usuario_id"],
            ["operacoes.id", "operacoes.usuario_id"],
            name=f"fk_{tabela}_operacao_id_operacoes",
            ondelete="CASCADE",
        ),
    ]


def _da_mesma_sala(
    tabela: str, coluna: str, alvo: str, ondelete: str | None = "CASCADE"
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


def _criar_operacoes() -> None:
    op.create_table(
        "operacoes",
        sa.Column("id", sa.Uuid, nullable=False),
        *_dono("operacoes"),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("situacao", sa.String(10), nullable=False, server_default="aberta"),
        sa.Column("retencao_ate", sa.Date, nullable=False),
        sa.Column("chave_cifrada", sa.LargeBinary, nullable=True),
        sa.Column("versao_da_chave", sa.Integer, nullable=True),
        _momento("criada_em"),
        _momento("atualizada_em"),
        sa.PrimaryKeyConstraint("id", name="pk_operacoes"),
        sa.UniqueConstraint("id", "usuario_id", name="uq_operacoes_id_usuario_id"),
        _entre("operacoes", "tipo", ("ma", "divida", "credito", "fidc")),
        _entre("operacoes", "situacao", ("aberta", "encerrada")),
        sa.CheckConstraint("length(nome) BETWEEN 1 AND 200", name="ck_operacoes_nome"),
        sa.CheckConstraint(
            "(chave_cifrada IS NULL) = (versao_da_chave IS NULL)",
            name="ck_operacoes_chave",
        ),
    )
    op.create_index(
        "ix_operacoes_usuario_id_criada_em", "operacoes", ["usuario_id", "criada_em"]
    )
    op.create_index("ix_operacoes_retencao_ate", "operacoes", ["retencao_ate"])


def _criar_documentos() -> None:
    op.create_table(
        "documentos_da_sala",
        sa.Column("id", sa.Uuid, nullable=False),
        *_dono("documentos_da_sala"),
        *_da_operacao("documentos_da_sala"),
        sa.Column("nome_original", sa.String(255), nullable=False),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("tamanho_bytes", sa.BigInteger, nullable=False),
        sa.Column("paginas", sa.Integer, nullable=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("nonce", sa.LargeBinary, nullable=True),
        sa.Column("situacao", sa.String(20), nullable=False, server_default="na_fila"),
        sa.Column("lido_por", sa.String(40), nullable=True),
        _momento("recebido_em"),
        sa.PrimaryKeyConstraint("id", name="pk_documentos_da_sala"),
        sa.UniqueConstraint(
            "id", "operacao_id", "usuario_id", name="uq_documentos_da_sala_id_operacao"
        ),
        sa.UniqueConstraint(
            "operacao_id", "sha256", name="uq_documentos_da_sala_sha256"
        ),
        _entre("documentos_da_sala", "tipo", ("pdf", "xlsx", "docx", "csv")),
        _entre(
            "documentos_da_sala",
            "situacao",
            ("na_fila", "lido", "sem_texto", "erro_na_leitura"),
        ),
        sa.CheckConstraint("tamanho_bytes > 0", name="ck_documentos_da_sala_tamanho"),
        sa.CheckConstraint(
            "paginas IS NULL OR paginas >= 0", name="ck_documentos_da_sala_paginas"
        ),
        sa.CheckConstraint("length(sha256) = 64", name="ck_documentos_da_sala_sha256"),
        sa.CheckConstraint(
            "length(nome_original) BETWEEN 1 AND 255", name="ck_documentos_da_sala_nome"
        ),
    )
    op.create_index(
        "ix_documentos_da_sala_usuario_id", "documentos_da_sala", ["usuario_id"]
    )


def _criar_evidencias() -> None:
    op.create_table(
        "evidencias_da_sala",
        sa.Column("id", sa.Uuid, nullable=False),
        *_dono("evidencias_da_sala"),
        *_da_operacao("evidencias_da_sala"),
        sa.Column("documento_id", sa.Uuid, nullable=False),
        sa.Column("metrica", sa.String(120), nullable=False),
        sa.Column("periodo", sa.String(20), nullable=False),
        sa.Column("valor_numero", sa.Numeric(28, 6), nullable=True),
        sa.Column("valor_texto", sa.String(500), nullable=True),
        sa.Column("unidade", sa.String(20), nullable=True),
        sa.Column("moeda", sa.String(3), nullable=True),
        sa.Column("pagina", sa.Integer, nullable=True),
        sa.Column("secao", sa.String(200), nullable=True),
        sa.Column("tabela", sa.String(200), nullable=True),
        sa.Column("trecho", sa.String(2000), nullable=True),
        sa.Column("conferida", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("extraido_por", sa.String(10), nullable=False),
        sa.Column(
            "estado_de_revisao",
            sa.String(12),
            nullable=False,
            server_default="automatico",
        ),
        _momento("criada_em"),
        sa.PrimaryKeyConstraint("id", name="pk_evidencias_da_sala"),
        _da_mesma_sala("evidencias_da_sala", "documento_id", "documentos_da_sala"),
        sa.UniqueConstraint(
            "id", "operacao_id", "usuario_id", name="uq_evidencias_da_sala_id_operacao"
        ),
        _entre("evidencias_da_sala", "extraido_por", ("pessoa", "regra")),
        _entre(
            "evidencias_da_sala",
            "estado_de_revisao",
            ("automatico", "revisado", "contestado", "rejeitado"),
        ),
        sa.CheckConstraint(
            "valor_numero IS NOT NULL OR valor_texto IS NOT NULL",
            name="ck_evidencias_da_sala_valor",
        ),
        sa.CheckConstraint(
            "pagina IS NULL OR pagina >= 1", name="ck_evidencias_da_sala_pagina"
        ),
    )
    op.create_index(
        "ix_evidencias_da_sala_usuario_id", "evidencias_da_sala", ["usuario_id"]
    )
    op.create_index(
        "ix_evidencias_da_sala_documento_id",
        "evidencias_da_sala",
        ["documento_id", "operacao_id", "usuario_id"],
    )


def _criar_contradicoes() -> None:
    op.create_table(
        "contradicoes_da_sala",
        sa.Column("id", sa.Uuid, nullable=False),
        *_dono("contradicoes_da_sala"),
        *_da_operacao("contradicoes_da_sala"),
        sa.Column("evidencia_a", sa.Uuid, nullable=False),
        sa.Column("evidencia_b", sa.Uuid, nullable=False),
        sa.Column("diferenca", sa.Numeric(28, 6), nullable=True),
        sa.Column("estado", sa.String(12), nullable=False, server_default="aberta"),
        sa.Column("nota", sa.String(2000), nullable=True),
        _momento("criada_em"),
        sa.PrimaryKeyConstraint("id", name="pk_contradicoes_da_sala"),
        _da_mesma_sala("contradicoes_da_sala", "evidencia_a", "evidencias_da_sala"),
        _da_mesma_sala("contradicoes_da_sala", "evidencia_b", "evidencias_da_sala"),
        sa.UniqueConstraint(
            "evidencia_a", "evidencia_b", name="uq_contradicoes_da_sala_evidencias"
        ),
        sa.CheckConstraint(
            "evidencia_a <> evidencia_b", name="ck_contradicoes_da_sala_duas_evidencias"
        ),
        _entre("contradicoes_da_sala", "estado", ("aberta", "explicada", "descartada")),
    )
    op.create_index(
        "ix_contradicoes_da_sala_usuario_id", "contradicoes_da_sala", ["usuario_id"]
    )
    op.create_index(
        "ix_contradicoes_da_sala_evidencia_b",
        "contradicoes_da_sala",
        ["evidencia_b", "operacao_id", "usuario_id"],
    )


def _criar_checklist() -> None:
    op.create_table(
        "checklist_da_sala",
        sa.Column("id", sa.Uuid, nullable=False),
        *_dono("checklist_da_sala"),
        *_da_operacao("checklist_da_sala"),
        sa.Column("codigo", sa.String(60), nullable=False),
        sa.Column("estado", sa.String(15), nullable=False, server_default="pendente"),
        sa.Column("documento_id", sa.Uuid, nullable=True),
        sa.Column("nota", sa.String(2000), nullable=True),
        _momento("atualizado_em"),
        sa.PrimaryKeyConstraint("id", name="pk_checklist_da_sala"),
        _da_mesma_sala(
            "checklist_da_sala", "documento_id", "documentos_da_sala", ondelete=None
        ),
        sa.UniqueConstraint(
            "operacao_id", "codigo", name="uq_checklist_da_sala_codigo"
        ),
        _entre(
            "checklist_da_sala",
            "estado",
            ("pendente", "recebido", "revisado", "contestado", "nao_se_aplica"),
        ),
    )
    op.create_index(
        "ix_checklist_da_sala_usuario_id", "checklist_da_sala", ["usuario_id"]
    )
    op.create_index(
        "ix_checklist_da_sala_documento_id",
        "checklist_da_sala",
        ["documento_id", "operacao_id", "usuario_id"],
    )


def upgrade() -> None:
    _criar_operacoes()
    _criar_documentos()
    _criar_evidencias()
    _criar_contradicoes()
    _criar_checklist()


def downgrade() -> None:
    for tabela in TABELAS_DA_SALA:
        op.drop_table(tabela)
