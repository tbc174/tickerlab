"""Painel de administração: o que só quem tem o papel de administrador pode ver e fazer.

Toda função confere, **no banco**, se quem pede é administrador (não confia no que a tela diz).
Mudanças ficam registradas na auditoria.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from src import auditoria as registro_de_auditoria
from src.autenticacao import VARIAVEL_DOS_ADMINS
from src.autenticacao import emails_de_admin as admins_do_servidor
from src.banco import sessoes
from src.banco.modelo import (
    MOTIVOS_DO_BLOQUEIO,
    PAPEIS,
    PLANOS,
    assinaturas,
    eventos_stripe,
    identidades,
    simulacoes,
    usuarios,
)
from src.banco.usuarios import buscar_por_email


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
    bloqueada_em: datetime | None = None
    motivo_do_bloqueio: str | None = None


def exigir_admin(conexao: sa.Connection, ator_id: uuid.UUID | None) -> None:
    """Levanta `PermissaoNegadaError` se o ator não existir, não for administrador ou estiver
    bloqueado (o admin bloqueado no incidente deixa de administrar na hora)."""
    linha = (
        conexao.execute(
            sa.select(usuarios.c.papel, usuarios.c.bloqueada_em).where(
                usuarios.c.id == ator_id
            )
        ).first()
        if ator_id
        else None
    )
    if linha is None or linha.papel != "admin" or linha.bloqueada_em is not None:
        raise PermissaoNegadaError("Só administradores podem fazer isso.")


def admin_do_servidor(pedido: str | None) -> str:
    """O e-mail de quem pede num script de administração: precisa estar em `TICKERLAB_ADMINS`.

    Sem `pedido`, vale o único e-mail da lista (com mais de um, é preciso dizer qual)."""
    lista = admins_do_servidor()
    if not lista:
        raise PermissaoNegadaError(f"{VARIAVEL_DOS_ADMINS} está vazia neste servidor.")
    if pedido is None:
        if len(lista) > 1:
            raise PermissaoNegadaError(
                f"{VARIAVEL_DOS_ADMINS} tem mais de um e-mail: diga qual com --admin."
            )
        return lista[0]
    email = pedido.strip().lower()
    if email not in lista:
        raise PermissaoNegadaError(f"Este e-mail não está em {VARIAVEL_DOS_ADMINS}.")
    return email


def ator_do_servidor(conexao: sa.Connection, email: str) -> uuid.UUID:
    """O id do administrador do script, conferido no banco (a lista sozinha não basta)."""
    usuario = buscar_por_email(conexao, email)
    if usuario is None:
        raise PermissaoNegadaError(
            "Nenhum administrador com este e-mail no banco: entre no app pelo Google antes."
        )
    exigir_admin(conexao, usuario.id)
    return usuario.id


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
            bloqueada_em=l.bloqueada_em,
            motivo_do_bloqueio=l.motivo_do_bloqueio,
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
    conexao: sa.Connection,
    ator_id: uuid.UUID,
    alvo_id: uuid.UUID,
    papel: str,
    emails_de_admin: tuple[str, ...] | None = None,
) -> None:
    """Muda o papel de alguém. `emails_de_admin` é a lista do servidor (None: lê a variável).

    Quem está na lista `TICKERLAB_ADMINS` não é rebaixado pelo painel: o login o promoveria de
    novo (achado 4a do Codex, ADR 0091). Para tirar o acesso, tira-se o e-mail da lista antes.
    """
    exigir_admin(conexao, ator_id)
    if papel not in PAPEIS:
        raise OperacaoInvalidaError(f"Papel desconhecido: {papel}.")
    alvo = conexao.execute(
        sa.select(usuarios.c.papel, usuarios.c.email).where(usuarios.c.id == alvo_id)
    ).first()
    if alvo is None:
        raise OperacaoInvalidaError("Usuário não encontrado.")
    antes = alvo.papel
    lista = admins_do_servidor() if emails_de_admin is None else emails_de_admin
    if papel != "admin" and alvo.email.lower() in {e.lower() for e in lista}:
        raise OperacaoInvalidaError(
            f"Este e-mail está em {VARIAVEL_DOS_ADMINS} e voltaria a ser administrador no "
            "próximo login. Tire-o da lista no servidor antes de rebaixar."
        )
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


def bloquear_conta(
    conexao: sa.Connection,
    ator_id: uuid.UUID,
    alvo_id: uuid.UUID,
    motivo: str,
    agora: datetime | None = None,
    pelo_servidor: bool = False,
) -> int:
    """Bloqueia uma conta no incidente: encerra as sessões dela na hora e para o login. Devolve
    quantas sessões encerrou.

    Não apaga nada (dados, links, assinatura). Ninguém bloqueia a si mesmo: assim quem bloqueia é
    sempre um administrador que continua desbloqueado, e o serviço nunca fica sem nenhum.

    Conta em `TICKERLAB_ADMINS` só se bloqueia pelo script do servidor (`pelo_servidor`): pelo
    painel, uma sessão de admin roubada trancaria do lado de fora o dono da lista, que não
    entraria nem desbloquearia a si mesmo.
    """
    exigir_admin(conexao, ator_id)
    if motivo not in MOTIVOS_DO_BLOQUEIO:
        raise OperacaoInvalidaError(f"Motivo desconhecido: {motivo}.")
    if alvo_id == ator_id:
        raise OperacaoInvalidaError("Você não pode bloquear a sua própria conta.")
    if _bloqueio_atual(conexao, alvo_id) is not None:
        raise OperacaoInvalidaError("Esta conta já está bloqueada.")
    if not pelo_servidor and _esta_na_lista_do_servidor(conexao, alvo_id):
        raise OperacaoInvalidaError(
            "Esta conta está na lista de administradores do servidor: bloqueie pelo script do "
            "servidor (scripts/contas_do_app.py)."
        )
    agora = agora or datetime.now(UTC)
    conexao.execute(
        sa.update(usuarios)
        .where(usuarios.c.id == alvo_id)
        .values(bloqueada_em=agora, motivo_do_bloqueio=motivo)
    )
    encerradas = sessoes.encerrar_todas(conexao, alvo_id, agora)
    registro_de_auditoria.registrar(
        conexao,
        ator_id,
        registro_de_auditoria.ACAO_CONTA_BLOQUEADA,
        alvo_id,
        {"motivo": motivo, "sessoes_encerradas": encerradas},
    )
    return encerradas


def desbloquear_conta(
    conexao: sa.Connection, ator_id: uuid.UUID, alvo_id: uuid.UUID
) -> None:
    """Tira o bloqueio: o login volta. As sessões encerradas no bloqueio não voltam.

    Encerra também as que sobraram abertas: com o login recusado, uma sessão aberta durante o
    bloqueio só nasce de um login de antes dele, numa corrida, e não pode valer depois (achado
    P0 da revisão cruzada do Codex no #659). A pessoa entra de novo.
    """
    exigir_admin(conexao, ator_id)
    motivo = _bloqueio_atual(conexao, alvo_id)
    if motivo is None:
        raise OperacaoInvalidaError("Esta conta não está bloqueada.")
    agora = datetime.now(UTC)
    encerradas = sessoes.encerrar_todas(conexao, alvo_id, agora)
    conexao.execute(
        sa.update(usuarios)
        .where(usuarios.c.id == alvo_id)
        .values(bloqueada_em=None, motivo_do_bloqueio=None)
    )
    registro_de_auditoria.registrar(
        conexao,
        ator_id,
        registro_de_auditoria.ACAO_CONTA_DESBLOQUEADA,
        alvo_id,
        {"motivo": motivo, "sessoes_encerradas": encerradas},
    )


def _bloqueio_atual(conexao: sa.Connection, alvo_id: uuid.UUID) -> str | None:
    """O motivo do bloqueio da conta (None: não está bloqueada). Conta que não existe é erro.

    O banco garante que o motivo e a data andam juntos (regra `ck_usuarios_bloqueio`)."""
    linha = conexao.execute(
        sa.select(usuarios.c.motivo_do_bloqueio).where(
            usuarios.c.id == alvo_id, usuarios.c.excluido_em.is_(None)
        )
    ).first()
    if linha is None:
        raise OperacaoInvalidaError("Usuário não encontrado.")
    return linha.motivo_do_bloqueio


def _esta_na_lista_do_servidor(conexao: sa.Connection, alvo_id: uuid.UUID) -> bool:
    """Se um e-mail da conta está em `TICKERLAB_ADMINS` (sem diferença de maiúsculas): o de
    contato ou o confirmado de qualquer forma de entrar. O de contato segue a última forma
    usada, e a do Google com o e-mail da lista continua na conta (achado P1 da revisão cruzada
    do Codex no #659)."""
    contato = sa.select(usuarios.c.email).where(usuarios.c.id == alvo_id)
    confirmados = sa.select(identidades.c.email).where(
        identidades.c.usuario_id == alvo_id, identidades.c.email_confirmado.is_(True)
    )
    emails = conexao.execute(sa.union(contato, confirmados)).scalars()
    lista = set(admins_do_servidor())
    return any(email.strip().lower() in lista for email in emails)


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
