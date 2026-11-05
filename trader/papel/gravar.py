"""Grava o que está pendente no papel da v0.2 (roda agendado; pode rodar quantas vezes quiser).

    python -m trader.papel.gravar                          # grava o dia pendente de cada série
    python -m trader.papel.gravar --iniciar 2026-11-05 --commit <sha>   # uma vez, depois do merge
    python -m trader.papel.gravar --verificar              # confere as cadeias
    python -m trader.papel.gravar --julgar                 # P1 a P3 até hoje (parcial antes dos 12 meses)

Cada série, a cada rodada: o dia cujo prazo passou vira falta; o dia que ainda não abriu (antes do
fechamento da véspera) espera; o dia aberto é gravado se o preço do fechamento já saiu, senão espera
a próxima rodada. Gravar duas vezes é impossível (a cadeia recusa), então rodar de novo é seguro.

Nada vai para corretora e nada aqui é recomendação de investimento.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from trader import criterio_quant
from trader.papel import julgamento
from trader.papel.dados import CARREGADORES, DadoAindaNaoSaiuError
from trader.papel.registro import (
    BRASILIA,
    MOTIVO_DA_FALTA_PULADA,
    PASTA_PADRAO,
    RegistroDoPapel,
    abre_em,
    prazo,
    vespera,
)
from trader.papel.series import SERIES, Serie

NOME_DA_TRAVA = ".gravando"
# rodada que morreu no meio não trava o papel para sempre
TRAVA_ESQUECIDA = timedelta(hours=1)

Carregador = Callable[[date, date], object]


@dataclass(frozen=True)
class Situacao:
    serie: str
    dia: str
    o_que: str  # gravado | falta | cedo | esperando | sem início

    def __str__(self) -> str:
        return f"{self.serie}: {self.dia} {self.o_que}"


def agora_em_brasilia() -> datetime:
    return datetime.now(BRASILIA)


def gravar_serie(
    registro: RegistroDoPapel,
    serie: Serie,
    carregar: Carregador,
    relogio: Callable[[], datetime] = agora_em_brasilia,
) -> list[Situacao]:
    """Leva a série até o dia de hoje: faltas vencidas, depois o dia aberto (se o dado saiu)."""
    inicio = registro.inicio()
    if inicio is None:
        return [Situacao(serie.nome, "-", "sem início")]
    primeiro_fechamento = vespera(inicio, serie.mercado)
    situacoes = []
    while True:
        dia = registro.proximo_dia(serie.nome, serie.mercado)
        assert dia is not None  # há início
        agora = relogio()
        if agora >= prazo(dia, serie.mercado):
            registro.registrar_falta(
                serie.nome, serie.mercado, dia, MOTIVO_DA_FALTA_PULADA, agora
            )
            situacoes.append(Situacao(serie.nome, dia.isoformat(), "falta"))
            continue
        if agora < abre_em(dia, serie.mercado):
            return situacoes + [Situacao(serie.nome, dia.isoformat(), "cedo")]
        fechamento = vespera(dia, serie.mercado)
        try:
            foto = serie.fotografar(
                carregar(fechamento, primeiro_fechamento),
                fechamento,
                primeiro_fechamento,
            )
        except DadoAindaNaoSaiuError:
            return situacoes + [Situacao(serie.nome, dia.isoformat(), "esperando")]
        registro.gravar(serie.nome, serie.mercado, dia, foto, relogio())
        situacoes.append(Situacao(serie.nome, dia.isoformat(), "gravado"))


def gravar_pendentes(
    registro: RegistroDoPapel,
    series: Iterable[Serie] = SERIES,
    carregadores: dict[str, Carregador] | None = None,
    relogio: Callable[[], datetime] = agora_em_brasilia,
) -> list[Situacao]:
    """Uma rodada em todas as séries, com o pré-registro conferido e uma rodada por vez."""
    criterio_quant.conferir()
    carregadores = carregadores if carregadores is not None else dict(CARREGADORES)
    with _trava(registro.pasta, relogio()):
        situacoes = []
        for serie in series:
            situacoes += gravar_serie(
                registro, serie, carregadores[serie.nome], relogio
            )
        return situacoes


class RodadaEmAndamentoError(RuntimeError):
    """Outra rodada do gravador está escrevendo agora."""


@contextmanager
def _trava(pasta: Path, agora: datetime) -> Iterator[None]:
    """Arquivo criado com exclusividade: duas rodadas agendadas nunca escrevem juntas."""
    arquivo = pasta / NOME_DA_TRAVA
    pasta.mkdir(parents=True, exist_ok=True)
    if arquivo.exists():
        criada = datetime.fromisoformat(arquivo.read_text(encoding="utf-8"))
        if agora - criada < TRAVA_ESQUECIDA:
            raise RodadaEmAndamentoError(
                f"outra rodada começou em {criada.isoformat()}"
            )
        arquivo.unlink()
    descritor = os.open(arquivo, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(descritor, "w", encoding="utf-8") as saida:
        saida.write(agora.isoformat())
    try:
        yield
    finally:
        arquivo.unlink(missing_ok=True)


# --- linha de comando ----------------------------------------------------------------------------


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    leitor = argparse.ArgumentParser(
        description="Grava o que está pendente no papel da v0.2."
    )
    leitor.add_argument("--pasta", type=Path, default=PASTA_PADRAO)
    acao = leitor.add_mutually_exclusive_group()
    acao.add_argument("--iniciar", type=date.fromisoformat, metavar="DATA_DO_MERGE")
    acao.add_argument("--verificar", action="store_true")
    acao.add_argument("--julgar", action="store_true")
    leitor.add_argument(
        "--commit", default="", help="o commit da main com o gravador (com --iniciar)"
    )
    return leitor.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    registro = RegistroDoPapel(args.pasta)
    if args.iniciar:
        if not args.commit:
            raise SystemExit("--iniciar pede o --commit do merge")
        criterio_quant.conferir()
        conteudo = registro.fixar_inicio(args.iniciar, args.commit, agora_em_brasilia())
        print(f"início do papel: {conteudo['inicio']}")
        return 0
    if args.verificar:
        for nome in registro.series():
            registro.verificar(nome)
            print(f"{nome}: {len(registro.linhas(nome))} linhas, cadeia confere")
        return 0
    if args.julgar:
        hoje = agora_em_brasilia().date()
        for serie in SERIES:
            print(
                json.dumps(julgamento.julgar(registro, serie, hoje), ensure_ascii=False)
            )
        return 0
    for situacao in gravar_pendentes(registro):
        print(f"{agora_em_brasilia():%Y-%m-%d %H:%M} {situacao}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
