"""Painel de administração: o que só quem tem o papel de administrador pode ver e fazer.

Toda função confere, **no banco**, se quem pede é administrador (não confia no que a tela diz).
Mudanças ficam registradas na auditoria.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from src import auditoria as registro_de_auditoria
from src.banco.modelo import (
    PAPEIS,
    PLANOS,
    assinaturas,
    eventos_stripe,
    simulacoes,
    usuarios,
)


class PermissaoNegadaError(PermissionError):
    """Quem pediu não é administrador."""


class OperacaoInvalidaError(ValueError):
    """A ação pedida não pode ser feita (por exemplo, tirar o último administrador)."""


@dataclass(frozen=True)
class LinhaDeUsuario:
    id: uuid.UUID
    email: str
    nome: str | None
    papel: str
    plano: str
    criado_em: datetime
    ultimo_acesso: datetime | None
    status_da_assinatura: str | None
    simulacoes: int


def exigir_admin(conexao: sa.Connection, ator_id: uuid.UUID | None) -> None:
    """Levanta `PermissaoNegadaError` se o ator não existir ou não for administrador."""
    papel = (
        conexao.execute(
            sa.select(usuarios.c.papel).where(usuarios.c.id == ator_id)
        ).scalar()
        if ator_id
        else None
    )
    if papel != "admin":
        raise PermissaoNegadaError("Só administradores podem fazer isso.")


def resumo_geral(conexao: sa.Connection, ator_id: uuid.UUID) -> dict:
    """Números gerais do serviço."""
    exigir_admin(conexao, ator_id)
    por_plano = dict(
        conexao.execute(
            sa.select(usuarios.c.plano, sa.func.count()).group_by(usuarios.c.plano)
        ).all()
    )
    por_status = dict(
        conexao.execute(
            sa.select(assinaturas.c.status, sa.func.count()).group_by(
                assinaturas.c.status
            )
        ).all()
    )
    semana = datetime.now(UTC) - timedelta(days=7)
    return {
        "usuarios": sum(por_plano.values()),
        "gratuito": por_plano.get("gratuito", 0),
        "plus": por_plano.get("plus", 0),
        "pro": por_plano.get("pro", 0),
        "administradores": conexao.execute(
            sa.select(sa.func.count()).where(usuarios.c.papel == "admin")
        ).scalar_one(),
        "novos_na_semana": conexao.execute(
            sa.select(sa.func.count()).where(usuarios.c.criado_em >= semana)
        ).scalar_one(),
        "ativos_na_semana": conexao.execute(
            sa.select(sa.func.count()).where(usuarios.c.ultimo_acesso >= semana)
        ).scalar_one(),
        "simulacoes": conexao.execute(
            sa.select(sa.func.count()).select_from(simulacoes)
        ).scalar_one(),
        "assinaturas_por_status": por_status,
        "eventos_do_stripe": conexao.execute(
            sa.select(sa.func.count()).select_from(eventos_stripe)
        ).scalar_one(),
    }


def _escapar_like(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def listar_usuarios(
    conexao: sa.Connection,
    ator_id: uuid.UUID,
    busca: str = "",
    limite: int = 100,
) -> list[LinhaDeUsuario]:
    """Usuários (mais novos primeiro), com status da assinatura e quantas simulações têm."""
    exigir_admin(conexao, ator_id)
    contagem = (
        sa.select(simulacoes.c.usuario_id, sa.func.count().label("total"))
        .group_by(simulacoes.c.usuario_id)
        .subquery()
    )
    consulta = (
        sa.select(
            usuarios,
            assinaturas.c.status.label("status_da_assinatura"),
            sa.func.coalesce(contagem.c.total, 0).label("total_de_simulacoes"),
        )
        .select_from(
            usuarios.outerjoin(
                assinaturas, assinaturas.c.usuario_id == usuarios.c.id
            ).outerjoin(contagem, contagem.c.usuario_id == usuarios.c.id)
        )
        .order_by(usuarios.c.criado_em.desc())
        .limit(max(1, min(limite, 500)))
    )
    busca = busca.strip().lower()
    if busca:
        padrao = f"%{_escapar_like(busca)}%"
        consulta = consulta.where(
            sa.or_(
                sa.func.lower(usuarios.c.email).like(padrao, escape="\\"),
                sa.func.lower(sa.func.coalesce(usuarios.c.nome, "")).like(
                    padrao, escape="\\"
                ),
            )
        )
    return [
        LinhaDeUsuario(
            id=l.id,
            email=l.email,
            nome=l.nome,
            papel=l.papel,
            plano=l.plano,
            criado_em=l.criado_em,
            ultimo_acesso=l.ultimo_acesso,
            status_da_assinatura=l.status_da_assinatura,
            simulacoes=l.total_de_simulacoes,
        )
        for l in conexao.execute(consulta)
    ]


def alterar_plano(
    conexao: sa.Connection, ator_id: uuid.UUID, alvo_id: uuid.UUID, plano: str
) -> None:
    exigir_admin(conexao, ator_id)
    if plano not in PLANOS:
        raise OperacaoInvalidaError(f"Plano desconhecido: {plano}.")
    antes = conexao.execute(
        sa.select(usuarios.c.plano).where(usuarios.c.id == alvo_id)
    ).scalar()
    if antes is None:
        raise OperacaoInvalidaError("Usuário não encontrado.")
    conexao.execute(
        sa.update(usuarios).where(usuarios.c.id == alvo_id).values(plano=plano)
    )
    registro_de_auditoria.registrar(
        conexao,
        ator_id,
        registro_de_auditoria.ACAO_PLANO_ALTERADO,
        alvo_id,
        {"de": antes, "para": plano},
    )


def alterar_papel(
    conexao: sa.Connection, ator_id: uuid.UUID, alvo_id: uuid.UUID, papel: str
) -> None:
    exigir_admin(conexao, ator_id)
    if papel not in PAPEIS:
        raise OperacaoInvalidaError(f"Papel desconhecido: {papel}.")
    antes = conexao.execute(
        sa.select(usuarios.c.papel).where(usuarios.c.id == alvo_id)
    ).scalar()
    if antes is None:
        raise OperacaoInvalidaError("Usuário não encontrado.")
    if alvo_id == ator_id and papel != "admin":
        raise OperacaoInvalidaError(
            "Você não pode tirar o seu próprio acesso de administrador."
        )
    if antes == "admin" and papel != "admin":
        restantes = conexao.execute(
            sa.select(sa.func.count()).where(
                usuarios.c.papel == "admin", usuarios.c.id != alvo_id
            )
        ).scalar_one()
        if restantes == 0:
            raise OperacaoInvalidaError(
                "O serviço precisa de pelo menos um administrador."
            )
    conexao.execute(
        sa.update(usuarios).where(usuarios.c.id == alvo_id).values(papel=papel)
    )
    registro_de_auditoria.registrar(
        conexao,
        ator_id,
        registro_de_auditoria.ACAO_PAPEL_ALTERADO,
        alvo_id,
        {"de": antes, "para": papel},
    )


def eventos_recentes_do_stripe(
    conexao: sa.Connection, ator_id: uuid.UUID, limite: int = 20
) -> list[tuple[str, str, datetime]]:
    """(id, tipo, quando) dos últimos eventos do Stripe processados."""
    exigir_admin(conexao, ator_id)
    linhas = conexao.execute(
        sa.select(
            eventos_stripe.c.id, eventos_stripe.c.tipo, eventos_stripe.c.processado_em
        )
        .order_by(eventos_stripe.c.processado_em.desc())
        .limit(limite)
    )
    return [(l.id, l.tipo, l.processado_em) for l in linhas]


def auditoria_recente(
    conexao: sa.Connection, ator_id: uuid.UUID, limite: int = 50
) -> list[registro_de_auditoria.Registro]:
    exigir_admin(conexao, ator_id)
    return registro_de_auditoria.listar_recentes(conexao, limite)
