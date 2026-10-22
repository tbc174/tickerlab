"""Troca da chave-mestra da sala sem perder as operações (RIPD da sala, risco R-S2).

O roteiro, em três passos (o script `scripts/trocar_chave_da_sala.py` roda cada um):
1. **Acrescentar** a versão nova na frente da variável (`v2:...,v1:...`): as operações novas já
   saem com ela, as antigas continuam abrindo pela versão gravada.
2. **Reembrulhar** (`reembrulhar`): a chave de cada operação é aberta pela versão que a embrulha e
   embrulhada de novo pela mais nova. Não recifra nenhum arquivo.
3. **Retirar** a versão antiga da variável só quando `pode_retirar` disser que nenhuma operação
   a usa. Atenção: os backups antigos (sala, 14 dias; geral, meses) ainda guardam as chaves
   embrulhadas pela versão antiga. Retire-a do servidor, mas guarde a cópia dela na pasta de
   segredos do Tiago até o último backup que a usa vencer; sem ela, restaurar esse backup deixa os
   arquivos ilegíveis.

Garantias: a chave nova é conferida (abre e dá a mesma chave) antes de gravar; a chave embrulhada e
a versão mudam no mesmo `UPDATE`, então uma operação nunca fica sem chave válida; se alguma versão
estiver faltando na variável, nada é gravado; rodar de novo não muda nada.

Não há `usuario_id` aqui de propósito (como no expurgo): age sobre todas as contas, só pelo script
do servidor, nunca por rota. Nenhuma chave aparece em retorno, log ou mensagem de erro.
"""

import uuid
from dataclasses import dataclass

import sqlalchemy as sa

from src.banco.modelo import operacoes
from src.sala import cofre


class VersaoEmUsoError(ValueError):
    """A versão ainda embrulha a chave de alguma operação (ou é a versão atual)."""


@dataclass(frozen=True)
class ResultadoDaTroca:
    versao_nova: int
    reembrulhadas: int
    ja_na_versao_nova: int


def uso_por_versao(conexao: sa.Connection) -> dict[int, int]:
    """Quantas operações têm a chave embrulhada por cada versão da chave-mestra."""
    linhas = conexao.execute(
        sa.select(operacoes.c.versao_da_chave, sa.func.count())
        .where(operacoes.c.chave_cifrada.is_not(None))
        .group_by(operacoes.c.versao_da_chave)
    )
    return {versao: total for versao, total in linhas}


def _novas_embrulhadas(
    conexao: sa.Connection, versao_nova: int
) -> tuple[list[tuple[uuid.UUID, int, bytes]], int]:
    """(operação, versão que embrulha hoje, chave embrulhada pela nova) e quantas já estão na nova.

    Abre e confere tudo antes de gravar qualquer coisa: se faltar uma versão na variável, ou uma
    chave não abrir, o erro sobe e o banco fica como estava.
    """
    mestra_nova = cofre.chaves_mestras()[versao_nova]
    pendentes = []
    ja_na_nova = 0
    linhas = conexao.execute(
        sa.select(
            operacoes.c.id, operacoes.c.chave_cifrada, operacoes.c.versao_da_chave
        ).where(operacoes.c.chave_cifrada.is_not(None))
    ).all()
    for operacao_id, embrulhada, versao in linhas:
        if versao == versao_nova:
            ja_na_nova += 1
            continue
        chave = cofre.abrir_chave_da_operacao(embrulhada, versao, operacao_id)
        nova = cofre.embrulhar_chave_da_operacao(chave, operacao_id, mestra_nova)
        if cofre.abrir_chave_da_operacao_com(mestra_nova, nova, operacao_id) != chave:
            raise cofre.CifraInvalidaError("A chave reembrulhada não confere.")
        pendentes.append((operacao_id, versao, nova))
    return pendentes, ja_na_nova


def reembrulhar(conexao: sa.Connection) -> ResultadoDaTroca:
    """Passa a chave de cada operação para a versão mais nova da chave-mestra. Idempotente."""
    versao_nova = max(cofre.chaves_mestras())
    pendentes, ja_na_nova = _novas_embrulhadas(conexao, versao_nova)
    reembrulhadas = 0
    for operacao_id, versao_antiga, nova in pendentes:
        # a versão antiga entra no WHERE: quem trocou a chave no meio do caminho não é sobrescrito
        reembrulhadas += conexao.execute(
            sa.update(operacoes)
            .where(
                operacoes.c.id == operacao_id,
                operacoes.c.versao_da_chave == versao_antiga,
            )
            .values(chave_cifrada=nova, versao_da_chave=versao_nova)
        ).rowcount
    return ResultadoDaTroca(versao_nova, reembrulhadas, ja_na_nova)


def pode_retirar(conexao: sa.Connection, versao: int) -> None:
    """Não faz nada se a versão pode sair da variável; senão `VersaoEmUsoError`."""
    if versao == max(cofre.chaves_mestras()):
        raise VersaoEmUsoError("A versão mais nova é a que as operações novas usam.")
    em_uso = uso_por_versao(conexao).get(versao, 0)
    if em_uso:
        raise VersaoEmUsoError(
            f"A versão v{versao} ainda embrulha a chave de {em_uso} operação(ões)."
        )
