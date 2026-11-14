"""Quem é de qual organização e se ela vê pessoa física na tela (ADR 0128, Emenda 1; linha 808).

A regra inteira da permissão mora aqui, para a rota só perguntar `pode_ver_pessoa`:

1. a conta é membro de uma organização (`membros_da_organizacao`: uma conta, uma organização);
2. a conta não está bloqueada e a organização não está suspensa;
3. o contrato da organização tem a linha `pessoa_na_tela`, finalidade `analise`, vigente no dia e
   não suspensa (nem a linha, nem o conjunto para todas as organizações).

Nasce desligado: nenhuma organização tem essa linha até um administrador concedê-la. A permissão é
só da tela com login; a API por chave não a conhece (o portão não tem linha para `pessoa_na_tela`).
A auditoria leva só ids: nunca nome nem e-mail.

O mesmo vínculo responde se a conta é de uma organização do piloto (`e_do_piloto`, D11): os passos 1 e 2
acima e a marca de piloto da organização vigente no dia, a mesma que vale para a chave dela na API externa.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

import sqlalchemy as sa

from src import auditoria
from src.banco import chaves_da_api as cb
from src.banco.modelo import (
    identidades,
    membros_da_organizacao,
    organizacoes,
    usuarios,
)

CONJUNTO_DE_PESSOA_NA_TELA = "pessoa_na_tela"
FINALIDADE_DA_TELA = "analise"


class ContaInexistenteError(ValueError):
    """A conta não existe (ou foi apagada)."""


class ContaAmbiguaError(ValueError):
    """Mais de uma conta provou o mesmo e-mail: não dá para saber qual vincular."""


class JaEMembroError(ValueError):
    """A conta já é de uma organização: desvincule antes de vincular a outra."""


@dataclass(frozen=True)
class Membro:
    usuario_id: uuid.UUID
    organizacao_id: uuid.UUID
    vinculado_em: datetime


def _com_fuso(momento: datetime) -> datetime:
    # o SQLite devolve sem fuso o que foi gravado em UTC
    return momento if momento.tzinfo else momento.replace(tzinfo=UTC)


def _membro(linha: sa.Row) -> Membro:
    return Membro(
        usuario_id=linha.usuario_id,
        organizacao_id=linha.organizacao_id,
        vinculado_em=_com_fuso(linha.vinculado_em),
    )


def _conta_existe(conexao: sa.Connection, usuario_id: uuid.UUID) -> bool:
    return conexao.execute(
        sa.select(
            sa.exists().where(
                usuarios.c.id == usuario_id, usuarios.c.excluido_em.is_(None)
            )
        )
    ).scalar_one()


def conta_do_email_confirmado(conexao: sa.Connection, email: str) -> uuid.UUID:
    """A única conta ativa que **provou** este e-mail num login (`identidades.email_confirmado`).

    Não usa `usuarios.email`: ele não é único nem provado, então quem se cadastrasse com o e-mail de
    um analista sem confirmá-lo seria vinculado no lugar dele (achado P0 da revisão cruzada do PR 1).
    Zero contas ou mais de uma: recusa, sem escolher.
    """
    contas = (
        conexao.execute(
            sa.select(usuarios.c.id)
            .join(identidades, identidades.c.usuario_id == usuarios.c.id)
            .where(
                identidades.c.email == (email or "").strip().lower(),
                identidades.c.email_confirmado.is_(True),
                usuarios.c.excluido_em.is_(None),
            )
            .distinct()
        )
        .scalars()
        .all()
    )
    if not contas:
        raise ContaInexistenteError(
            "Nenhuma conta com este e-mail confirmado: a pessoa precisa entrar no app antes."
        )
    if len(contas) > 1:
        raise ContaAmbiguaError("Mais de uma conta com este e-mail confirmado.")
    return contas[0]


def _vinculo(conexao: sa.Connection, usuario_id: uuid.UUID) -> sa.Row | None:
    tabela = membros_da_organizacao
    return conexao.execute(
        sa.select(tabela).where(tabela.c.usuario_id == usuario_id)
    ).first()


def vincular_membro(
    conexao: sa.Connection,
    *,
    organizacao_id: uuid.UUID,
    usuario_id: uuid.UUID,
    ator_id: uuid.UUID,
    agora: datetime | None = None,
) -> Membro:
    """A conta passa a ser da organização. Sozinho não mostra nada: falta o contrato permitir."""
    if cb.buscar_organizacao(conexao, organizacao_id) is None:
        raise cb.OrganizacaoInvalidaError("Organização inexistente.")
    if not _conta_existe(conexao, usuario_id):
        raise ContaInexistenteError("Conta inexistente.")
    if _vinculo(conexao, usuario_id) is not None:
        raise JaEMembroError("A conta já é de uma organização: desvincule antes.")
    conexao.execute(
        sa.insert(membros_da_organizacao).values(
            usuario_id=usuario_id,
            organizacao_id=organizacao_id,
            vinculado_em=agora or datetime.now(UTC),
            vinculado_por=ator_id,
        )
    )
    auditoria.registrar(
        conexao,
        ator_id,
        auditoria.ACAO_MEMBRO_VINCULADO,
        alvo_id=usuario_id,
        detalhes={"organizacao_id": str(organizacao_id)},
    )
    linha = _vinculo(conexao, usuario_id)
    assert linha is not None  # acabou de ser gravada nesta transação
    return _membro(linha)


def desvincular_membro(
    conexao: sa.Connection,
    *,
    organizacao_id: uuid.UUID,
    usuario_id: uuid.UUID,
    ator_id: uuid.UUID,
) -> bool:
    """A conta deixa de ser da organização. False se não era membro desta organização."""
    tabela = membros_da_organizacao
    mudou = conexao.execute(
        sa.delete(tabela).where(
            tabela.c.usuario_id == usuario_id,
            tabela.c.organizacao_id == organizacao_id,
        )
    ).rowcount
    if mudou:
        auditoria.registrar(
            conexao,
            ator_id,
            auditoria.ACAO_MEMBRO_DESVINCULADO,
            alvo_id=usuario_id,
            detalhes={"organizacao_id": str(organizacao_id)},
        )
    return bool(mudou)


def listar_membros(conexao: sa.Connection, organizacao_id: uuid.UUID) -> list[Membro]:
    """Os membros de uma organização, do mais antigo ao mais novo (só ids e a data)."""
    tabela = membros_da_organizacao
    linhas = conexao.execute(
        sa.select(tabela)
        .where(tabela.c.organizacao_id == organizacao_id)
        .order_by(tabela.c.vinculado_em, tabela.c.usuario_id)
    )
    return [_membro(linha) for linha in linhas]


def _organizacao_ativa_da_conta(
    conexao: sa.Connection, usuario_id: uuid.UUID
) -> uuid.UUID | None:
    tabela = membros_da_organizacao
    return conexao.execute(
        sa.select(tabela.c.organizacao_id)
        .join(organizacoes, organizacoes.c.id == tabela.c.organizacao_id)
        .join(usuarios, usuarios.c.id == tabela.c.usuario_id)
        .where(
            tabela.c.usuario_id == usuario_id,
            organizacoes.c.suspensa_em.is_(None),
            usuarios.c.excluido_em.is_(None),
            usuarios.c.bloqueada_em.is_(None),
        )
    ).scalar_one_or_none()


def organizacao_da_conta(
    conexao: sa.Connection, usuario_id: uuid.UUID
) -> uuid.UUID | None:
    """A organização ativa da conta (não suspensa, conta nem apagada nem bloqueada), ou None.

    É por ela que o chat do app (linha 903) usa o contrato da organização: o chat nunca vê pessoa,
    mesmo quando a organização tem `pessoa_na_tela` (essa permissão é só da tela).
    """
    return _organizacao_ativa_da_conta(conexao, usuario_id)


def organizacao_que_ve_pessoa(
    conexao: sa.Connection, usuario_id: uuid.UUID, dia: date
) -> uuid.UUID | None:
    """A organização pela qual a conta vê pessoa física na tela no dia; None se não vê.

    Devolve o id para a rota registrar na auditoria por qual organização a pessoa foi vista.
    """
    organizacao_id = _organizacao_ativa_da_conta(conexao, usuario_id)
    if organizacao_id is None:
        return None
    permite = cb.contrato_permite(
        conexao,
        organizacao_id,
        conjunto=CONJUNTO_DE_PESSOA_NA_TELA,
        finalidade=FINALIDADE_DA_TELA,
        dia=dia,
    )
    return organizacao_id if permite else None


def pode_ver_pessoa(conexao: sa.Connection, usuario_id: uuid.UUID, dia: date) -> bool:
    """A conta pode ver, na tela com login, pessoa física do cadastro da Receita neste dia?"""
    return organizacao_que_ve_pessoa(conexao, usuario_id, dia) is not None


def e_do_piloto(conexao: sa.Connection, usuario_id: uuid.UUID, dia: date) -> bool:
    """A conta é membro de uma organização com a marca de piloto vigente no dia, para a tela (D11)?

    A mesma marca que libera o piloto para a chave da organização na API externa
    (`chaves_da_api.e_organizacao_do_piloto`), agora para a conta com login que é membro dela. Organização
    suspensa, conta bloqueada ou excluída e marca fora da vigência não contam.
    """
    organizacao_id = _organizacao_ativa_da_conta(conexao, usuario_id)
    if organizacao_id is None:
        return False
    return cb.e_organizacao_do_piloto(
        conexao, organizacao_id, finalidade=FINALIDADE_DA_TELA, dia=dia
    )


def dados_para_exportar(
    conexao: sa.Connection, *, usuario_id: uuid.UUID
) -> dict[str, str] | None:
    """A organização de que a pessoa é membro (LGPD: exportar meus dados); None se nenhuma."""
    tabela = membros_da_organizacao
    linha = conexao.execute(
        sa.select(organizacoes.c.nome, tabela.c.vinculado_em)
        .join(organizacoes, organizacoes.c.id == tabela.c.organizacao_id)
        .where(tabela.c.usuario_id == usuario_id)
    ).first()
    if linha is None:
        return None
    return {
        "nome": linha.nome,
        "membro_desde": _com_fuso(linha.vinculado_em).isoformat(),
    }
