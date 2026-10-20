"""Código de entrada por e-mail: a pessoa recebe 6 dígitos e entra sem senha (plano do login, PR 2).

Regras: o código vale 10 minutos, é de uso único e aceita 5 tentativas; pedir um novo invalida o
anterior; no máximo 3 pedidos por e-mail a cada 15 minutos (o limite por IP fica na API). O banco
guarda só o hash do e-mail e o do código (`codigos_de_entrada` não tem chave para a conta: no primeiro
acesso ela ainda não existe). O hash do código leva o do e-mail junto, então o mesmo código em dois
e-mails dá hashes diferentes.

O expurgo (`expurgar`) apaga o que venceu há tempo: sessões de login e códigos não têm o que fazer no
banco depois disso, e os códigos nem sobem na exclusão em cascata da conta (LGPD, art. 15 e 16).
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from src.banco.modelo import codigos_de_entrada, sessoes_de_login
from src.banco.usuarios import TAMANHO_MAXIMO_DO_EMAIL
from src.envio_newsletter import Email

DIGITOS = 6
VALIDADE = timedelta(minutes=10)
TENTATIVAS = 5
PEDIDOS_POR_EMAIL = 3
JANELA_DOS_PEDIDOS = timedelta(minutes=15)
# o expurgo guarda a sessão encerrada ou vencida por 90 dias (para a pessoa e o suporte olharem um
# acesso suspeito) e o código vencido por 1 dia (para ver quem tentou)
GUARDA_DA_SESSAO = timedelta(days=90)
GUARDA_DO_CODIGO = timedelta(days=1)


def _agora() -> datetime:
    return datetime.now(UTC)


def _hash(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()


def _hash_do_email(email: str) -> str:
    return _hash(email.strip().lower())


def _hash_do_codigo(email: str, codigo: str) -> str:
    return _hash(f"{_hash_do_email(email)}:{codigo.strip()}")


def email_valido(email: str) -> bool:
    email = (email or "").strip()
    local, _, dominio = email.rpartition("@")
    return (
        bool(local)
        and "." in dominio
        and len(email) <= TAMANHO_MAXIMO_DO_EMAIL
        and not any(c.isspace() for c in email)
    )


def pedir_codigo(
    conexao: sa.Connection, email: str, agora: datetime | None = None
) -> str | None:
    """Grava um código novo para o e-mail e o devolve para ser enviado; None se não deve enviar.

    Não envia (None) para e-mail inválido e quando o e-mail já pediu `PEDIDOS_POR_EMAIL` códigos na
    janela. A tela responde igual nos dois casos: não revela nada. O código anterior só deixa de
    valer quando um novo é de fato gerado."""
    if not email_valido(email):
        return None
    agora = agora or _agora()
    chave = _hash_do_email(email)
    pedidos = conexao.execute(
        sa.select(sa.func.count())
        .select_from(codigos_de_entrada)
        .where(
            codigos_de_entrada.c.hash_do_email == chave,
            codigos_de_entrada.c.criado_em > agora - JANELA_DOS_PEDIDOS,
        )
    ).scalar_one()
    if pedidos >= PEDIDOS_POR_EMAIL:
        return None
    conexao.execute(
        sa.update(codigos_de_entrada)
        .where(
            codigos_de_entrada.c.hash_do_email == chave,
            codigos_de_entrada.c.usado_em.is_(None),
        )
        .values(usado_em=agora)
    )
    codigo = f"{secrets.randbelow(10**DIGITOS):0{DIGITOS}d}"
    conexao.execute(
        sa.insert(codigos_de_entrada).values(
            id=uuid.uuid4(),
            hash_do_email=chave,
            hash_do_codigo=_hash_do_codigo(email, codigo),
            criado_em=agora,
            expira_em=agora + VALIDADE,
        )
    )
    return codigo


def _com_fuso(momento: datetime) -> datetime:
    # o SQLite devolve as datas sem fuso; o PostgreSQL, com
    return momento if momento.tzinfo else momento.replace(tzinfo=UTC)


def conferir_codigo(
    conexao: sa.Connection, email: str, codigo: str, agora: datetime | None = None
) -> bool:
    """O código certo, vigente e com tentativas sobrando? Se sim, ele é gasto (uso único).

    Toda conferência conta uma tentativa antes de comparar, então um erro não devolve a tentativa."""
    agora = agora or _agora()
    chave = _hash_do_email(email)
    linha = conexao.execute(
        sa.select(codigos_de_entrada)
        .where(
            codigos_de_entrada.c.hash_do_email == chave,
            codigos_de_entrada.c.usado_em.is_(None),
        )
        .order_by(codigos_de_entrada.c.criado_em.desc())
        .limit(1)
    ).first()
    if linha is None or _com_fuso(linha.expira_em) <= agora:
        return False
    contou = conexao.execute(
        sa.update(codigos_de_entrada)
        .where(
            codigos_de_entrada.c.id == linha.id,
            codigos_de_entrada.c.tentativas == linha.tentativas,
            codigos_de_entrada.c.tentativas < TENTATIVAS,
        )
        .values(tentativas=linha.tentativas + 1)
    )
    if contou.rowcount != 1:
        return False
    if not hmac.compare_digest(linha.hash_do_codigo, _hash_do_codigo(email, codigo)):
        return False
    conexao.execute(
        sa.update(codigos_de_entrada)
        .where(codigos_de_entrada.c.id == linha.id)
        .values(usado_em=agora)
    )
    return True


def montar_email(codigo: str) -> Email:
    minutos = int(VALIDADE.total_seconds() // 60)
    assunto = f"{codigo} é o seu código de entrada no TickerLab"
    texto = (
        f"Seu código de entrada no TickerLab: {codigo}\n\n"
        f"Ele vale por {minutos} minutos e só pode ser usado uma vez. "
        "Se não foi você quem pediu, ignore este e-mail: nada acontece com a sua conta."
    )
    html = (
        '<div style="font-family:Arial,sans-serif;max-width:480px">'
        "<p>Seu código de entrada no TickerLab:</p>"
        f'<p style="font-size:32px;letter-spacing:6px;font-weight:bold">{codigo}</p>'
        f"<p>Ele vale por {minutos} minutos e só pode ser usado uma vez. "
        "Se não foi você quem pediu, ignore este e-mail: nada acontece com a sua conta.</p>"
        "</div>"
    )
    return Email(assunto, html, texto)


def expurgar(conexao: sa.Connection, agora: datetime | None = None) -> dict[str, int]:
    """Apaga as sessões encerradas ou vencidas há mais de 90 dias e os códigos vencidos há mais de
    1 dia. Devolve quantas linhas saíram de cada tabela. Roda uma vez por dia."""
    agora = agora or _agora()
    corte_da_sessao = agora - GUARDA_DA_SESSAO
    sessoes = conexao.execute(
        sa.delete(sessoes_de_login).where(
            sa.or_(
                sessoes_de_login.c.encerrada_em < corte_da_sessao,
                sessoes_de_login.c.expira_em < corte_da_sessao,
            )
        )
    )
    codigos = conexao.execute(
        sa.delete(codigos_de_entrada).where(
            codigos_de_entrada.c.expira_em < agora - GUARDA_DO_CODIGO
        )
    )
    return {"sessoes": sessoes.rowcount, "codigos": codigos.rowcount}
