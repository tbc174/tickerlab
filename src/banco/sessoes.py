"""Sessões de login do app novo: abrir, achar a conta pelo token, encerrar.

O token vai só para o cookie da pessoa (`__Host-tl_sessao`); o banco guarda o SHA-256 dele. Quem
ler o banco (um backup, um erro de log) não consegue entrar por ninguém, e não há segredo do
servidor a proteger: o token tem 32 bytes aleatórios, então o hash simples basta (não é senha).

A sessão vale `DURACAO` a contar de quando abriu, sem renovar sozinha: depois de 30 dias a pessoa
entra de novo. Acaba antes quando ela sai, quando todas as sessões da conta são encerradas ou
quando a conta é apagada (chave estrangeira em cascata).
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from src.banco.modelo import PROVEDORES_DE_LOGIN, sessoes_de_login
from src.banco.usuarios import Usuario, buscar_por_id

DURACAO = timedelta(days=30)
BYTES_DO_TOKEN = 32
# o token de verdade tem 43 caracteres; maior que isto é lixo e nem chega ao banco
TAMANHO_MAXIMO_DO_TOKEN = 100
# o último uso é para a pessoa ver as sessões dela, não um relógio: gravar a cada pedido seria
# uma escrita no banco por clique
INTERVALO_DO_ULTIMO_USO = timedelta(hours=1)


def _agora() -> datetime:
    return datetime.now(UTC)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _com_fuso(momento: datetime | None) -> datetime | None:
    # o SQLite devolve as datas sem fuso; o PostgreSQL, com
    if momento is None or momento.tzinfo is not None:
        return momento
    return momento.replace(tzinfo=UTC)


def abrir(
    conexao: sa.Connection,
    usuario_id: uuid.UUID,
    provedor: str,
    agora: datetime | None = None,
) -> str:
    """Abre uma sessão para a conta e devolve o token (que só o cookie vai guardar)."""
    if provedor not in PROVEDORES_DE_LOGIN:
        raise ValueError(f"Forma de entrar desconhecida: {provedor}.")
    agora = agora or _agora()
    token = secrets.token_urlsafe(BYTES_DO_TOKEN)
    conexao.execute(
        sa.insert(sessoes_de_login).values(
            id=uuid.uuid4(),
            usuario_id=usuario_id,
            hash_do_token=_hash(token),
            provedor=provedor,
            criada_em=agora,
            expira_em=agora + DURACAO,
            ultimo_uso=agora,
        )
    )
    return token


def conta_da_sessao(
    conexao: sa.Connection, token: str, agora: datetime | None = None
) -> Usuario | None:
    """A conta ativa da sessão aberta e não vencida desse token; None em qualquer outro caso."""
    token = (token or "").strip()
    if not token or len(token) > TAMANHO_MAXIMO_DO_TOKEN:
        return None
    agora = agora or _agora()
    linha = conexao.execute(
        sa.select(
            sessoes_de_login.c.id,
            sessoes_de_login.c.usuario_id,
            sessoes_de_login.c.expira_em,
            sessoes_de_login.c.ultimo_uso,
        ).where(
            sessoes_de_login.c.hash_do_token == _hash(token),
            sessoes_de_login.c.encerrada_em.is_(None),
        )
    ).first()
    if linha is None:
        return None
    expira_em = _com_fuso(linha.expira_em)
    if expira_em is None or expira_em <= agora:
        return None
    ultimo_uso = _com_fuso(linha.ultimo_uso)
    if ultimo_uso is None or agora - ultimo_uso >= INTERVALO_DO_ULTIMO_USO:
        conexao.execute(
            sa.update(sessoes_de_login)
            .where(sessoes_de_login.c.id == linha.id)
            .values(ultimo_uso=agora)
        )
    return buscar_por_id(conexao, linha.usuario_id)


def encerrar(conexao: sa.Connection, token: str, agora: datetime | None = None) -> bool:
    """Encerra a sessão desse token (o "Sair"). Devolve se havia uma sessão aberta."""
    token = (token or "").strip()
    if not token or len(token) > TAMANHO_MAXIMO_DO_TOKEN:
        return False
    resultado = conexao.execute(
        sa.update(sessoes_de_login)
        .where(
            sessoes_de_login.c.hash_do_token == _hash(token),
            sessoes_de_login.c.encerrada_em.is_(None),
        )
        .values(encerrada_em=agora or _agora())
    )
    return resultado.rowcount > 0


def encerrar_todas(
    conexao: sa.Connection, usuario_id: uuid.UUID, agora: datetime | None = None
) -> int:
    """Encerra todas as sessões abertas da conta (em todos os aparelhos). Devolve quantas."""
    resultado = conexao.execute(
        sa.update(sessoes_de_login)
        .where(
            sessoes_de_login.c.usuario_id == usuario_id,
            sessoes_de_login.c.encerrada_em.is_(None),
        )
        .values(encerrada_em=agora or _agora())
    )
    return resultado.rowcount
