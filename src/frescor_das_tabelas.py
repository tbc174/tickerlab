"""Frescor de cada tabela do conector: o dado da tabela chegou dentro do prazo? (foco "base em dia", parte 2)

`src/frescor_das_fontes.py` diz isso por fonte, e só das seis que alguém escreveu à mão. Aqui o frescor
sai de **toda** tabela consultável: o mapa tabela -> fontes (`src/fontes_das_tabelas.py`) diz de onde ela
vem, a frequência é a que o catálogo já declara, e a data é a da última coleta "ok" no registro de coletas.

A tabela vale pela fonte **mais atrasada** que a alimenta: se uma das fontes parou, a tabela está
atrasada, mesmo que as outras estejam em dia. O resultado diz qual fonte é, para quem for consertar.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import sqlalchemy as sa

from base import dossie as regras
from base.dicionario import TABELAS
from base.vitrine import SEM_CALENDARIO, frequencia_do_site
from src.agenda_das_tarefas import prazo_do_periodo
from src.fontes_das_tabelas import fontes_da_tabela
from src.frescor_das_fontes import frescor_das_fontes

SituacaoDaTabela = Literal["fresca", "velha", "nunca", "sem_prazo", "sem_fonte"]
SITUACOES_DA_TABELA: tuple[str, ...] = (
    "fresca",
    "velha",
    "nunca",
    "sem_prazo",
    "sem_fonte",
)

# o período de cada rótulo do catálogo (o mês e o ano com folga de um dia, como nas tarefas)
PERIODOS_DOS_ROTULOS: dict[str, timedelta] = {
    "Diária": timedelta(days=1),
    "Semanal": timedelta(days=7),
    "Mensal": timedelta(days=31),
    "Trimestral": timedelta(days=92),
    "Anual": timedelta(days=366),
}


@dataclass(frozen=True)
class FrescorDaTabela:
    """A situação de uma tabela: a coleta "ok" da fonte mais atrasada e quando o dado vence."""

    tabela: str
    situacao: SituacaoDaTabela
    frequencia: str
    fontes: tuple[str, ...]
    fonte_mais_atrasada: str | None
    ultima_ok: datetime | None
    vence_em: datetime | None

    def como_dicionario(self) -> dict[str, str | list[str] | None]:
        """Devolve o frescor em tipos simples (datas em ISO), pronto para virar JSON."""
        return {
            "tabela": self.tabela,
            "situacao": self.situacao,
            "frequencia": self.frequencia,
            "fontes": list(self.fontes),
            "fonte_mais_atrasada": self.fonte_mais_atrasada,
            "ultima_ok": self.ultima_ok.isoformat() if self.ultima_ok else None,
            "vence_em": self.vence_em.isoformat() if self.vence_em else None,
        }


def periodo_do_rotulo(rotulo: str) -> timedelta | None:
    """O período de um rótulo de frequência do catálogo; None para "Sem calendário fixo"."""
    return PERIODOS_DOS_ROTULOS.get(rotulo)


def frequencias_do_conector() -> dict[str, str]:
    """O rótulo de frequência de cada tabela consultável, do mesmo catálogo que a API mostra."""
    return {
        nome: frequencia_do_site(tabela.frequencia)
        for nome, tabela in TABELAS.items()
        if regras.pode_consultar(nome)
    }


def frescor_das_tabelas(
    conexao: sa.Connection,
    tabelas: dict[str, str],
    agora: datetime,
    fontes_de: Callable[[str], tuple[str, ...] | None] = fontes_da_tabela,
) -> list[FrescorDaTabela]:
    """O frescor de cada tabela de `tabelas` (nome -> rótulo de frequência), em ordem de nome.

    Lê só a tabela `coletas`, uma vez: a última coleta "ok" de cada fonte.
    """
    ultimas_ok = {f.fonte: f.ultima_ok for f in frescor_das_fontes(conexao, {}, agora)}
    return [
        _frescor(nome, rotulo, tuple(fontes_de(nome) or ()), ultimas_ok, agora)
        for nome, rotulo in sorted(tabelas.items())
    ]


def _frescor(
    tabela: str,
    rotulo: str,
    fontes: tuple[str, ...],
    ultimas_ok: dict[str, datetime | None],
    agora: datetime,
) -> FrescorDaTabela:
    if not fontes:
        return FrescorDaTabela(tabela, "sem_fonte", rotulo, (), None, None, None)
    # a mais atrasada: a que nunca trouxe dado vem antes, depois a de coleta "ok" mais antiga
    mais_atrasada = min(
        fontes,
        key=lambda fonte: (
            ultimas_ok.get(fonte) or datetime.min.replace(tzinfo=agora.tzinfo)
        ),
    )
    ultima_ok = ultimas_ok.get(mais_atrasada)
    periodo = periodo_do_rotulo(rotulo) if rotulo != SEM_CALENDARIO else None
    vence_em = ultima_ok + prazo_do_periodo(periodo) if ultima_ok and periodo else None
    situacao: SituacaoDaTabela
    if ultima_ok is None:
        situacao = "nunca" if periodo else "sem_prazo"
    elif vence_em is None:
        situacao = "sem_prazo"
    else:
        situacao = "fresca" if agora <= vence_em else "velha"
    return FrescorDaTabela(
        tabela, situacao, rotulo, fontes, mais_atrasada, ultima_ok, vence_em
    )
