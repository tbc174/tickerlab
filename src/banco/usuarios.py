"""Usuários: criar no primeiro login, atualizar nos seguintes e consultar.

Toda função recebe uma `Connection` aberta pelo chamador (`with motor.begin() as conexao:`), para
várias operações poderem fazer parte da mesma transação.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa

from src.banco.modelo import PAPEIS, PLANOS, usuarios

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Usuario:
    id: uuid.UUID
    google_sub: str
    email: str
    nome: str | None
    foto_url: str | None
    papel: str
    plano: str
    criado_em: datetime
    ultimo_acesso: datetime | None
    termos_versao: str | None = None
    termos_aceitos_em: datetime | None = None

    @property
    def e_admin(self) -> bool:
        return self.papel == "admin"


def _agora() -> datetime:
    return datetime.now(UTC)


def _de_linha(linha: sa.Row) -> Usuario:
    return Usuario(
        id=linha.id,
        google_sub=linha.google_sub,
        email=linha.email,
        nome=linha.nome,
        foto_url=linha.foto_url,
        papel=linha.papel,
        plano=linha.plano,
        criado_em=linha.criado_em,
        ultimo_acesso=linha.ultimo_acesso,
        termos_versao=linha.termos_versao,
        termos_aceitos_em=linha.termos_aceitos_em,
    )


def buscar_por_id(conexao: sa.Connection, usuario_id: uuid.UUID) -> Usuario | None:
    linha = conexao.execute(
        sa.select(usuarios).where(
            usuarios.c.id == usuario_id, usuarios.c.excluido_em.is_(None)
        )
    ).first()
    return _de_linha(linha) if linha else None


def buscar_por_google_sub(conexao: sa.Connection, google_sub: str) -> Usuario | None:
    linha = conexao.execute(
        sa.select(usuarios).where(
            usuarios.c.google_sub == google_sub, usuarios.c.excluido_em.is_(None)
        )
    ).first()
    return _de_linha(linha) if linha else None


def buscar_por_email(conexao: sa.Connection, email: str) -> Usuario | None:
    linha = conexao.execute(
        sa.select(usuarios).where(
            usuarios.c.email == (email or "").strip().lower(),
            usuarios.c.excluido_em.is_(None),
        )
    ).first()
    return _de_linha(linha) if linha else None


def entrar(
    conexao: sa.Connection,
    google_sub: str,
    email: str,
    nome: str | None = None,
    foto_url: str | None = None,
    emails_de_admin: tuple[str, ...] = (),
) -> tuple[Usuario, bool]:
    """Registra um login do Google. Devolve (usuário, é a primeira vez?).

    Na primeira vez cria o usuário; nas seguintes atualiza nome, foto, e-mail e o último
    acesso. Quem tiver o e-mail em `emails_de_admin` vira administrador.
    """
    google_sub = (google_sub or "").strip()
    email = (email or "").strip().lower()
    if not google_sub or len(google_sub) > 64:
        raise ValueError("O identificador do Google é obrigatório (até 64 caracteres).")
    if "@" not in email or len(email) > 320:
        raise ValueError("O e-mail do Google é inválido.")
    admin = email in {e.strip().lower() for e in emails_de_admin}
    agora = _agora()

    existente = buscar_por_google_sub(conexao, google_sub)
    if existente is not None:
        mudancas = {
            "email": email,
            "nome": nome,
            "foto_url": foto_url,
            "ultimo_acesso": agora,
        }
        if admin and not existente.e_admin:
            mudancas["papel"] = "admin"
        conexao.execute(
            sa.update(usuarios).where(usuarios.c.id == existente.id).values(**mudancas)
        )
        return buscar_por_id(conexao, existente.id), False

    novo_id = uuid.uuid4()
    conexao.execute(
        sa.insert(usuarios).values(
            id=novo_id,
            google_sub=google_sub,
            email=email,
            nome=nome,
            foto_url=foto_url,
            papel="admin" if admin else "usuario",
            plano="gratuito",
            criado_em=agora,
            ultimo_acesso=agora,
        )
    )
    log.info("Novo usuário cadastrado (id %s)", novo_id)
    return buscar_por_id(conexao, novo_id), True


def mudar_plano(conexao: sa.Connection, usuario_id: uuid.UUID, plano: str) -> None:
    if plano not in PLANOS:
        raise ValueError(f"Plano desconhecido: {plano}. Use um destes: {PLANOS}.")
    resultado = conexao.execute(
        sa.update(usuarios).where(usuarios.c.id == usuario_id).values(plano=plano)
    )
    if resultado.rowcount == 0:
        raise LookupError("Usuário não encontrado.")


def mudar_papel(conexao: sa.Connection, usuario_id: uuid.UUID, papel: str) -> None:
    if papel not in PAPEIS:
        raise ValueError(f"Papel desconhecido: {papel}. Use um destes: {PAPEIS}.")
    resultado = conexao.execute(
        sa.update(usuarios).where(usuarios.c.id == usuario_id).values(papel=papel)
    )
    if resultado.rowcount == 0:
        raise LookupError("Usuário não encontrado.")


def contar(conexao: sa.Connection) -> int:
    return conexao.execute(
        sa.select(sa.func.count())
        .select_from(usuarios)
        .where(usuarios.c.excluido_em.is_(None))
    ).scalar_one()


def apagar_conta(conexao: sa.Connection, usuario_id: uuid.UUID) -> bool:
    """Apaga o usuário e, em cascata, tudo o que é dele. Devolve se havia o que apagar."""
    resultado = conexao.execute(sa.delete(usuarios).where(usuarios.c.id == usuario_id))
    return resultado.rowcount > 0
