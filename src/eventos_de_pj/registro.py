"""As tentativas de ler uma fonte, tiradas do registro de coletas (`src/banco/coletas.py`).

O registro tem uma linha por download, com a situação ("ok", "falhou", "nao_encontrado"). Só "ok"
conta como leitura boa: o arquivo que a fonte ainda não publicou também não foi lido. A tabela é
global (as coletas são da base, não de uma conta), então não há `usuario_id` a filtrar.
"""

from datetime import date

import sqlalchemy as sa

from src.banco.coletas import LIMITE_DA_URL
from src.banco.modelo import coletas
from src.eventos_de_pj.evento import Tentativa

SITUACAO_OK = "ok"


def tentativas_da_url(
    conexao: sa.Connection, url: str, *, periodo: date
) -> list[Tentativa]:
    """Cada download de `url`, como tentativa de ler o `periodo`, da mais antiga para a mais nova."""
    linhas = conexao.execute(
        sa.select(coletas.c.baixado_em, coletas.c.situacao)
        .where(coletas.c.url == url[:LIMITE_DA_URL])
        .order_by(coletas.c.baixado_em)
    )
    return [
        Tentativa(
            periodo=periodo,
            dia=linha.baixado_em.date(),
            ok=linha.situacao == SITUACAO_OK,
        )
        for linha in linhas
    ]
