"""As tentativas de ler uma fonte, tiradas do registro de coletas (`src/banco/coletas.py`).

O registro tem uma linha por download, com a situação ("ok", "falhou", "nao_encontrado"). Só "ok"
conta como leitura boa: o arquivo que a fonte ainda não publicou também não foi lido. A tabela é
global (as coletas são da base, não de uma conta), então não há `usuario_id` a filtrar.
"""

from datetime import date

import sqlalchemy as sa

from base.publicacao import dia_da_coleta
from src.banco.coletas import LIMITE_DA_URL
from src.banco.modelo import coletas
from src.eventos_de_pj.evento import Tentativa

SITUACAO_OK = "ok"


def tentativas_da_url(
    conexao: sa.Connection, url: str, *, periodo: date | None = None
) -> list[Tentativa]:
    """Cada download de `url`, como tentativa de ler o `periodo`, da mais antiga para a mais nova.

    Sem `periodo`, cada tentativa vale para o próprio dia (o arquivo do dia, como o cadastro da CVM).
    O dia é o de São Paulo, o mesmo das versões guardadas (`base.publicacao.dia_da_coleta`).
    """
    linhas = conexao.execute(
        sa.select(coletas.c.baixado_em, coletas.c.situacao)
        .where(coletas.c.url == url[:LIMITE_DA_URL])
        .order_by(coletas.c.baixado_em)
    )
    tentativas = []
    for linha in linhas:
        dia = dia_da_coleta(linha.baixado_em).date()
        tentativas.append(
            Tentativa(
                periodo=dia if periodo is None else periodo,
                dia=dia,
                ok=linha.situacao == SITUACAO_OK,
            )
        )
    return tentativas
