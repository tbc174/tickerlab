"""Cadastro completo da CVM na `setores_cvm` (linha 49 da fila; relatório do CNPJ, molde B)

Revisão: 0044 (reservada no quadro de sessões em 22/10; encadeada na última da `main`, 0043)

O relatório do CNPJ dizia que situação, categoria e data de registro na CVM "ainda não estão no banco
do app". Estão no mesmo `cad_cia_aberta.csv` que o VPS já baixa todo dia (`fundamentos-cvm`,
`scripts/atualizar_fundamentos.py`), de onde só o setor era aproveitado. Cinco colunas novas na
`setores_cvm`, todas opcionais: `situacao` (SIT), `situacao_desde` (DT_INI_SIT), `categoria`
(CATEG_REG), `registro` (DT_REG) e `atualizado_em` (quando a coleta gravou). Nada pessoal: é o
cadastro público da companhia.

"Sem olhar o futuro": a situação muda com o tempo, então a linha guarda desde quando ela vale e o dia
em que foi lida; o relatório mostra a data junto do dado. O histórico diário fica no acervo de casa.

Caminho de volta: o `downgrade` apaga as cinco colunas; o setor, que já existia, fica.
"""

import sqlalchemy as sa
from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None

TABELA = "setores_cvm"
COLUNAS = (
    sa.Column("situacao", sa.String(40), nullable=True),
    sa.Column("situacao_desde", sa.Date, nullable=True),
    sa.Column("categoria", sa.String(40), nullable=True),
    sa.Column("registro", sa.Date, nullable=True),
    sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
)


def upgrade() -> None:
    with op.batch_alter_table(TABELA) as lote:
        for coluna in COLUNAS:
            lote.add_column(coluna)


def downgrade() -> None:
    with op.batch_alter_table(TABELA) as lote:
        for coluna in reversed(COLUNAS):
            lote.drop_column(coluna.name)
