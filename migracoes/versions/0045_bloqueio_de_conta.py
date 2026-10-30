"""Bloqueio de uma conta só, durante um incidente (linha 306 da fila; plano de incidente, passo 4)

Revisão: 0045 (reservada no quadro de sessões em 24/10; encadeada na última da `main`, 0044).
Desenho, migração e texto aprovados pelo Tiago em 24/10 15h41.

Até aqui o plano de incidente só sabia derrubar o app inteiro. Duas colunas novas em `usuarios`, no
mesmo molde da suspensão das organizações: `bloqueada_em` (quando) e `motivo_do_bloqueio` (só um
código, nunca texto livre), com a regra "as duas vazias ou as duas preenchidas". Não é um papel novo:
o login pelo Google de quem está em `TICKERLAB_ADMINS` devolveria o papel `admin` sozinho, e o
desbloqueio precisaria lembrar o papel de antes.

Caminho de volta: o `downgrade` tira as duas colunas e as duas regras. Perde só a marca do bloqueio
(a conta volta a entrar); nenhum dado da conta sai.
"""

from collections.abc import Generator
from contextlib import contextmanager

import sqlalchemy as sa
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None

TABELA = "usuarios"
MOTIVOS = ("abuso", "acesso_de_terceiro", "incidente", "pedido_do_titular")
REGRAS = {
    "motivo_do_bloqueio": "motivo_do_bloqueio IS NULL OR motivo_do_bloqueio IN ("
    + ", ".join(f"'{m}'" for m in MOTIVOS)
    + ")",
    "bloqueio": "(bloqueada_em IS NULL) = (motivo_do_bloqueio IS NULL)",
}


@contextmanager
def _sem_cascata_no_sqlite() -> Generator[None]:
    """No SQLite o lote recria `usuarios` (copia, apaga a velha, renomeia): com as chaves
    estrangeiras ligadas, apagar a velha levaria junto, em cascata, tudo o que é das contas.
    Mesmo cuidado da 0039. No PostgreSQL o lote é um ALTER TABLE comum."""
    sqlite = op.get_bind().dialect.name == "sqlite"
    if sqlite:
        op.execute("PRAGMA foreign_keys=OFF")
    try:
        yield
    finally:
        if sqlite:
            op.execute("PRAGMA foreign_keys=ON")


def upgrade() -> None:
    with _sem_cascata_no_sqlite(), op.batch_alter_table(TABELA) as lote:
        lote.add_column(sa.Column("bloqueada_em", sa.DateTime(timezone=True)))
        lote.add_column(sa.Column("motivo_do_bloqueio", sa.String(30)))
        for nome, regra in REGRAS.items():
            lote.create_check_constraint(op.f(f"ck_{TABELA}_{nome}"), regra)


def downgrade() -> None:
    with _sem_cascata_no_sqlite(), op.batch_alter_table(TABELA) as lote:
        for nome in reversed(REGRAS):
            lote.drop_constraint(op.f(f"ck_{TABELA}_{nome}"), type_="check")
        lote.drop_column("motivo_do_bloqueio")
        lote.drop_column("bloqueada_em")
