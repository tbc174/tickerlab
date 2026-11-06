"""Usuários: criar no primeiro login, atualizar nos seguintes e consultar.

Uma conta pode ter várias formas de entrar (identidades: Google, Microsoft, e-mail com código). A
forma de entrar nova só se junta a uma conta existente pelo e-mail quando ele foi confirmado nos dois
lados: o provedor provou o e-mail agora, e a conta já tinha uma identidade com esse e-mail provado.
Sem isso, quem declarasse o e-mail de outra pessoa entraria na conta dela (ou ficaria com ela).

Toda função recebe uma `Connection` aberta pelo chamador (`with motor.begin() as conexao:`), para
várias operações poderem fazer parte da mesma transação.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa

from src.banco.modelo import (
    PAPEIS,
    PLANOS,
    PROVEDORES_DE_LOGIN,
    identidades,
    usuarios,
)

log = logging.getLogger(__name__)

TAMANHO_DO_GOOGLE_SUB = 64  # a coluna usuarios.google_sub
TAMANHO_MAXIMO_DO_SUB = 255
TAMANHO_MAXIMO_DO_EMAIL = 320
# só o Google dá o papel de administrador (TICKERLAB_ADMINS): é o login que já existia e o único em
# que a lista foi pensada
PROVEDOR_DOS_ADMINS = "google"


@dataclass(frozen=True)
class Usuario:
    id: uuid.UUID
    google_sub: str | None  # vazio na conta criada pela Microsoft ou por e-mail
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


@dataclass(frozen=True)
class IdentidadeDoProvedor:
    """O que um provedor de login devolveu, já verificado (assinatura do token, código certo)."""

    provedor: str  # um de PROVEDORES_DE_LOGIN
    sub: str  # o identificador da pessoa nesse provedor (no e-mail com código, o próprio e-mail)
    email: str
    email_confirmado: bool  # o provedor provou que a pessoa é dona do e-mail
    nome: str | None = None
    foto_url: str | None = None


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
    email_confirmado: bool = False,
) -> tuple[Usuario, bool]:
    """Registra um login do Google. Devolve (usuário, é a primeira vez?).

    `email_confirmado` é o `email_verified` do Google: sem ele o e-mail não junta contas nem dá o
    papel de administrador. As regras estão em `entrar_por_identidade`.
    """
    google_sub = (google_sub or "").strip()
    if not google_sub or len(google_sub) > TAMANHO_DO_GOOGLE_SUB:
        raise ValueError(
            f"O identificador do Google é obrigatório (até {TAMANHO_DO_GOOGLE_SUB} caracteres)."
        )
    identidade = IdentidadeDoProvedor(
        "google", google_sub, email, email_confirmado, nome, foto_url
    )
    return entrar_por_identidade(conexao, identidade, emails_de_admin)


def entrar_por_identidade(
    conexao: sa.Connection,
    identidade: IdentidadeDoProvedor,
    emails_de_admin: tuple[str, ...] = (),
) -> tuple[Usuario, bool]:
    """Registra um login por qualquer provedor. Devolve (usuário, é a primeira vez?).

    A conta é, nesta ordem: a da própria identidade; a do `google_sub` (conta do Google sem
    identidade gravada); a conta ativa mais antiga com uma identidade de e-mail confirmado igual ao
    deste login, se ele também veio confirmado; ou uma conta nova. Nas seguintes, atualiza o último
    acesso (e nome, foto e e-mail, quando vieram). Vira administrador quem entra pelo Google com o
    e-mail confirmado e listado em `emails_de_admin`.
    """
    identidade = _validada(identidade)
    admin = (
        identidade.provedor == PROVEDOR_DOS_ADMINS
        and identidade.email_confirmado
        and identidade.email in {e.strip().lower() for e in emails_de_admin}
    )
    conta = _conta_da_identidade(conexao, identidade)
    if conta is not None:
        _atualizar_identidade(conexao, identidade)
    else:
        conta = _conta_para_juntar(conexao, identidade)
        if conta is None:
            return _criar_conta(conexao, identidade, admin), True
        _gravar_identidade(conexao, conta.id, identidade)
    _atualizar_conta(conexao, conta, identidade, admin)
    atualizada = buscar_por_id(conexao, conta.id)
    assert atualizada is not None  # ativa: achada nesta mesma transação
    return atualizada, False


def _validada(identidade: IdentidadeDoProvedor) -> IdentidadeDoProvedor:
    sub = (identidade.sub or "").strip()
    email = (identidade.email or "").strip().lower()
    if identidade.provedor not in PROVEDORES_DE_LOGIN:
        raise ValueError(f"Forma de entrar desconhecida: {identidade.provedor}.")
    if not sub or len(sub) > TAMANHO_MAXIMO_DO_SUB:
        raise ValueError(
            f"O identificador do login é obrigatório (até {TAMANHO_MAXIMO_DO_SUB} caracteres)."
        )
    if "@" not in email or len(email) > TAMANHO_MAXIMO_DO_EMAIL:
        raise ValueError("O e-mail do login é inválido.")
    return IdentidadeDoProvedor(
        identidade.provedor,
        sub,
        email,
        identidade.email_confirmado,
        identidade.nome,
        identidade.foto_url,
    )


def buscar_por_identidade(
    conexao: sa.Connection, provedor: str, sub: str
) -> Usuario | None:
    """A conta ativa dessa forma de entrar (a do Google também pelo `google_sub`, das contas antigas)."""
    usuario_id = _dono_da_identidade(conexao, provedor, sub)
    if usuario_id is not None:
        return buscar_por_id(conexao, usuario_id)
    return buscar_por_google_sub(conexao, sub) if provedor == "google" else None


def _dono_da_identidade(
    conexao: sa.Connection, provedor: str, sub: str
) -> uuid.UUID | None:
    return conexao.execute(
        sa.select(identidades.c.usuario_id).where(
            identidades.c.provedor == provedor, identidades.c.sub == sub
        )
    ).scalar()


def _conta_da_identidade(
    conexao: sa.Connection, identidade: IdentidadeDoProvedor
) -> Usuario | None:
    usuario_id = _dono_da_identidade(conexao, identidade.provedor, identidade.sub)
    if usuario_id is not None:
        return buscar_por_id(conexao, usuario_id)
    if identidade.provedor == "google":
        conta = buscar_por_google_sub(conexao, identidade.sub)
        if conta is not None:
            _gravar_identidade(conexao, conta.id, identidade)
        return conta
    return None


def _conta_para_juntar(
    conexao: sa.Connection, identidade: IdentidadeDoProvedor
) -> Usuario | None:
    """A conta ativa mais antiga que já provou o mesmo e-mail (só se este login também provou)."""
    if not identidade.email_confirmado:
        return None
    linha = conexao.execute(
        sa.select(usuarios)
        .join(identidades, identidades.c.usuario_id == usuarios.c.id)
        .where(
            identidades.c.email == identidade.email,
            identidades.c.email_confirmado.is_(True),
            usuarios.c.excluido_em.is_(None),
        )
        .order_by(usuarios.c.criado_em, usuarios.c.id)
    ).first()
    return _de_linha(linha) if linha else None


def _gravar_identidade(
    conexao: sa.Connection, usuario_id: uuid.UUID, identidade: IdentidadeDoProvedor
) -> None:
    conexao.execute(
        sa.insert(identidades).values(
            id=uuid.uuid4(),
            usuario_id=usuario_id,
            provedor=identidade.provedor,
            sub=identidade.sub,
            email=identidade.email,
            email_confirmado=identidade.email_confirmado,
            ultimo_uso=_agora(),
        )
    )


def _atualizar_identidade(
    conexao: sa.Connection, identidade: IdentidadeDoProvedor
) -> None:
    conexao.execute(
        sa.update(identidades)
        .where(
            identidades.c.provedor == identidade.provedor,
            identidades.c.sub == identidade.sub,
        )
        .values(
            email=identidade.email,
            email_confirmado=identidade.email_confirmado,
            ultimo_uso=_agora(),
        )
    )


def _atualizar_conta(
    conexao: sa.Connection,
    conta: Usuario,
    identidade: IdentidadeDoProvedor,
    admin: bool,
) -> None:
    mudancas: dict[str, object] = {"ultimo_acesso": _agora()}
    # o e-mail de contato só muda para um e-mail provado; nome e foto, quando o provedor manda
    if identidade.email_confirmado:
        mudancas["email"] = identidade.email
    if identidade.nome:
        mudancas["nome"] = identidade.nome
    if identidade.foto_url:
        mudancas["foto_url"] = identidade.foto_url
    if identidade.provedor == "google" and conta.google_sub is None:
        mudancas["google_sub"] = (
            identidade.sub
        )  # a versão clássica acha a conta por ele
    if admin and not conta.e_admin:
        mudancas["papel"] = "admin"
    conexao.execute(
        sa.update(usuarios).where(usuarios.c.id == conta.id).values(**mudancas)
    )


def _criar_conta(
    conexao: sa.Connection, identidade: IdentidadeDoProvedor, admin: bool
) -> Usuario:
    novo_id = uuid.uuid4()
    agora = _agora()
    conexao.execute(
        sa.insert(usuarios).values(
            id=novo_id,
            google_sub=identidade.sub if identidade.provedor == "google" else None,
            email=identidade.email,
            nome=identidade.nome,
            foto_url=identidade.foto_url,
            papel="admin" if admin else "usuario",
            plano="gratuito",
            criado_em=agora,
            ultimo_acesso=agora,
        )
    )
    _gravar_identidade(conexao, novo_id, identidade)
    log.info("Novo usuário cadastrado (id %s, %s)", novo_id, identidade.provedor)
    conta = buscar_por_id(conexao, novo_id)
    assert conta is not None  # acabou de ser criada, na mesma transação
    return conta


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
