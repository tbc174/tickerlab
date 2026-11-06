"""Reaplica as exclusões de conta depois de restaurar uma cópia de segurança.

A política de privacidade promete que restaurar o backup não traz de volta quem mandou apagar a
conta. O backup é de antes do pedido; a auditoria (`conta_apagada`, só o id) é mais nova, e é ela
que diz quem sumiu. A sala de dados tem a própria regra (`src/sala/restauracao.py`); esta cobre a
conta e tudo o que depende dela em cascata. É o que o teste mensal de restauração roda, em SQL
equivalente, no PostgreSQL descartável.
"""

from dataclasses import dataclass
from pathlib import Path

import sqlalchemy as sa

from src import auditoria as registro
from src.banco.modelo import auditoria, usuarios
from src.sala.documentos import apagar_arquivos_da_conta


@dataclass(frozen=True)
class ContasReaplicadas:
    contas: int


def reaplicar_contas_apagadas(
    conexao: sa.Connection, *, raiz: Path | None = None
) -> ContasReaplicadas:
    """Apaga de novo as contas que a auditoria diz que foram excluídas, no banco e no disco.

    Só mexe em conta que voltou com a restauração; rodar duas vezes dá o mesmo resultado e não
    escreve nada na auditoria (ela é a fonte, não o destino). O banco restaurado precisa ter a
    auditoria mais nova que a cópia dos dados.
    """
    voltaram = [
        linha.id
        for linha in conexao.execute(
            sa.select(usuarios.c.id).where(
                usuarios.c.id.in_(
                    sa.select(auditoria.c.alvo_id).where(
                        auditoria.c.acao == registro.ACAO_CONTA_APAGADA,
                        auditoria.c.alvo_id.is_not(None),
                    )
                )
            )
        )
    ]
    for usuario_id in voltaram:
        apagar_arquivos_da_conta(conexao, usuario_id=usuario_id, raiz=raiz)
    if voltaram:
        conexao.execute(sa.delete(usuarios).where(usuarios.c.id.in_(voltaram)))
    return ContasReaplicadas(len(voltaram))
