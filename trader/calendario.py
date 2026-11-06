"""Calendário das estratégias quant (base comum das 8 P0; ADR 0118): quando cada mercado negocia.

O backtest honesto só executa no pregão seguinte ao sinal: o sinal sai com o fechamento do dia D e a
ordem entra no dia D+1 (`proxima_execucao`). Aqui ficam as regras de data que cada estratégia precisa,
num lugar só:

- **B3:** pregões (o calendário de `src/calendario_b3.py`), pregão anterior e seguinte, primeiro e
  último do mês (rebalanceamento mensal), leilões de abertura e de fechamento.
- **WIN (mini-índice):** vence na quarta-feira mais próxima do dia 15 dos meses pares; se essa
  quarta não tem pregão, no pregão seguinte. A rolagem do backtest é no pregão anterior ao
  vencimento, e `contrato_do_win` diz qual contrato está em vigor em cada dia.
- **DI1 (juros):** vence no primeiro pregão do mês, em todos os meses; `di1_de_janeiro` acha o
  vértice de janeiro mais perto de um prazo em anos (o mesmo critério do pregão do dia).
- **Cripto:** 365 dias por ano; o dia seguinte é o dia corrido seguinte.

Horários dos leilões (hora de Brasília): pré-abertura das 09h45 às 10h00 e chamada de fechamento das
16h55 às 17h00 [**a confirmar** na tabela de horários da B3, que muda com o horário de verão dos EUA].
Eles só entram no backtest como o instante do preço usado (abertura ou fechamento), nunca como
estratégia intradiária.

Nada aqui olha o futuro: toda função depende só das datas que recebe (há teste de que cortar o
futuro não muda o passado).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from src.calendario_b3 import FECHAMENTOS_EXTRAS, eh_pregao, feriados
from src.pregao_do_dia import LETRAS_DOS_MESES

__all__ = [
    "FECHAMENTOS_EXTRAS",
    "LEILAO_DE_ABERTURA",
    "LEILAO_DE_FECHAMENTO",
    "MERCADOS",
    "codigo_do_di1",
    "codigo_do_win",
    "contrato_do_win",
    "di1_de_janeiro",
    "dias_de_cripto",
    "dias_de_negociacao",
    "eh_pregao",
    "feriados",
    "momento_do_leilao",
    "pregao_anterior",
    "pregoes",
    "primeiro_pregao_do_mes",
    "proxima_execucao",
    "proximo_pregao",
    "rolagem_do_win",
    "ultimo_pregao_do_mes",
    "vencimento_do_di1",
    "vencimento_do_win",
    "vencimentos_do_win",
]

MERCADOS = ("b3", "cripto")
UM_DIA = timedelta(days=1)
QUARTA_FEIRA = 2  # weekday(): segunda = 0
DIA_DE_REFERENCIA_DO_WIN = 15
MESES_DO_WIN = (2, 4, 6, 8, 10, 12)
DIAS_POR_ANO = 365  # prazo em anos corridos do vértice do DI1
MES_DE_JANEIRO = 1


@dataclass(frozen=True)
class Leilao:
    """Um leilão da B3: a janela de chamada (`inicio` a `fim`) e o nome que aparece nos relatórios."""

    nome: str
    inicio: time
    fim: time


LEILAO_DE_ABERTURA = Leilao("abertura", time(9, 45), time(10, 0))
LEILAO_DE_FECHAMENTO = Leilao("fechamento", time(16, 55), time(17, 0))


# --- Pregões da B3 ---------------------------------------------------------------------


def proximo_pregao(dia: date) -> date:
    """O primeiro pregão depois de `dia` (nunca o próprio dia)."""
    seguinte = dia + UM_DIA
    while not eh_pregao(seguinte):
        seguinte += UM_DIA
    return seguinte


def pregao_anterior(dia: date) -> date:
    """O último pregão antes de `dia` (nunca o próprio dia)."""
    anterior = dia - UM_DIA
    while not eh_pregao(anterior):
        anterior -= UM_DIA
    return anterior


def pregoes(inicio: date, fim: date) -> list[date]:
    """Os pregões de `inicio` a `fim`, as duas pontas inclusive."""
    return [dia for dia in dias_de_cripto(inicio, fim) if eh_pregao(dia)]


def primeiro_pregao_do_mes(ano: int, mes: int) -> date:
    """O primeiro pregão do mês (o vencimento do DI1 e o dia do rebalanceamento mensal)."""
    primeiro = date(ano, mes, 1)
    return primeiro if eh_pregao(primeiro) else proximo_pregao(primeiro)


def ultimo_pregao_do_mes(ano: int, mes: int) -> date:
    """O último pregão do mês (a B3 fecha em 31/12, então dezembro termina antes)."""
    proximo_mes = date(ano + (mes == 12), mes % 12 + 1, 1)
    return pregao_anterior(proximo_mes)


def momento_do_leilao(pregao: date, leilao: Leilao) -> datetime:
    """O instante em que o leilão termina e sai o preço (sem fuso; a hora é a de Brasília)."""
    return datetime.combine(pregao, leilao.fim)


# --- Execução no dia seguinte ---------------------------------------------------------


def proxima_execucao(sinal: date, mercado: str = "b3") -> date:
    """O dia em que um sinal fechado em `sinal` pode ser executado: o próximo pregão na B3, o dia
    corrido seguinte em cripto. Nunca o próprio dia: é o atraso de um dia que o backtest simula."""
    _conferir_mercado(mercado)
    if mercado == "cripto":
        return sinal + UM_DIA
    return proximo_pregao(sinal)


def dias_de_negociacao(inicio: date, fim: date, mercado: str) -> list[date]:
    """Os dias em que `mercado` negocia entre as datas (pontas inclusive)."""
    _conferir_mercado(mercado)
    if mercado == "cripto":
        return dias_de_cripto(inicio, fim)
    return pregoes(inicio, fim)


def dias_de_cripto(inicio: date, fim: date) -> list[date]:
    """Todos os dias corridos de `inicio` a `fim` (cripto negocia 365 dias por ano)."""
    if fim < inicio:
        return []
    return [inicio + timedelta(days=n) for n in range((fim - inicio).days + 1)]


def _conferir_mercado(mercado: str) -> None:
    if mercado not in MERCADOS:
        raise ValueError(f"mercado desconhecido: {mercado!r} (use um de {MERCADOS})")


# --- WIN (mini-índice) ------------------------------------------------------------------


def vencimento_do_win(ano: int, mes: int) -> date:
    """O vencimento do WIN de `ano`/`mes`: a quarta-feira mais próxima do dia 15 (meses pares) ou, se
    ela não tem pregão, o pregão seguinte."""
    if mes not in MESES_DO_WIN:
        raise ValueError(f"o WIN só vence nos meses pares; recebi {mes}")
    referencia = date(ano, mes, DIA_DE_REFERENCIA_DO_WIN)
    quarta = referencia + timedelta(days=_dias_ate_a_quarta_mais_proxima(referencia))
    return quarta if eh_pregao(quarta) else proximo_pregao(quarta)


def _dias_ate_a_quarta_mais_proxima(dia: date) -> int:
    """Quantos dias (de -3 a +3) até a quarta-feira mais perto de `dia`."""
    adiante = (QUARTA_FEIRA - dia.weekday()) % 7
    return adiante if adiante <= 3 else adiante - 7


def rolagem_do_win(ano: int, mes: int) -> date:
    """O pregão em que o backtest troca de contrato: o anterior ao vencimento."""
    return pregao_anterior(vencimento_do_win(ano, mes))


def codigo_do_win(ano: int, mes: int) -> str:
    """O código do contrato (`WINZ25` para dezembro de 2025)."""
    return f"WIN{LETRAS_DOS_MESES[mes - 1]}{ano % 100:02d}"


def contrato_do_win(dia: date) -> str:
    """O contrato do WIN que a carteira carrega em `dia`: o do próximo vencimento, já trocado no dia
    seguinte à rolagem (no dia da rolagem a posição ainda é do contrato que vence)."""
    ano, mes = dia.year, dia.month
    while True:
        if mes in MESES_DO_WIN and dia <= rolagem_do_win(ano, mes):
            return codigo_do_win(ano, mes)
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)


def vencimentos_do_win(inicio: date, fim: date) -> list[date]:
    """Os vencimentos do WIN entre as datas (pontas inclusive)."""
    candidatos = [
        vencimento_do_win(ano, mes)
        for ano in range(inicio.year, fim.year + 1)
        for mes in MESES_DO_WIN
    ]
    return [dia for dia in candidatos if inicio <= dia <= fim]


# --- DI1 (juros) -------------------------------------------------------------------------


def vencimento_do_di1(ano: int, mes: int) -> date:
    """O vencimento do DI1 de `ano`/`mes`: o primeiro pregão do mês."""
    return primeiro_pregao_do_mes(ano, mes)


def codigo_do_di1(ano: int, mes: int) -> str:
    """O código do contrato (`DI1F27` para janeiro de 2027)."""
    return f"DI1{LETRAS_DOS_MESES[mes - 1]}{ano % 100:02d}"


def di1_de_janeiro(dia: date, anos: int) -> str:
    """O DI1 de janeiro cujo vencimento fica mais perto de `anos` anos corridos depois de `dia`."""
    alvo = dia + timedelta(days=anos * DIAS_POR_ANO)
    ano = min(
        (alvo.year, alvo.year + 1),
        key=lambda candidato: abs(date(candidato, MES_DE_JANEIRO, 1) - alvo),
    )
    return codigo_do_di1(ano, MES_DE_JANEIRO)
