"""Diário de Teses: as regras, em tipos simples (onda 3, PR F; ADR 0046, atualização 2).

A pessoa escreve anotações datadas sobre um ativo (por que comprou, o que espera, o que a faria
mudar de ideia) e pode ligar cada uma a backtests salvos do mesmo ativo. Uma anotação não se edita,
só se apaga: o diário mostra o que ela pensava naquele dia, sem reescrever o passado.

Sem banco e sem tela (ADR 0044): o banco (`src/banco/teses.py`) e a página usam estas funções. O
texto é da pessoa e é tratado como dado não confiável: limpo aqui e mostrado como texto puro.
"""

import unicodedata
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.banco.modelo import TAMANHO_MAXIMO_DA_TESE
from src.dados import normalizar_ticker
from src.link import ticker_valido

TAMANHO_MAXIMO = (
    TAMANHO_MAXIMO_DA_TESE  # caracteres por anotação (a mesma trava do banco)
)
MAXIMO_DE_ANOTACOES = 500  # por conta: trava contra abuso, igual para todos os planos
MAXIMO_DE_ESTRATEGIAS = 10  # backtests ligados a uma anotação
TAMANHO_DO_TRECHO = 200  # o pedaço da tese que aparece no Pulse
_CONTROLES_PERMITIDOS = frozenset(
    "\n\t‍"
)  # quebra de linha, tabulação e o "junta emoji"


class TeseInvalidaError(ValueError):
    """O que a pessoa mandou não pode ser guardado no diário (a mensagem é para ela)."""


@dataclass(frozen=True)
class Anotacao:
    id: uuid.UUID
    ticker: str
    texto: str
    criada_em: datetime
    estrategias: tuple[uuid.UUID, ...]  # os backtests salvos ligados a ela


class _SimulacaoSalva(Protocol):
    tipo: str
    parametros: object


def limpar_texto(texto: str) -> str:
    """O texto pronto para guardar: sem caracteres de controle, quebras de linha `\\n`, sem
    espaço nas pontas. Recusa vazio e acima de `TAMANHO_MAXIMO` caracteres."""
    if not isinstance(texto, str):
        raise TeseInvalidaError("Escreva a sua tese em texto.")
    texto = unicodedata.normalize(
        "NFC", texto.replace("\r\n", "\n").replace("\r", "\n")
    )
    limpo = "".join(
        c
        for c in texto
        if c in _CONTROLES_PERMITIDOS or not unicodedata.category(c).startswith("C")
    ).strip()
    if not limpo:
        raise TeseInvalidaError("Escreva alguma coisa antes de guardar.")
    if len(limpo) > TAMANHO_MAXIMO:
        raise TeseInvalidaError(
            f"Cada anotação pode ter até {TAMANHO_MAXIMO} caracteres "
            f"(esta tem {len(limpo)}). Divida em duas."
        )
    return limpo


def ticker_da_tese(bruto: str) -> str:
    """O ticker como o app usa (`PETR4` → `PETR4.SA`); recusa o que não é um código de ativo."""
    ticker = normalizar_ticker(bruto) if isinstance(bruto, str) else ""
    if not ticker_valido(ticker):
        raise TeseInvalidaError("Escolha um ativo válido (ex.: PETR4 ou AAPL).")
    return ticker


def ticker_do_backtest(parametros: object) -> str | None:
    """O ativo do retrato guardado com o backtest. Vem do banco: o que for estranho vira None."""
    if not isinstance(parametros, Mapping):
        return None
    bruto = parametros.get("ticker")
    if not isinstance(bruto, str):
        return None
    ticker = normalizar_ticker(bruto)
    return ticker if ticker_valido(ticker) else None


def backtests_que_podem_ser_ligados[S: _SimulacaoSalva](
    ticker: str, simulacoes: Iterable[S]
) -> list[S]:
    """Os backtests salvos do mesmo ativo da tese, na ordem recebida."""
    return [
        s
        for s in simulacoes
        if s.tipo == "backtest" and ticker_do_backtest(s.parametros) == ticker
    ]


def agrupar_por_ativo(
    anotacoes: Iterable[Anotacao],
) -> list[tuple[str, list[Anotacao]]]:
    """As anotações por ativo: primeiro o ativo da anotação mais nova; dentro dele, a mais nova."""
    grupos: dict[str, list[Anotacao]] = {}
    for anotacao in sorted(anotacoes, key=lambda a: a.criada_em, reverse=True):
        grupos.setdefault(anotacao.ticker, []).append(anotacao)
    return list(grupos.items())


def trecho(texto: str, maximo: int = TAMANHO_DO_TRECHO) -> str:
    """O começo do texto numa linha só, cortado no fim de uma palavra e com "…" se foi cortado."""
    corrido = " ".join(texto.split())
    if len(corrido) <= maximo:
        return corrido
    cortado = corrido[: maximo - 1]
    if " " in cortado:
        cortado = cortado.rsplit(" ", 1)[0]
    return cortado.rstrip() + "…"
