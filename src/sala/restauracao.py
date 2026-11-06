"""Reaplica as exclusões depois de restaurar o backup da sala (decisão D4 do plano do B-20).

O backup da sala (`sala-*.tar.age`) tem até 14 dias; o do banco geral, que leva a auditoria, é
mais novo. Restaurar a sala de ontem traria de volta o que a pessoa apagou hoje (ou o que o
expurgo levou): este módulo apaga de novo tudo o que a auditoria diz que foi excluído e tudo o que
é de conta que não existe mais, no banco e no disco. É o que o teste de restauração mensal
(`servidor/scripts/testar-restauracao-backup.sh`) roda, em SQL equivalente, no PostgreSQL
descartável; aqui fica a versão em Python, com teste, que é a regra de referência.
"""

import uuid
from dataclasses import dataclass
from pathlib import Path

import sqlalchemy as sa

from src import auditoria as registro
from src.banco.modelo import auditoria, documentos_da_sala, operacoes, usuarios
from src.sala import guarda

ACOES_QUE_EXCLUEM_A_OPERACAO = (
    registro.ACAO_OPERACAO_APAGADA,
    registro.ACAO_OPERACAO_EXPIRADA,
)


@dataclass(frozen=True)
class ExclusoesReaplicadas:
    operacoes: int
    documentos: int
    pastas: int


def _alvos(acoes: tuple[str, ...]) -> sa.Select:
    return sa.select(auditoria.c.alvo_id).where(
        auditoria.c.acao.in_(acoes), auditoria.c.alvo_id.is_not(None)
    )


def _apagar_pastas_sem_operacao(conexao: sa.Connection, raiz: Path) -> int:
    if not raiz.is_dir():
        return 0
    vivas = {linha.id for linha in conexao.execute(sa.select(operacoes.c.id))}
    apagadas = 0
    for item in raiz.iterdir():
        try:
            operacao_id = uuid.UUID(item.name)
        except ValueError:
            continue
        if operacao_id not in vivas:
            guarda.apagar_operacao(raiz, operacao_id)
            apagadas += 1
    return apagadas


def _apagar_arquivos_dos_documentos_excluidos(
    conexao: sa.Connection, raiz: Path
) -> None:
    """Documento apagado de uma sala que continua viva: o arquivo restaurado sai do disco."""
    vivos = {linha.id for linha in conexao.execute(sa.select(documentos_da_sala.c.id))}
    for operacao in conexao.execute(sa.select(operacoes.c.id)):
        pasta = guarda.pasta_da_operacao(raiz, operacao.id)
        if not pasta.is_dir():
            continue
        for arquivo in pasta.iterdir():
            documento_id = arquivo.name.split(".")[0]
            try:
                if uuid.UUID(documento_id) not in vivos:
                    arquivo.unlink(missing_ok=True)
            except ValueError:
                continue


def reaplicar_exclusoes(
    conexao: sa.Connection, *, raiz: Path | None = None
) -> ExclusoesReaplicadas:
    """Apaga o que a auditoria diz que foi excluído (e o que é de conta apagada), banco e disco.

    O banco restaurado precisa ter a auditoria mais nova que a sala (o backup geral é do dia).
    """
    raiz = raiz or guarda.pasta_da_sala()
    documentos = conexao.execute(
        sa.delete(documentos_da_sala).where(
            documentos_da_sala.c.id.in_(_alvos((registro.ACAO_DOCUMENTO_APAGADO,)))
        )
    ).rowcount
    excluidas = conexao.execute(
        sa.delete(operacoes).where(
            sa.or_(
                operacoes.c.id.in_(_alvos(ACOES_QUE_EXCLUEM_A_OPERACAO)),
                operacoes.c.usuario_id.not_in(sa.select(usuarios.c.id)),
            )
        )
    ).rowcount
    _apagar_arquivos_dos_documentos_excluidos(conexao, raiz)
    pastas = _apagar_pastas_sem_operacao(conexao, raiz)
    return ExclusoesReaplicadas(excluidas, documentos, pastas)
