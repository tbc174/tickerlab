"""A administração das chaves da API externa para a tela do admin (N7, linha 169).

Cada função confere no banco que quem pede é administrador (`exigir_admin`) e só então chama as
consultas de `src/banco/chaves_da_api.py`, as mesmas do script `scripts/chaves_da_api.py`. Quem chama
decide o commit. A chave nova (`ChaveNova.valor`) só existe na volta de `emitir` e `rotacionar`: a
tela mostra uma vez e não guarda; aqui ela não vai para log nem para auditoria (que leva só ids e o
prefixo) e a visão da organização nunca carrega o hash.
"""

import uuid
from dataclasses import dataclass
from datetime import date

import sqlalchemy as sa

from src.administracao import exigir_admin
from src.banco import chaves_da_api as cb
from src.chaves_da_api import ChaveNova

# os erros que o admin pode causar e que a mensagem já explica (a tela mostra o texto, sem traceback)
ERROS_ESPERADOS = (
    cb.OrganizacaoInvalidaError,
    cb.OrganizacaoSuspensaError,
    cb.LimiteDeChavesError,
    cb.ChaveInexistenteError,
    ValueError,
)


@dataclass(frozen=True)
class VisaoDaOrganizacao:
    """O que a tela mostra de uma organização: nunca o hash nem a chave."""

    organizacao: cb.Organizacao
    chaves: list[cb.ChaveListada]
    direitos: list[cb.Direito]
    consumo: cb.ConsumoDoMes


def listar_organizacoes(
    conexao: sa.Connection, ator_id: uuid.UUID
) -> list[cb.Organizacao]:
    exigir_admin(conexao, ator_id)
    return cb.listar_organizacoes(conexao)


def ver_organizacao(
    conexao: sa.Connection, ator_id: uuid.UUID, organizacao_id: uuid.UUID, hoje: date
) -> VisaoDaOrganizacao:
    """Chaves (pelo prefixo), direitos vigentes e consumo do mês de `hoje` (UTC)."""
    exigir_admin(conexao, ator_id)
    organizacao = cb.buscar_organizacao(conexao, organizacao_id)
    if organizacao is None:
        raise cb.OrganizacaoInvalidaError("Organização inexistente.")
    return VisaoDaOrganizacao(
        organizacao=organizacao,
        chaves=cb.listar_chaves(conexao, organizacao_id),
        direitos=cb.direitos_vigentes(conexao, organizacao_id, hoje),
        consumo=cb.consumo_do_mes(conexao, organizacao_id, hoje),
    )


def criar_organizacao(
    conexao: sa.Connection,
    ator_id: uuid.UUID,
    *,
    nome: str,
    cnpj: str | None,
    plano_da_api: str,
) -> cb.Organizacao:
    exigir_admin(conexao, ator_id)
    return cb.criar_organizacao(
        conexao,
        nome=nome,
        cnpj=cnpj or None,
        plano_da_api=plano_da_api,
        ator_id=ator_id,
    )


def emitir_chave(
    conexao: sa.Connection, ator_id: uuid.UUID, organizacao_id: uuid.UUID
) -> ChaveNova:
    exigir_admin(conexao, ator_id)
    return cb.emitir_chave(conexao, organizacao_id=organizacao_id, ator_id=ator_id)


def rotacionar_chave(
    conexao: sa.Connection,
    ator_id: uuid.UUID,
    organizacao_id: uuid.UUID,
    chave_id: uuid.UUID,
) -> ChaveNova:
    exigir_admin(conexao, ator_id)
    return cb.rotacionar_chave(
        conexao, organizacao_id=organizacao_id, chave_id=chave_id, ator_id=ator_id
    )


def revogar_chave(
    conexao: sa.Connection,
    ator_id: uuid.UUID,
    organizacao_id: uuid.UUID,
    chave_id: uuid.UUID,
) -> bool:
    exigir_admin(conexao, ator_id)
    return cb.revogar_chave(
        conexao, organizacao_id=organizacao_id, chave_id=chave_id, ator_id=ator_id
    )


def suspender_organizacao(
    conexao: sa.Connection, ator_id: uuid.UUID, organizacao_id: uuid.UUID, motivo: str
) -> bool:
    exigir_admin(conexao, ator_id)
    return cb.suspender_organizacao(
        conexao, organizacao_id=organizacao_id, motivo=motivo, ator_id=ator_id
    )


def reativar_organizacao(
    conexao: sa.Connection, ator_id: uuid.UUID, organizacao_id: uuid.UUID
) -> bool:
    exigir_admin(conexao, ator_id)
    return cb.reativar_organizacao(
        conexao, organizacao_id=organizacao_id, ator_id=ator_id
    )
