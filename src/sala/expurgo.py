"""Expurgo diário da sala de dados (decisões D13 e D14 do plano do B-20).

Apaga as operações cujo prazo de guarda (`retencao_ate`) já passou e as pastas órfãs do disco.
A ordem importa: primeiro a linha do banco, que leva a chave da operação (o arquivo fica ilegível
na hora, mesmo se a remoção do disco falhar), depois a pasta. Pasta que sobrar sem operação é
apagada na varredura de órfãs. A auditoria guarda só ids; nome de operação, de arquivo e de dono
nunca vão para o registro.

Não há `usuario_id` aqui de propósito: é o único código da sala que age sobre todas as contas, e
só roda pelo cron (`scripts/expurgar_salas.py`), nunca por rota.
"""

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import sqlalchemy as sa

from src import auditoria
from src.banco.modelo import operacoes
from src.sala import guarda

log = logging.getLogger("tickerlab.expurgo")

SEGUNDOS_POR_DIA = 86_400
# uma pasta sem operação só é órfã depois de um dia: um envio cria a pasta antes de a linha chegar
IDADE_MINIMA_DA_PASTA_ORFA_EM_DIAS = 1


@dataclass(frozen=True)
class ResultadoDoExpurgo:
    operacoes_vencidas: int
    pastas_orfas: int
    falhas_no_disco: int


def _vencidas(conexao: sa.Connection, hoje: date) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """(operação, dono) das operações cujo prazo terminou ontem ou antes; no dia do prazo ainda vale."""
    linhas = conexao.execute(
        sa.select(operacoes.c.id, operacoes.c.usuario_id).where(
            operacoes.c.retencao_ate < hoje
        )
    )
    return [(linha.id, linha.usuario_id) for linha in linhas]


def _apagar_pasta(raiz: Path, operacao_id: uuid.UUID) -> bool:
    try:
        guarda.apagar_operacao(raiz, operacao_id)
    except OSError:
        return False
    return True


def expurgar_vencidas(
    conexao: sa.Connection, *, hoje: date, raiz: Path
) -> tuple[int, int]:
    """Apaga as operações vencidas (banco, chave e disco); devolve (apagadas, falhas no disco)."""
    falhas = 0
    vencidas = _vencidas(conexao, hoje)
    for operacao_id, dono_id in vencidas:
        conexao.execute(sa.delete(operacoes).where(operacoes.c.id == operacao_id))
        auditoria.registrar(
            conexao, dono_id, auditoria.ACAO_OPERACAO_EXPIRADA, operacao_id, {}
        )
        if not _apagar_pasta(raiz, operacao_id):
            falhas += 1
    return len(vencidas), falhas


def _pastas_de_operacao(raiz: Path) -> list[tuple[uuid.UUID, Path]]:
    if not raiz.is_dir():
        return []
    pastas = []
    for item in raiz.iterdir():
        try:
            pastas.append((uuid.UUID(item.name), item))
        except ValueError:
            continue  # o que não é UUID não é pasta de operação: não se mexe
    return pastas


def expurgar_orfas(
    conexao: sa.Connection, *, raiz: Path, agora: float | None = None
) -> tuple[int, int]:
    """Apaga as pastas sem operação no banco (e mais velhas que um dia); (apagadas, falhas)."""
    agora = time.time() if agora is None else agora
    limite = agora - IDADE_MINIMA_DA_PASTA_ORFA_EM_DIAS * SEGUNDOS_POR_DIA
    pastas = _pastas_de_operacao(raiz)
    existentes = {linha.id for linha in conexao.execute(sa.select(operacoes.c.id))}
    apagadas = falhas = 0
    for operacao_id, pasta in pastas:
        if operacao_id in existentes or pasta.lstat().st_mtime > limite:
            continue
        if _apagar_pasta(raiz, operacao_id):
            apagadas += 1
        else:
            falhas += 1
    return apagadas, falhas


def expurgar(
    conexao: sa.Connection,
    *,
    hoje: date,
    raiz: Path | None = None,
    agora: float | None = None,
) -> ResultadoDoExpurgo:
    """O expurgo inteiro: operações vencidas e depois as pastas órfãs."""
    raiz = raiz or guarda.pasta_da_sala()
    vencidas, falhas = expurgar_vencidas(conexao, hoje=hoje, raiz=raiz)
    orfas, falhas_orfas = expurgar_orfas(conexao, raiz=raiz, agora=agora)
    return ResultadoDoExpurgo(vencidas, orfas, falhas + falhas_orfas)
