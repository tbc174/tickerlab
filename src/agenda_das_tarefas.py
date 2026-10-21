"""Agenda das tarefas dos servidores, lida do próprio crontab (painel das coletas).

Cada tarefa que roda por `rodar-tarefa.sh NOME LOG 'comando'` entra na agenda com o seu período (o
maior intervalo entre duas rodadas) e o prazo (período mais uma folga). O prazo sai do crontab, e não
de uma lista escrita à mão, para que tarefa nova no cron já nasça conferida: antes, quem esquecia de
pôr a tarefa no `conferir-tarefas.sh` deixava a coleta parar em silêncio.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise

SCRIPT_DAS_TAREFAS = "rodar-tarefa.sh"
NOME_VALIDO = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

# folga somada ao período: as faixas mantêm os limites que os conferir-tarefas*.sh já usavam
# (26 h para a diária, 8 dias para a semanal, 35 dias para a mensal)
FOLGA_ATE_UM_DIA = timedelta(hours=2)
FOLGA_ATE_UMA_SEMANA = timedelta(days=1)
FOLGA_ACIMA_DE_UMA_SEMANA = timedelta(days=4)

# as rodadas são contadas a partir de uma segunda-feira fixa; a janela longa cobre fevereiro, meses
# de 30 e 31 dias e um ano bissexto (em UTC: o Brasil não tem mais horário de verão, e o intervalo
# entre rodadas não depende do fuso)
INICIO_DA_CONTAGEM = datetime(2024, 1, 1, tzinfo=UTC)
JANELA_CURTA = timedelta(days=2)
JANELA_SEMANAL = timedelta(days=15)
JANELA_LONGA = timedelta(days=4 * 366)
MESES_NO_ANO = 12

MACROS = {
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@weekly": "0 0 * * 0",
    "@monthly": "0 0 1 * *",
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
}
MACROS_SEM_HORARIO = {"@reboot"}

# (mínimo, máximo) de cada campo: minuto, hora, dia do mês, mês, dia da semana (0 e 7 são domingo)
LIMITES_DOS_CAMPOS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
CAMPOS_DA_EXPRESSAO = len(LIMITES_DOS_CAMPOS)
DOMINGO_TAMBEM = 7


@dataclass(frozen=True)
class TarefaAgendada:
    """Uma tarefa do crontab: nome, maior intervalo entre rodadas, prazo, expressões do cron e log."""

    nome: str
    periodo: timedelta
    prazo: timedelta
    horarios: tuple[str, ...]
    log: str | None = (
        None  # o LOG do rodar-tarefa.sh (o da 1ª linha, se a tarefa tiver várias)
    )


@dataclass(frozen=True)
class _Expressao:
    minutos: frozenset[int]
    horas: frozenset[int]
    dias_do_mes: frozenset[int]
    meses: frozenset[int]
    dias_da_semana: frozenset[int]  # 0 = domingo, como no cron
    dia_do_mes_restrito: bool
    dia_da_semana_restrito: bool


def ler_agenda(texto_do_crontab: str) -> list[TarefaAgendada]:
    """Devolve as tarefas do `rodar-tarefa.sh` no texto de um `crontab -l`, na ordem em que aparecem.

    Linhas de comentário, de variável, `@reboot` e as que não usam o `rodar-tarefa.sh` ficam de fora.
    A tarefa com mais de uma linha (ex.: duas rodadas por dia) vira uma entrada só.
    """
    horarios_por_nome: dict[str, list[str]] = {}
    log_por_nome: dict[str, str | None] = {}
    for linha in texto_do_crontab.splitlines():
        lida = _ler_linha(linha)
        if lida:
            nome, expressao, log = lida
            horarios_por_nome.setdefault(nome, []).append(expressao)
            log_por_nome.setdefault(nome, log)
    return [
        _agendar(nome, horarios, log_por_nome[nome])
        for nome, horarios in horarios_por_nome.items()
    ]


def periodo_da_expressao(expressao: str) -> timedelta:
    """Devolve o maior intervalo entre duas rodadas de uma expressão do cron (5 campos ou macro)."""
    return _maior_intervalo([expressao])


def prazo_do_periodo(periodo: timedelta) -> timedelta:
    """Devolve o prazo de uma tarefa: o período mais a folga da faixa dele."""
    if periodo <= timedelta(days=1):
        return periodo + FOLGA_ATE_UM_DIA
    if periodo <= timedelta(days=7):
        return periodo + FOLGA_ATE_UMA_SEMANA
    return periodo + FOLGA_ACIMA_DE_UMA_SEMANA


def _agendar(nome: str, horarios: list[str], log: str | None) -> TarefaAgendada:
    periodo = _maior_intervalo(horarios)
    return TarefaAgendada(
        nome, periodo, prazo_do_periodo(periodo), tuple(horarios), log
    )


def _ler_linha(linha: str) -> tuple[str, str, str | None] | None:
    """Devolve (nome, expressão do cron, log) de uma linha do `rodar-tarefa.sh`, ou None."""
    partes = linha.split()
    if not partes or partes[0].startswith("#") or "=" in partes[0]:
        return None
    if partes[0] in MACROS_SEM_HORARIO:
        return None
    if partes[0].startswith("@"):
        expressao, comando = partes[0], partes[1:]
    else:
        expressao, comando = (
            " ".join(partes[:CAMPOS_DA_EXPRESSAO]),
            partes[CAMPOS_DA_EXPRESSAO:],
        )
    posicao = next(
        (i for i, parte in enumerate(comando) if parte.endswith(SCRIPT_DAS_TAREFAS)),
        None,
    )
    if posicao is None or posicao + 1 >= len(comando):
        return None
    nome = comando[posicao + 1]
    if not NOME_VALIDO.match(nome):
        raise ValueError(f"nome de tarefa fora do padrão no crontab: {nome[:40]!r}")
    log = comando[posicao + 2] if posicao + 2 < len(comando) else None
    return nome, expressao, log


def _maior_intervalo(horarios: Iterable[str]) -> timedelta:
    """Devolve o maior intervalo entre duas rodadas seguidas de um grupo de expressões do cron.

    Conta dia a dia, guardando de cada dia só a primeira e a última rodada e o maior intervalo
    dentro dele: assim uma expressão de 5 em 5 minutos num ano inteiro não vira 100 mil horários.
    """
    expressoes = [_ler_expressao(horario) for horario in horarios]
    janela = max(_janela(e) for e in expressoes)
    resumos: dict[tuple[int, ...], _ResumoDoDia] = {}
    maior: timedelta | None = None
    ultima_rodada: datetime | None = None
    for deslocamento in range(janela.days):
        dia = INICIO_DA_CONTAGEM + timedelta(days=deslocamento)
        quais = tuple(i for i, e in enumerate(expressoes) if _roda_no_dia(e, dia))
        if not quais:
            continue
        if quais not in resumos:
            resumos[quais] = _resumir_o_dia([expressoes[i] for i in quais])
        resumo = resumos[quais]
        candidatos = [resumo.maior_intervalo, maior]
        if ultima_rodada is not None:
            candidatos.append(dia + resumo.primeira - ultima_rodada)
        maior = max((c for c in candidatos if c is not None), default=None)
        ultima_rodada = dia + resumo.ultima
    if maior is None:
        raise ValueError("expressão do cron que quase nunca roda: sem prazo possível")
    return maior


@dataclass(frozen=True)
class _ResumoDoDia:
    primeira: timedelta
    ultima: timedelta
    maior_intervalo: timedelta | None  # None quando o dia tem uma rodada só


def _resumir_o_dia(expressoes: list[_Expressao]) -> _ResumoDoDia:
    horarios = sorted(
        {
            timedelta(hours=h, minutes=m)
            for e in expressoes
            for h in e.horas
            for m in e.minutos
        }
    )
    intervalos = [depois - antes for antes, depois in pairwise(horarios)]
    return _ResumoDoDia(horarios[0], horarios[-1], max(intervalos, default=None))


def _janela(expressao: _Expressao) -> timedelta:
    """Quantos dias contar: a menor janela que mostra o maior intervalo da expressão."""
    if expressao.dia_do_mes_restrito or len(expressao.meses) < MESES_NO_ANO:
        return JANELA_LONGA
    if expressao.dia_da_semana_restrito:
        return JANELA_SEMANAL
    return JANELA_CURTA


def _roda_no_dia(expressao: _Expressao, dia: datetime) -> bool:
    if dia.month not in expressao.meses:
        return False
    dia_da_semana = dia.isoweekday() % 7  # domingo vira 0, como no cron
    no_dia_do_mes = dia.day in expressao.dias_do_mes
    no_dia_da_semana = dia_da_semana in expressao.dias_da_semana
    # regra do cron: com os dois campos restritos, basta um deles
    if expressao.dia_do_mes_restrito and expressao.dia_da_semana_restrito:
        return no_dia_do_mes or no_dia_da_semana
    return no_dia_do_mes and no_dia_da_semana


def _ler_expressao(horario: str) -> _Expressao:
    campos = MACROS.get(horario, horario).split()
    if len(campos) != CAMPOS_DA_EXPRESSAO:
        raise ValueError(f"expressão do cron sem 5 campos: {horario[:40]!r}")
    valores = [
        _valores_do_campo(campo, minimo, maximo)
        for campo, (minimo, maximo) in zip(campos, LIMITES_DOS_CAMPOS, strict=True)
    ]
    dias_da_semana = frozenset(0 if d == DOMINGO_TAMBEM else d for d in valores[4])
    return _Expressao(
        minutos=valores[0],
        horas=valores[1],
        dias_do_mes=valores[2],
        meses=valores[3],
        dias_da_semana=dias_da_semana,
        # como no cron: campo que começa com "*" (inclusive "*/2") não conta como restrito
        dia_do_mes_restrito=not campos[2].startswith("*"),
        dia_da_semana_restrito=not campos[4].startswith("*"),
    )


def _valores_do_campo(campo: str, minimo: int, maximo: int) -> frozenset[int]:
    valores: set[int] = set()
    for pedaco in campo.split(","):
        intervalo, _, passo = pedaco.partition("/")
        if intervalo == "*":
            inicio, fim = minimo, maximo
        elif "-" in intervalo:
            inicio, fim = (_numero(p, minimo, maximo) for p in intervalo.split("-", 1))
        else:
            inicio = fim = _numero(intervalo, minimo, maximo)
        if passo and intervalo != "*" and "-" not in intervalo:
            fim = maximo  # "5/10" vale de 5 até o fim, de 10 em 10
        valores.update(
            range(inicio, fim + 1, _numero(passo, 1, maximo) if passo else 1)
        )
    return frozenset(valores)


def _numero(texto: str, minimo: int, maximo: int) -> int:
    if not texto.isdigit() or not minimo <= int(texto) <= maximo:
        raise ValueError(f"campo do cron fora do esperado: {texto[:20]!r}")
    return int(texto)
