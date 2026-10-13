"""Inscrições e envios da Newsletter por e-mail (Research, etapa 5c; decisão 0020).

Toda função de inscrição recebe o `usuario_id` da sessão e filtra por ele, como em
`dados_do_usuario`. A exceção é `sair_pelo_codigo`: o link do e-mail funciona sem login e o
código aleatório (256 bits) é a prova de que o pedido veio de quem recebeu o e-mail.
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa

from src import auditoria
from src.banco.modelo import (
    CADENCIAS_DO_EMAIL,
    SITUACOES_DO_ENVIO,
    envios_da_newsletter,
    inscricoes_da_newsletter,
    usuarios,
)

TAMANHO_MAXIMO_DO_DETALHE = 200
BYTES_DO_CODIGO = 32  # o código para sair tem 43 caracteres (256 bits aleatórios)


class InscricaoInvalidaError(ValueError):
    """A lista ou a frequência pedida não existe."""


@dataclass(frozen=True)
class Inscricao:
    usuario_id: uuid.UUID
    lista: str
    cadencia: str
    codigo_para_sair: str
    inscrito_em: datetime


@dataclass(frozen=True)
class Destinatario:
    """Quem recebe: a inscrição e o que o envio precisa saber da conta."""

    inscricao: Inscricao
    email: str
    plano: str


def _de_linha(linha: sa.Row) -> Inscricao:
    return Inscricao(
        linha.usuario_id,
        linha.lista,
        linha.cadencia,
        linha.codigo_para_sair,
        linha.inscrito_em,
    )


def inscrever(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    lista: str,
    cadencia: str,
    versao_do_consentimento: str,
    agora: datetime | None = None,
) -> Inscricao:
    """Inscreve (ou troca a lista e a frequência), com a versão do texto que a pessoa marcou.

    Só chame depois do consentimento na tela. Cada inscrição ganha um código novo para sair (o
    link de um e-mail antigo deixa de valer).
    """
    if cadencia not in CADENCIAS_DO_EMAIL:
        raise InscricaoInvalidaError(f"Frequência desconhecida: {cadencia}.")
    if not lista.strip():
        raise InscricaoInvalidaError("Escolha uma lista.")
    agora = agora or datetime.now(UTC)
    conexao.execute(
        sa.delete(inscricoes_da_newsletter).where(
            inscricoes_da_newsletter.c.usuario_id == usuario_id
        )
    )
    conexao.execute(
        sa.insert(inscricoes_da_newsletter).values(
            usuario_id=usuario_id,
            lista=lista.strip(),
            cadencia=cadencia,
            versao_do_consentimento=versao_do_consentimento,
            codigo_para_sair=secrets.token_urlsafe(BYTES_DO_CODIGO),
            inscrito_em=agora,
        )
    )
    auditoria.registrar(
        conexao,
        usuario_id,
        auditoria.ACAO_NEWSLETTER_INSCRITA,
        usuario_id,
        {"versao": versao_do_consentimento, "cadencia": cadencia},
    )
    inscrita = inscricao(conexao, usuario_id)
    assert inscrita is not None
    return inscrita


def inscricao(conexao: sa.Connection, usuario_id: uuid.UUID) -> Inscricao | None:
    linha = conexao.execute(
        sa.select(inscricoes_da_newsletter).where(
            inscricoes_da_newsletter.c.usuario_id == usuario_id
        )
    ).first()
    return None if linha is None else _de_linha(linha)


def _cancelar_onde(conexao: sa.Connection, condicao: sa.ColumnElement) -> bool:
    usuario_id = conexao.execute(
        sa.select(inscricoes_da_newsletter.c.usuario_id).where(condicao)
    ).scalar()
    if usuario_id is None:
        return False
    conexao.execute(sa.delete(inscricoes_da_newsletter).where(condicao))
    auditoria.registrar(
        conexao, usuario_id, auditoria.ACAO_NEWSLETTER_CANCELADA, usuario_id
    )
    return True


def cancelar(conexao: sa.Connection, usuario_id: uuid.UUID) -> bool:
    """Cancela pela tela (com login). Devolve False se não havia inscrição."""
    return _cancelar_onde(conexao, inscricoes_da_newsletter.c.usuario_id == usuario_id)


def sair_pelo_codigo(conexao: sa.Connection, codigo: str) -> bool:
    """Cancela pelo link do e-mail (sem login). Código errado ou já usado: False."""
    if not codigo:
        return False
    return _cancelar_onde(
        conexao, inscricoes_da_newsletter.c.codigo_para_sair == codigo
    )


def destinatarios(conexao: sa.Connection) -> list[Destinatario]:
    """As inscrições de contas ativas, com o e-mail (confirmado pelo Google) e o plano."""
    consulta = (
        sa.select(inscricoes_da_newsletter, usuarios.c.email, usuarios.c.plano)
        .join(usuarios, usuarios.c.id == inscricoes_da_newsletter.c.usuario_id)
        .where(usuarios.c.excluido_em.is_(None))
        .order_by(inscricoes_da_newsletter.c.inscrito_em)
    )
    return [
        Destinatario(_de_linha(linha), linha.email, linha.plano)
        for linha in conexao.execute(consulta)
    ]


def situacao_do_envio(
    conexao: sa.Connection, usuario_id: uuid.UUID, periodo: str
) -> str | None:
    """ "enviado", "retido" ou "falhou" para esta edição, ou None se ainda não foi tentada."""
    return conexao.execute(
        sa.select(envios_da_newsletter.c.situacao).where(
            envios_da_newsletter.c.usuario_id == usuario_id,
            envios_da_newsletter.c.periodo == periodo,
        )
    ).scalar()


def registrar_envio(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    periodo: str,
    situacao: str,
    detalhe: str = "",
) -> None:
    """Registra o resultado. Uma falha é trocada pelo resultado da próxima tentativa."""
    if situacao not in SITUACOES_DO_ENVIO:
        raise ValueError(f"Situação desconhecida: {situacao}")
    conexao.execute(
        sa.delete(envios_da_newsletter).where(
            envios_da_newsletter.c.usuario_id == usuario_id,
            envios_da_newsletter.c.periodo == periodo,
        )
    )
    conexao.execute(
        sa.insert(envios_da_newsletter).values(
            usuario_id=usuario_id,
            periodo=periodo,
            situacao=situacao,
            detalhe=detalhe[:TAMANHO_MAXIMO_DO_DETALHE],
            registrado_em=datetime.now(UTC),
        )
    )
