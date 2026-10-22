"""Registro do que aconteceu de importante: ações de administrador, aceite dos termos, contas apagadas.

Só guarda ids e dados técnicos, nunca e-mail, nome ou foto. Assim o registro pode continuar
existindo depois que a conta da pessoa é apagada, sem manter dado pessoal.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa

from src.banco.modelo import auditoria

ACAO_PLANO_ALTERADO = "plano_alterado"
ACAO_PAPEL_ALTERADO = "papel_alterado"
ACAO_TERMOS_ACEITOS = "termos_aceitos"
ACAO_CONTA_APAGADA = "conta_apagada"
ACAO_DADOS_EXPORTADOS = "dados_exportados"
ACAO_CARTEIRA_CONSENTIDA = "carteira_consentida"  # Research, etapa 5 (decisão 0020)
ACAO_CARTEIRA_REVOGADA = "carteira_revogada"
ACAO_NEWSLETTER_INSCRITA = "newsletter_inscrita"  # Research, etapa 5c (decisão 0020)
ACAO_NEWSLETTER_CANCELADA = "newsletter_cancelada"
ACAO_NOVIDADES_INSCRITA = "novidades_inscrita"  # Novidades e ofertas por e-mail (0037)
ACAO_NOVIDADES_CANCELADA = "novidades_cancelada"
# Sala de dados (B-20, D15): detalhes só com ids, tamanho, tipo e código do motivo; nunca o nome do
# arquivo nem o SHA-256 (o registro fica depois da exclusão, e o hash confirmaria quem tinha um
# documento conhecido). Recusado e baixados entram com o upload (PR 2 e 3); expirada, com o expurgo.
ACAO_OPERACAO_CRIADA = "operacao_criada"
ACAO_DOCUMENTO_ENVIADO = "documento_enviado"
ACAO_DOCUMENTO_RECUSADO = "documento_recusado"
ACAO_DOCUMENTO_BAIXADO = "documento_baixado"
ACAO_DOCUMENTO_APAGADO = "documento_apagado"
ACAO_OPERACAO_APAGADA = "operacao_apagada"
ACAO_OPERACAO_EXPIRADA = "operacao_expirada"
ACAO_OPERACAO_ENCERRADA = (
    "operacao_encerrada"  # só o novo prazo (data), sem nome (RIPD R-S4)
)
ACAO_OPERACAO_PRORROGADA = "operacao_prorrogada"
ACAO_SALA_BAIXADA = "sala_baixada"
# Originação (B-33): só ids e códigos de fase; nunca origem, próximo passo nem texto do contato.
ACAO_NEGOCIO_ABERTO = "negocio_aberto"
ACAO_NEGOCIO_FASE_MUDADA = "negocio_fase_mudada"
ACAO_NEGOCIO_ATUALIZADO = "negocio_atualizado"
ACAO_CONTATO_REGISTRADO = "contato_registrado"
ACAO_CONTATO_APAGADO = "contato_apagado"
# Garantias (B-17): só ids e o código do tipo; nunca rótulo, titular nem valor.
ACAO_EXPOSICAO_REGISTRADA = "exposicao_registrada"
ACAO_EXPOSICAO_APAGADA = "exposicao_apagada"
ACAO_GARANTIA_REGISTRADA = "garantia_registrada"
ACAO_GARANTIA_APAGADA = "garantia_apagada"
# API externa (N7): só ids, prefixo da chave, plano, finalidade, conjunto e código do motivo; nunca a
# chave, o hash dela nem o nome da organização.
ACAO_ORGANIZACAO_CRIADA = "organizacao_criada"
ACAO_ORGANIZACAO_SUSPENSA = "organizacao_suspensa"
ACAO_ORGANIZACAO_REATIVADA = "organizacao_reativada"
ACAO_CHAVE_EMITIDA = "chave_emitida"
ACAO_CHAVE_ROTACIONADA = "chave_rotacionada"
ACAO_CHAVE_REVOGADA = "chave_revogada"
ACAO_DIREITO_CONCEDIDO = "direito_concedido"
ACAO_DIREITO_SUSPENSO = "direito_suspenso"
ACAO_DIREITO_REATIVADO = "direito_reativado"


@dataclass(frozen=True)
class Registro:
    id: uuid.UUID
    ator_id: uuid.UUID | None
    acao: str
    alvo_id: uuid.UUID | None
    detalhes: dict
    criado_em: datetime


def registrar(
    conexao: sa.Connection,
    ator_id: uuid.UUID | None,
    acao: str,
    alvo_id: uuid.UUID | None = None,
    detalhes: dict | None = None,
) -> None:
    conexao.execute(
        sa.insert(auditoria).values(
            id=uuid.uuid4(),
            ator_id=ator_id,
            acao=acao,
            alvo_id=alvo_id,
            detalhes=detalhes or {},
            criado_em=datetime.now(UTC),
        )
    )


def listar_recentes(conexao: sa.Connection, limite: int = 50) -> list[Registro]:
    linhas = conexao.execute(
        sa.select(auditoria).order_by(auditoria.c.criado_em.desc()).limit(limite)
    )
    return [
        Registro(
            id=l.id,
            ator_id=l.ator_id,
            acao=l.acao,
            alvo_id=l.alvo_id,
            detalhes=dict(l.detalhes),
            criado_em=l.criado_em,
        )
        for l in linhas
    ]
