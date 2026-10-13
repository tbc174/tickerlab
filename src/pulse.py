"""O Pulse: o que mudou nos ativos da pessoa desde a última vez que ela o abriu (onda 3, PR E).

Junta, numa janela "desde a última visita", o que outras partes do app já calculam:
- os **acontecimentos** coletados depois da visita (CVM e SEC), na mesma ordem de relevância do
  Research e da Newsletter (`research.ordenar`);
- a **variação** do preço de cada ativo, do último fechamento conhecido na hora da visita até o
  último fechamento de hoje (sem olhar o futuro: um preço que ainda não existia na hora da visita
  nunca vira a base).

Os ativos da pessoa são tudo o que ela guardou: favoritos, a carteira do Research (Pro), as listas
e os ativos das estratégias salvas. Tudo aqui é função pura em tipos simples (ADR 0044): a tela só
lê do banco, chama e mostra. Nada é recomendação.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from src import research
from src.banco.eventos import Evento
from src.dados import normalizar_ticker

FUSO = ZoneInfo("America/Sao_Paulo")
JANELA_DA_PRIMEIRA_VISITA = timedelta(days=7)
# um documento entregue um pouco antes da visita pode ser coletado depois dela; mais velho que
# isso é carga antiga (não é novidade para a pessoa)
PUBLICADOS_ATE_ANTES_DA_VISITA = timedelta(days=30)
# a partir desta hora (São Paulo) o fechamento do dia já existe (B3 fecha às 17h, EUA às 17h)
HORA_DO_FECHAMENTO = 18
TAMANHO_MAXIMO_DO_TICKER = 20  # o mesmo das tabelas do banco
# cada ativo é um download de preços: a página não pode ficar lenta
MAXIMO_DE_ATIVOS = 30
NOME_DOS_FAVORITOS = "favoritos"
NOME_DA_CARTEIRA = research.NOME_DA_CARTEIRA
NOME_DAS_ESTRATEGIAS = "estratégias salvas"
LIMITES = (
    (
        "Os acontecimentos vêm de documentos públicos entregues à CVM e à SEC, coletados uma "
        "vez por dia; um documento pode chegar com atraso ou ser corrigido depois."
    ),
    (
        "A variação usa o fechamento do Yahoo Finance, que pode ter atraso ou erros, e não "
        "inclui proventos."
    ),
    "O Pulse mostra o que mudou, não o que fazer: nada aqui é recomendação de investimento.",
)


def _codigo(ticker: str) -> str:
    return ticker.removesuffix(".SA")


# --- janela ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Janela:
    desde: datetime  # a última visita (ou 7 dias atrás, na primeira)
    ate: datetime  # agora, na hora em que a página foi aberta
    primeira_vez: bool

    @property
    def publicados_desde(self) -> date:
        return (self.desde - PUBLICADOS_ATE_ANTES_DA_VISITA).astimezone(FUSO).date()


def janela(ultima_visita: datetime | None, agora: datetime) -> Janela:
    """A janela do Pulse: da última visita até agora (na primeira vez, os últimos 7 dias)."""
    if agora.tzinfo is None or (
        ultima_visita is not None and ultima_visita.tzinfo is None
    ):
        raise ValueError("As horas do Pulse precisam ter fuso.")
    if ultima_visita is None:
        return Janela(agora - JANELA_DA_PRIMEIRA_VISITA, agora, primeira_vez=True)
    return Janela(min(ultima_visita, agora), agora, primeira_vez=False)


def texto_da_janela(j: Janela) -> str:
    if j.primeira_vez:
        return (
            "Primeira visita: o que aconteceu nos últimos "
            f"{JANELA_DA_PRIMEIRA_VISITA.days} dias."
        )
    desde = j.desde.astimezone(FUSO)
    return f"Desde a sua última visita, em {desde:%d/%m/%Y} às {desde:%Hh%M}."


# --- ativos da pessoa -----------------------------------------------------------------------


@dataclass(frozen=True)
class AtivoDaPessoa:
    ticker: str
    origens: tuple[
        str, ...
    ]  # "favoritos", "Minha carteira", "lista X", "estratégias salvas"


def ativos_da_pessoa(
    favoritos: Iterable[str],
    carteira: Iterable[str],
    listas: Iterable[tuple[str, Iterable[str]]],
    estrategias: Iterable[object],
    maximo: int = MAXIMO_DE_ATIVOS,
) -> tuple[tuple[AtivoDaPessoa, ...], int]:
    """Os ativos guardados pela pessoa, sem repetir, e quantos ficaram além do `maximo`.

    A ordem é a de quem ela escolheu primeiro: favoritos, carteira, listas, estratégias.
    """
    fontes: list[tuple[str, Iterable[object]]] = [
        (NOME_DOS_FAVORITOS, favoritos),
        (NOME_DA_CARTEIRA, carteira),
        *((f"lista {nome}", tickers) for nome, tickers in listas),
        (NOME_DAS_ESTRATEGIAS, estrategias),
    ]
    origens: dict[str, list[str]] = {}
    for origem, tickers in fontes:
        for bruto in tickers:
            if (
                not isinstance(bruto, str)
                or len(bruto.strip()) > TAMANHO_MAXIMO_DO_TICKER
            ):
                continue  # o retrato de uma simulação salva vem do banco: não confiável
            ticker = normalizar_ticker(bruto)
            if ticker and origem not in origens.setdefault(ticker, []):
                origens[ticker].append(origem)
    todos = [AtivoDaPessoa(t, tuple(o)) for t, o in origens.items()]
    return tuple(todos[:maximo]), max(len(todos) - maximo, 0)


# --- variação -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Variacao:
    ticker: str
    de: date
    preco_de: float
    ate: date
    preco_ate: float

    @property
    def retorno(self) -> float:
        return self.preco_ate / self.preco_de - 1


def _ultimo_dia_fechado(visita: datetime) -> date:
    """O último dia cujo fechamento já existia na hora da visita."""
    local = visita.astimezone(FUSO)
    if local.hour >= HORA_DO_FECHAMENTO:
        return local.date()
    return local.date() - timedelta(days=1)


def variacao(ticker: str, fechamentos: pd.Series, visita: datetime) -> Variacao | None:
    """Do último fechamento conhecido na hora da visita ao último fechamento da série.

    None quando não há preço antes da visita ou nenhum pregão novo depois dela.
    """
    serie = pd.Series(fechamentos, dtype=float).dropna().sort_index()
    serie = serie[serie > 0]
    dias = [pd.Timestamp(rotulo).date() for rotulo in serie.index]
    corte = _ultimo_dia_fechado(visita)
    fechados = [i for i, dia in enumerate(dias) if dia <= corte]
    if not fechados or dias[-1] <= dias[fechados[-1]]:
        return None
    base = fechados[-1]
    return Variacao(
        ticker, dias[base], float(serie.iloc[base]), dias[-1], float(serie.iloc[-1])
    )


# períodos aceitos pelo leitor de preços e quantos dias cada um cobre com folga (feriados)
PERIODOS_DE_PRECOS = (("6mo", 170), ("1y", 350), ("2y", 715))


def periodo_de_precos(j: Janela) -> str:
    """O menor histórico de preços que ainda tem o fechamento de antes da visita."""
    dias = (j.ate - j.desde).days
    return next((p for p, cobre in PERIODOS_DE_PRECOS if dias <= cobre), "5y")


def ordenar_variacoes(variacoes: Iterable[Variacao]) -> list[Variacao]:
    """A maior mudança (para cima ou para baixo) primeiro."""
    return sorted(variacoes, key=lambda v: abs(v.retorno), reverse=True)


def texto_da_variacao(v: Variacao) -> str:
    numero = f"{v.retorno * 100:+.1f}".replace(".", ",")
    return f"{_codigo(v.ticker)}: {numero}% (de {v.de:%d/%m} a {v.ate:%d/%m})"


# --- acontecimentos -------------------------------------------------------------------------


def acontecimentos(
    eventos: Iterable[Evento],
    ativos: Iterable[AtivoDaPessoa],
    j: Janela,
    pesos: Mapping[str, float],
    temas: Iterable[str],
) -> list[research.ItemDoResearch]:
    """Os eventos novos por relevância, todos (é o que mudou), com a origem de cada ativo."""
    hoje = j.ate.astimezone(FUSO).date()
    itens = research.ordenar(
        eventos,
        pesos,
        temas,
        hoje,
        max((hoje - j.publicados_desde).days, 1),
        "Pulse",
        maximo_por_ativo=None,
    )
    origens = {a.ticker: a.origens for a in ativos}
    return [_com_a_origem(item, origens.get(item.evento.ticker, ())) for item in itens]


def _com_a_origem(
    item: research.ItemDoResearch, origens: tuple[str, ...]
) -> research.ItemDoResearch:
    codigo = _codigo(item.evento.ticker)
    razao = (
        f"Você acompanha {codigo} em: {', '.join(origens)}."
        if origens
        else (f"Você acompanha {codigo}.")
    )
    return replace(item, razoes=[razao, *item.razoes[1:]])


def agora() -> datetime:
    return datetime.now(UTC)
