"""As perguntas ao chat de IA do app (linha 903): a cota de cada conta e o gasto do mês somando todas.

Uma linha por pergunta (`perguntas_do_chat`, 0048), gravada antes de o modelo ser chamado e completada no
fim com os tokens, o custo e a latência. Só ids e números: nem a pergunta nem a resposta. Toda consulta de
conta filtra pelo `usuario_id`; o gasto do mês é o único total de todas as contas (é ele que pausa o chat
no teto). Os dias e os meses são os de Brasília; as horas ficam em UTC no banco.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from src.banco.modelo import perguntas_do_chat
from src.bcb import FUSO

EM_CURSO = "em_curso"
ERRO = "erro"
# Uma pergunta leva minutos. Em curso há mais que isto, o processo morreu no meio (deploy, falta de
# memória) e o fim dela nunca vai gravar: ela fecha como erro na próxima reserva.
MINUTOS_PARA_ABANDONAR = 60
# Número fixo da trava das reservas no PostgreSQL (pg_advisory_xact_lock pede um inteiro de 64 bits);
# diferente da trava das migrações (src/banco/conexao.py).
CHAVE_DA_TRAVA_DAS_RESERVAS = 7_423_903


@dataclass(frozen=True)
class UsoDaPergunta:
    """O que a pergunta gastou no modelo (somando as voltas) e quantas ferramentas chamou."""

    tokens_de_entrada: int = 0
    tokens_de_saida: int = 0
    tokens_lidos_do_cache: int = 0
    tokens_gravados_no_cache: int = 0
    custo_em_microdolares: int = 0
    chamadas_de_ferramenta: int = 0


def _em_utc(momento: datetime) -> datetime:
    if momento.tzinfo is None:
        raise ValueError("A hora precisa ter fuso.")
    return momento.astimezone(UTC)


def inicio_do_dia(momento: datetime) -> datetime:
    """A meia-noite de Brasília do dia de `momento`, em UTC."""
    local = momento.astimezone(FUSO)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


def inicio_do_mes(momento: datetime) -> datetime:
    """O dia 1º à meia-noite de Brasília do mês de `momento`, em UTC."""
    local = momento.astimezone(FUSO)
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(
        UTC
    )


def travar_reservas(conexao: sa.Connection) -> None:
    """Espera a vez de reservar: uma reserva por vez em todo o PostgreSQL, até o fim da transação.

    Sem a trava, pedidos simultâneos contam as perguntas antes de qualquer um gravar e todos passam:
    uma rajada furaria a cota da conta e o teto do mês. O teto soma todas as contas, então a trava é
    uma só. Chame no começo da transação que confere a cota e grava a reserva. No SQLite (o modo local,
    de uma pessoa) não faz nada: lá a escrita já é uma por vez.
    """
    if conexao.dialect.name != "postgresql":
        return
    conexao.execute(
        sa.text("SELECT pg_advisory_xact_lock(:chave)"),
        {"chave": CHAVE_DA_TRAVA_DAS_RESERVAS},
    )


def reservar(
    conexao: sa.Connection,
    *,
    usuario_id: uuid.UUID,
    organizacao_id: uuid.UUID,
    modelo: str,
    agora: datetime,
) -> uuid.UUID:
    """Grava a pergunta em curso (já conta na cota) e devolve o id dela."""
    pergunta_id = uuid.uuid4()
    conexao.execute(
        sa.insert(perguntas_do_chat).values(
            id=pergunta_id,
            usuario_id=usuario_id,
            organizacao_id=organizacao_id,
            feita_em=_em_utc(agora),
            modelo=modelo,
            estado=EM_CURSO,
        )
    )
    return pergunta_id


def concluir(
    conexao: sa.Connection,
    pergunta_id: uuid.UUID,
    *,
    estado: str,
    uso: UsoDaPergunta,
    latencia_ms: int,
) -> None:
    """Fecha a pergunta com o estado final, o uso e a latência."""
    if estado == EM_CURSO:
        raise ValueError("Uma pergunta concluída não fica em curso.")
    conexao.execute(
        sa.update(perguntas_do_chat)
        .where(perguntas_do_chat.c.id == pergunta_id)
        .values(
            estado=estado,
            tokens_de_entrada=uso.tokens_de_entrada,
            tokens_de_saida=uso.tokens_de_saida,
            tokens_lidos_do_cache=uso.tokens_lidos_do_cache,
            tokens_gravados_no_cache=uso.tokens_gravados_no_cache,
            custo_em_microdolares=uso.custo_em_microdolares,
            chamadas_de_ferramenta=uso.chamadas_de_ferramenta,
            latencia_ms=latencia_ms,
        )
    )


def fechar_abandonadas(
    conexao: sa.Connection, agora: datetime, *, reserva_em_microdolares: int
) -> int:
    """Fecha como erro as perguntas em curso há mais de `MINUTOS_PARA_ABANDONAR`; devolve quantas.

    O gasto delas fica pela reserva (o pior caso): o processo pode ter morrido depois de pagar voltas do
    modelo, e o teto erra para o lado de gastar menos.
    """
    limite = _em_utc(agora) - timedelta(minutes=MINUTOS_PARA_ABANDONAR)
    resultado = conexao.execute(
        sa.update(perguntas_do_chat)
        .where(
            perguntas_do_chat.c.estado == EM_CURSO,
            perguntas_do_chat.c.feita_em < limite,
        )
        .values(estado=ERRO, custo_em_microdolares=reserva_em_microdolares)
    )
    return resultado.rowcount


def perguntas_desde(
    conexao: sa.Connection, usuario_id: uuid.UUID, desde: datetime
) -> int:
    """Quantas perguntas a conta fez a partir de `desde` (todas contam, até as que deram erro)."""
    return conexao.execute(
        sa.select(sa.func.count())
        .select_from(perguntas_do_chat)
        .where(
            perguntas_do_chat.c.usuario_id == usuario_id,
            perguntas_do_chat.c.feita_em >= _em_utc(desde),
        )
    ).scalar_one()


def gasto_do_mes(
    conexao: sa.Connection, agora: datetime, *, reserva_em_microdolares: int
) -> int:
    """O custo do mês somando todas as contas, em microdólares.

    A pergunta ainda em curso entra pela reserva (o pior caso dela), não pelo custo ainda zerado: duas
    perguntas ao mesmo tempo não passam juntas do teto.
    """
    tabela = perguntas_do_chat
    concluidas, em_curso = conexao.execute(
        sa.select(
            sa.func.coalesce(
                sa.func.sum(
                    sa.case(
                        (tabela.c.estado != EM_CURSO, tabela.c.custo_em_microdolares),
                        else_=0,
                    )
                ),
                0,
            ),
            sa.func.coalesce(
                sa.func.sum(sa.case((tabela.c.estado == EM_CURSO, 1), else_=0)), 0
            ),
        ).where(tabela.c.feita_em >= inicio_do_mes(agora))
    ).one()
    return int(concluidas) + int(em_curso) * reserva_em_microdolares


def para_exportar(conexao: sa.Connection, usuario_id: uuid.UUID) -> list[dict]:
    """As perguntas da conta para a exportação da LGPD: só a data, o modelo, o estado e os números."""
    tabela = perguntas_do_chat
    linhas = conexao.execute(
        sa.select(tabela)
        .where(tabela.c.usuario_id == usuario_id)
        .order_by(tabela.c.feita_em)
    )
    return [
        {
            "feita_em": _em_utc(
                l.feita_em if l.feita_em.tzinfo else l.feita_em.replace(tzinfo=UTC)
            ).isoformat(),
            "modelo": l.modelo,
            "estado": l.estado,
            "tokens_de_entrada": l.tokens_de_entrada,
            "tokens_de_saida": l.tokens_de_saida,
            "tokens_lidos_do_cache": l.tokens_lidos_do_cache,
            "tokens_gravados_no_cache": l.tokens_gravados_no_cache,
            "custo_em_microdolares": l.custo_em_microdolares,
            "latencia_ms": l.latencia_ms,
            "chamadas_de_ferramenta": l.chamadas_de_ferramenta,
        }
        for l in linhas
    ]
