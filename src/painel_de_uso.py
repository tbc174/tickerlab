"""Painel de uso (ADR 0109, item 15): quanto gente de verdade usa o app, sem dinheiro.

Até a cobrança real ligar, a empresa mede **usuários ativos por semana**, **relatórios gerados** e
**PDFs entregues**; MRR, churn e CAC ficam para depois (ADR 0052). Só contagens: nenhuma função
devolve e-mail, nome ou id de pessoa. Tudo sai em tipos simples (dicionários e listas), pronto para
virar uma rota da API.

Uma semana vai de segunda 00:00 a domingo 23:59 (UTC) e é identificada pela segunda-feira.
"Usou o app" é qualquer um destes eventos datados da pessoa: entrar (sessão de login), salvar uma
simulação, gerar um relatório em PDF, anotar uma tese ou rodar uma configuração nova do backtest.
O app não guarda "download" à parte: o PDF gerado é o PDF entregue.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import sqlalchemy as sa

from src.administracao import exigir_admin
from src.banco.modelo import (
    relatorios,
    sessoes_de_login,
    simulacoes,
    tentativas,
    teses,
)

SEMANAS_DA_JANELA = 4
SEMANAS_ATIVAS_MINIMAS = 2  # "ativo" = usou em pelo menos 2 das últimas 4 semanas
SEMANAS_NO_HISTORICO = 12

_EVENTOS_DE_USO = (
    (sessoes_de_login, "criada_em"),
    (simulacoes, "criada_em"),
    (relatorios, "criado_em"),
    (teses, "criada_em"),
    (tentativas, "criada_em"),
)


def segunda_da_semana(dia: date) -> date:
    """A segunda-feira da semana que contém `dia`."""
    return dia - timedelta(days=dia.weekday())


def _limites(segunda: date) -> tuple[datetime, datetime]:
    inicio = datetime(segunda.year, segunda.month, segunda.day, tzinfo=UTC)
    return inicio, inicio + timedelta(days=7)


def _semana_do_evento(momento: datetime | str) -> date:
    if isinstance(momento, str):  # o SQLite devolve texto
        momento = datetime.fromisoformat(momento)
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return segunda_da_semana(momento.astimezone(UTC).date())


def _semanas_de_uso(
    conexao: sa.Connection, inicio: datetime, fim: datetime
) -> dict[uuid.UUID, set[date]]:
    """Para cada pessoa, as semanas em que ela fez alguma coisa dentro de [inicio, fim)."""
    por_pessoa: dict[uuid.UUID, set[date]] = {}
    for tabela, coluna in _EVENTOS_DE_USO:
        momento = tabela.c[coluna]
        linhas = conexao.execute(
            sa.select(tabela.c.usuario_id, momento).where(
                momento >= inicio, momento < fim
            )
        )
        for usuario_id, quando in linhas:
            por_pessoa.setdefault(usuario_id, set()).add(_semana_do_evento(quando))
    return por_pessoa


def _contar_relatorios(
    conexao: sa.Connection, inicio: datetime, fim: datetime
) -> dict[str, int]:
    consulta = (
        sa.select(relatorios.c.tipo, sa.func.count())
        .where(relatorios.c.criado_em >= inicio, relatorios.c.criado_em < fim)
        .group_by(relatorios.c.tipo)
    )
    return {tipo: total for tipo, total in conexao.execute(consulta)}


def numeros_da_semana(conexao: sa.Connection, segunda: date) -> dict:
    """Os números de UMA semana: só olha eventos até o fim dela.

    "Sem olhar o futuro": evento depois do domingo não muda o resultado da semana.
    `ativos` usa a janela das 4 semanas que terminam nesta.
    """
    inicio, fim = _limites(segunda)
    janela_inicio, _ = _limites(segunda - timedelta(weeks=SEMANAS_DA_JANELA - 1))
    por_pessoa = _semanas_de_uso(conexao, janela_inicio, fim)
    por_tipo = _contar_relatorios(conexao, inicio, fim)
    return {
        "semana": segunda.isoformat(),
        "ativos_na_semana": sum(1 for s in por_pessoa.values() if segunda in s),
        "ativos": sum(
            1 for s in por_pessoa.values() if len(s) >= SEMANAS_ATIVAS_MINIMAS
        ),
        "relatorios_gerados": sum(por_tipo.values()),
        "relatorios_por_tipo": dict(sorted(por_tipo.items())),
        "pdfs_entregues": sum(por_tipo.values()),
    }


def historico(
    conexao: sa.Connection,
    hoje: date | None = None,
    semanas: int = SEMANAS_NO_HISTORICO,
) -> list[dict]:
    """Os números das últimas `semanas` semanas (a em curso por último), sem checar quem pede.

    Para scripts do servidor; a tela e a API usam `historico_semanal`, que exige administrador.
    """
    atual = segunda_da_semana(hoje or datetime.now(UTC).date())
    return [
        numeros_da_semana(conexao, atual - timedelta(weeks=n))
        for n in range(semanas - 1, -1, -1)
    ]


def historico_semanal(
    conexao: sa.Connection,
    ator_id: uuid.UUID,
    hoje: date | None = None,
    semanas: int = SEMANAS_NO_HISTORICO,
) -> list[dict]:
    """O mesmo histórico, só para administradores."""
    exigir_admin(conexao, ator_id)
    return historico(conexao, hoje, semanas)
