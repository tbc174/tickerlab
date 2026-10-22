"""Código de entrada por e-mail: a pessoa recebe 6 dígitos e entra sem senha (plano do login, PR 2).

Regras: o código vale 10 minutos, é de uso único e aceita 5 tentativas; no máximo 3 pedidos por
e-mail a cada 15 minutos (o limite por IP fica na API). Pedir um novo **não** derruba o anterior que
ainda vale: quem pede é quem digita o e-mail, não quem é dono dele, e um estranho que sabe o e-mail
trancaria a dona (derrubando o código que ela acabou de receber e esgotando os pedidos). Assim, os
códigos que o estranho pede caem na caixa da dona e qualquer um deles a deixa entrar; entrar gasta
todos, e cada tentativa conta em todos os vivos (o limite de chutes não cresce). O banco
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
    janela. A tela responde igual nos dois casos: não revela nada. Os códigos anteriores que ainda
    valem continuam valendo (ver o docstring do módulo)."""
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
    """O código bate com um dos vivos do e-mail (vigente, não usado, com tentativas sobrando)? Se sim,
    todos os vivos do e-mail são gastos (uso único).

    Toda conferência conta uma tentativa em cada código vivo antes de comparar, então um erro não
    devolve a tentativa e ter vários códigos vivos não dá mais chutes."""
    agora = agora or _agora()
    chave = _hash_do_email(email)
    contados = [
        linha
        for linha in _codigos_vivos(conexao, chave, agora)
        if _contar_tentativa(conexao, linha)
    ]
    procurado = _hash_do_codigo(email, codigo)
    certo = next(
        (c for c in contados if hmac.compare_digest(c.hash_do_codigo, procurado)), None
    )
    if certo is None or not _gastar(conexao, certo.id, agora):
        return False
    conexao.execute(
        sa.update(codigos_de_entrada)
        .where(
            codigos_de_entrada.c.hash_do_email == chave,
            codigos_de_entrada.c.usado_em.is_(None),
        )
        .values(usado_em=agora)
    )
    return True


def _codigos_vivos(conexao: sa.Connection, chave: str, agora: datetime) -> list[sa.Row]:
    linhas = conexao.execute(
        sa.select(codigos_de_entrada).where(
            codigos_de_entrada.c.hash_do_email == chave,
            codigos_de_entrada.c.usado_em.is_(None),
            codigos_de_entrada.c.tentativas < TENTATIVAS,
        )
    ).all()
    return [linha for linha in linhas if _com_fuso(linha.expira_em) > agora]


def _contar_tentativa(conexao: sa.Connection, linha: sa.Row) -> bool:
    # o `tentativas == lido` faz duas conferências ao mesmo tempo não contarem a mesma tentativa
    contou = conexao.execute(
        sa.update(codigos_de_entrada)
        .where(
            codigos_de_entrada.c.id == linha.id,
            codigos_de_entrada.c.tentativas == linha.tentativas,
            codigos_de_entrada.c.tentativas < TENTATIVAS,
        )
        .values(tentativas=linha.tentativas + 1)
    )
    return contou.rowcount == 1


def _gastar(conexao: sa.Connection, id_do_codigo: uuid.UUID, agora: datetime) -> bool:
    # só uma de duas conferências certas ao mesmo tempo gasta o código (e abre a sessão)
    gastou = conexao.execute(
        sa.update(codigos_de_entrada)
        .where(
            codigos_de_entrada.c.id == id_do_codigo,
            codigos_de_entrada.c.usado_em.is_(None),
        )
        .values(usado_em=agora)
    )
    return gastou.rowcount == 1


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
