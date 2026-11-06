"""Frescor das fontes: chegou dado novo de cada fonte dentro do prazo? (painel das coletas, PR 3)

O vigia das tarefas (`src/estado_das_tarefas.py`) diz se a tarefa rodou; este módulo diz se ela
trouxe dado. Uma tarefa pode sair com 0 sem baixar nada: a fonte mudou o endereço e o coletor só
registrou "nao_encontrado". Aqui vale a última coleta "ok" de cada fonte na tabela `coletas`, que só
tem dado público (nenhum dado de usuário).

O prazo segue a mesma regra das tarefas (`prazo_do_periodo`): a frequência esperada mais a folga.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import sqlalchemy as sa

from src.agenda_das_tarefas import prazo_do_periodo
from src.banco.modelo import coletas

SituacaoDaFonte = Literal["fresca", "velha", "nunca", "sem_prazo"]
SEGUNDOS_POR_HORA = 3600
DIARIA = timedelta(days=1)

# a frequência com que cada fonte traz dado novo; a fonte que não está aqui aparece "sem_prazo"
# (visível no painel, sem ficar vermelha). As diárias são as dos coletores das 7h na VPS
# (crontab: eventos-cvm, fundamentos-cvm, eventos-sec, negociacoes-cvm, fundos-cvm, fundos-sec).
FREQUENCIAS_DAS_FONTES: dict[str, timedelta] = {
    "cvm-eventos": DIARIA,
    "cvm-dfp-itr": DIARIA,
    "sec-eventos": DIARIA,
    "cvm-vlmo": DIARIA,
    "cvm-cda": DIARIA,
    "sec-13f": DIARIA,
}


@dataclass(frozen=True)
class FrescorDaFonte:
    """A situação de uma fonte: a última coleta "ok", a última tentativa e quando o dado vence."""

    fonte: str
    situacao: SituacaoDaFonte
    ultima_ok: datetime | None
    ultima_tentativa: datetime | None
    vence_em: datetime | None
    prazo: timedelta | None

    def como_dicionario(self) -> dict[str, str | float | None]:
        """Devolve o frescor em tipos simples (datas em ISO, prazo em horas), pronto para virar JSON."""
        return {
            "fonte": self.fonte,
            "situacao": self.situacao,
            "ultima_ok": _iso(self.ultima_ok),
            "ultima_tentativa": _iso(self.ultima_tentativa),
            "vence_em": _iso(self.vence_em),
            "prazo_em_horas": (
                self.prazo.total_seconds() / SEGUNDOS_POR_HORA if self.prazo else None
            ),
        }


def frescor_das_fontes(
    conexao: sa.Connection, frequencias: dict[str, timedelta], agora: datetime
) -> list[FrescorDaFonte]:
    """Devolve o frescor de cada fonte com coleta registrada ou com frequência esperada, por nome.

    Lê só a tabela `coletas`: a última coleta "ok" e a última tentativa (qualquer situação) de cada fonte.
    """
    momentos = _momentos_por_fonte(conexao)
    fontes = sorted(set(momentos) | set(frequencias))
    return [
        _frescor(
            fonte, *momentos.get(fonte, (None, None)), frequencias.get(fonte), agora
        )
        for fonte in fontes
    ]


def _momentos_por_fonte(
    conexao: sa.Connection,
) -> dict[str, tuple[datetime | None, datetime | None]]:
    ultima_ok = sa.func.max(sa.case((coletas.c.situacao == "ok", coletas.c.baixado_em)))
    linhas = conexao.execute(
        sa.select(
            coletas.c.fonte, ultima_ok, sa.func.max(coletas.c.baixado_em)
        ).group_by(coletas.c.fonte)
    ).all()
    return {
        fonte: (_com_fuso(ok), _com_fuso(tentativa)) for fonte, ok, tentativa in linhas
    }


def _frescor(
    fonte: str,
    ultima_ok: datetime | None,
    ultima_tentativa: datetime | None,
    frequencia: timedelta | None,
    agora: datetime,
) -> FrescorDaFonte:
    prazo = prazo_do_periodo(frequencia) if frequencia else None
    vence_em = ultima_ok + prazo if ultima_ok and prazo else None
    situacao: SituacaoDaFonte
    if prazo is None:
        situacao = "sem_prazo"
    elif vence_em is None:
        situacao = "nunca"
    else:
        situacao = "fresca" if agora <= vence_em else "velha"
    return FrescorDaFonte(fonte, situacao, ultima_ok, ultima_tentativa, vence_em, prazo)


def _com_fuso(momento: datetime | str | None) -> datetime | None:
    # o SQLite devolve o máximo como texto e sem fuso: foi gravado em UTC
    if momento is None:
        return None
    if isinstance(momento, str):
        momento = datetime.fromisoformat(momento)
    return momento if momento.tzinfo else momento.replace(tzinfo=UTC)


def _iso(momento: datetime | None) -> str | None:
    return momento.isoformat() if momento else None
