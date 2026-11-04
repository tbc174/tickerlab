"""Painel de uso (ADR 0109, item 15): quanto gente de verdade usa o app, sem dinheiro.

Até a cobrança real ligar, a empresa mede **usuários ativos por semana**, **relatórios gerados** e
**PDFs entregues**; MRR, churn e CAC ficam para depois (ADR 0052). Só contagens: nenhuma função
devolve e-mail, nome ou id de pessoa. Tudo sai em tipos simples (dicionários e listas), pronto para
virar uma rota da API.

Uma semana vai de segunda 00:00 a domingo 23:59 (UTC) e é identificada pela segunda-feira.
"Usou o app" é qualquer um destes eventos datados da pessoa: entrar (sessão de login), salvar uma
simulação, gerar um relatório em PDF, anotar uma tese ou rodar uma configuração nova do backtest.
O app não guarda "download" à parte: o PDF gerado é o PDF entregue.

**Ativos por origem** (plano da campanha, seção 5): os mesmos ativos, separados pela origem do
cadastro (`origens_do_cadastro`, lida do cookie `tl_origem` no primeiro login). Mostra qual canal
traz gente que volta, não só gente que se cadastra. Conta apagada sai da contagem (LGPD).
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import sqlalchemy as sa

from src.administracao import exigir_admin
from src.banco.modelo import (
    origens_do_cadastro,
    relatorios,
    sessoes_de_login,
    simulacoes,
    tentativas,
    teses,
    usuarios,
)

SEMANAS_DA_JANELA = 4
SEMANAS_ATIVAS_MINIMAS = 2  # "ativo" = usou em pelo menos 2 das últimas 4 semanas
SEMANAS_NO_HISTORICO = 12
# o que separa um canal do outro; a peça (`utm_content`) fica de fora: dividiria demais
CAMPOS_DA_ORIGEM = ("utm_source", "utm_medium", "utm_campaign", "ref")

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


def _ativos(por_pessoa: dict[uuid.UUID, set[date]]) -> set[uuid.UUID]:
    """Quem usou o app em pelo menos `SEMANAS_ATIVAS_MINIMAS` semanas da janela."""
    return {
        p for p, semanas in por_pessoa.items() if len(semanas) >= SEMANAS_ATIVAS_MINIMAS
    }


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
        "ativos": len(_ativos(por_pessoa)),
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


def ativos_por_origem(conexao: sa.Connection, segunda: date) -> list[dict]:
    """Cadastros e ativos de cada origem, na semana que começa em `segunda`, sem checar quem pede.

    Uma linha por origem (`CAMPOS_DA_ORIGEM`; todos `None` = chegou sem link de campanha), com
    `cadastros` (contas criadas até o fim da semana), `cadastros_na_semana` e `ativos` (mesma regra
    de `numeros_da_semana`). Quem traz mais ativos vem primeiro. "Sem olhar o futuro": conta e uso
    depois do domingo não mudam a semana. Só contagens, nenhum id ou e-mail.
    """
    _, fim = _limites(segunda)
    janela_inicio, _ = _limites(segunda - timedelta(weeks=SEMANAS_DA_JANELA - 1))
    ativos = _ativos(_semanas_de_uso(conexao, janela_inicio, fim))
    consulta = (
        sa.select(
            usuarios.c.id,
            usuarios.c.criado_em,
            *(origens_do_cadastro.c[campo] for campo in CAMPOS_DA_ORIGEM),
        )
        .select_from(usuarios.outerjoin(origens_do_cadastro))
        .where(usuarios.c.criado_em < fim, usuarios.c.excluido_em.is_(None))
    )
    por_origem: dict[tuple, dict] = {}
    for usuario_id, criado_em, *origem in conexao.execute(consulta):
        linha = por_origem.setdefault(
            tuple(origem),
            dict(zip(CAMPOS_DA_ORIGEM, origem, strict=True))
            | {"cadastros": 0, "cadastros_na_semana": 0, "ativos": 0},
        )
        linha["cadastros"] += 1
        linha["cadastros_na_semana"] += _semana_do_evento(criado_em) == segunda
        linha["ativos"] += usuario_id in ativos
    return sorted(
        por_origem.values(),
        key=lambda l: (
            -l["ativos"],
            -l["cadastros"],
            *(l[c] or "" for c in CAMPOS_DA_ORIGEM),
        ),
    )


def ativos_por_origem_do_admin(
    conexao: sa.Connection, ator_id: uuid.UUID, hoje: date | None = None
) -> list[dict]:
    """Os ativos por origem da semana em curso, só para administradores."""
    exigir_admin(conexao, ator_id)
    return ativos_por_origem(
        conexao, segunda_da_semana(hoje or datetime.now(UTC).date())
    )
