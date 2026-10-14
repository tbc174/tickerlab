"""Inscrições e envios das Novidades e ofertas do TickerLab por e-mail (migração 0037).

O e-mail do login serve só para a conta: propaganda só vai para quem marcou este consentimento
próprio (LGPD, finalidade). Toda função de inscrição recebe o `usuario_id` da sessão e filtra por
ele. A exceção é `sair_pelo_codigo`: o link do e-mail funciona sem login e o código aleatório
(256 bits) é a prova de que o pedido veio de quem recebeu o e-mail.
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa

from src import auditoria
from src.banco.modelo import (
    SITUACOES_DO_ENVIO,
    envios_de_novidades,
    inscricoes_de_novidades,
    usuarios,
)

TAMANHO_MAXIMO_DO_DETALHE = 200
BYTES_DO_CODIGO = 32  # o código para sair tem 43 caracteres (256 bits aleatórios)


@dataclass(frozen=True)
class Inscricao:
    usuario_id: uuid.UUID
    versao_do_consentimento: str
    codigo_para_sair: str
    inscrito_em: datetime


@dataclass(frozen=True)
class Destinatario:
    """Quem recebe: a inscrição e o e-mail da conta."""

    inscricao: Inscricao
    email: str


def _de_linha(linha: sa.Row) -> Inscricao:
    return Inscricao(
        linha.usuario_id,
        linha.versao_do_consentimento,
        linha.codigo_para_sair,
        linha.inscrito_em,
    )


def inscrever(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    versao_do_consentimento: str,
    agora: datetime | None = None,
) -> Inscricao:
    """Inscreve com a versão do texto que a pessoa marcou (ou renova a inscrição).

    Só chame depois do consentimento na tela. Cada inscrição ganha um código novo para sair (o
    link de um e-mail antigo deixa de valer).
    """
    agora = agora or datetime.now(UTC)
    conexao.execute(
        sa.delete(inscricoes_de_novidades).where(
            inscricoes_de_novidades.c.usuario_id == usuario_id
        )
    )
    conexao.execute(
        sa.insert(inscricoes_de_novidades).values(
            usuario_id=usuario_id,
            versao_do_consentimento=versao_do_consentimento,
            codigo_para_sair=secrets.token_urlsafe(BYTES_DO_CODIGO),
            inscrito_em=agora,
        )
    )
    auditoria.registrar(
        conexao,
        usuario_id,
        auditoria.ACAO_NOVIDADES_INSCRITA,
        usuario_id,
        {"versao": versao_do_consentimento},
    )
    inscrita = inscricao(conexao, usuario_id)
    assert inscrita is not None
    return inscrita


def inscricao(conexao: sa.Connection, usuario_id: uuid.UUID) -> Inscricao | None:
    linha = conexao.execute(
        sa.select(inscricoes_de_novidades).where(
            inscricoes_de_novidades.c.usuario_id == usuario_id
        )
    ).first()
    return None if linha is None else _de_linha(linha)


def _cancelar_onde(conexao: sa.Connection, condicao: sa.ColumnElement) -> bool:
    usuario_id = conexao.execute(
        sa.select(inscricoes_de_novidades.c.usuario_id).where(condicao)
    ).scalar()
    if usuario_id is None:
        return False
    conexao.execute(sa.delete(inscricoes_de_novidades).where(condicao))
    auditoria.registrar(
        conexao, usuario_id, auditoria.ACAO_NOVIDADES_CANCELADA, usuario_id
    )
    return True


def cancelar(conexao: sa.Connection, usuario_id: uuid.UUID) -> bool:
    """Cancela pela tela (com login). Devolve False se não havia inscrição."""
    return _cancelar_onde(conexao, inscricoes_de_novidades.c.usuario_id == usuario_id)


def sair_pelo_codigo(conexao: sa.Connection, codigo: str) -> bool:
    """Cancela pelo link do e-mail (sem login). Código errado ou já usado: False."""
    if not codigo:
        return False
    return _cancelar_onde(conexao, inscricoes_de_novidades.c.codigo_para_sair == codigo)


def destinatarios(conexao: sa.Connection) -> list[Destinatario]:
    """As inscrições de contas ativas, com o e-mail (confirmado pelo Google)."""
    consulta = (
        sa.select(inscricoes_de_novidades, usuarios.c.email)
        .join(usuarios, usuarios.c.id == inscricoes_de_novidades.c.usuario_id)
        .where(usuarios.c.excluido_em.is_(None))
        .order_by(inscricoes_de_novidades.c.inscrito_em)
    )
    return [
        Destinatario(_de_linha(linha), linha.email)
        for linha in conexao.execute(consulta)
    ]


def situacao_do_envio(
    conexao: sa.Connection, usuario_id: uuid.UUID, campanha: str
) -> str | None:
    """ "enviado", "retido" ou "falhou" para esta campanha, ou None se ainda não foi tentada."""
    return conexao.execute(
        sa.select(envios_de_novidades.c.situacao).where(
            envios_de_novidades.c.usuario_id == usuario_id,
            envios_de_novidades.c.campanha == campanha,
        )
    ).scalar()


def registrar_envio(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    campanha: str,
    situacao: str,
    detalhe: str = "",
) -> None:
    """Registra o resultado. Uma falha (ou uma retenção) é trocada pela próxima tentativa."""
    if situacao not in SITUACOES_DO_ENVIO:
        raise ValueError(f"Situação desconhecida: {situacao}")
    conexao.execute(
        sa.delete(envios_de_novidades).where(
            envios_de_novidades.c.usuario_id == usuario_id,
            envios_de_novidades.c.campanha == campanha,
        )
    )
    conexao.execute(
        sa.insert(envios_de_novidades).values(
            usuario_id=usuario_id,
            campanha=campanha,
            situacao=situacao,
            detalhe=detalhe[:TAMANHO_MAXIMO_DO_DETALHE],
            registrado_em=datetime.now(UTC),
        )
    )
