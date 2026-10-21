"""Estado de cada tarefa dos servidores: as marcas do `rodar-tarefa.sh` contra a agenda (painel das coletas).

O `rodar-tarefa.sh` grava `~/estado-tarefas/NOME.ok` no sucesso (e apaga o `.falha`) ou `NOME.falha`
na falha. Uma tarefa que parou de rodar não grava nada; por isso o estado compara o último sucesso
com o prazo da agenda, e não só olha se há falha.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from src.agenda_das_tarefas import TarefaAgendada

Situacao = Literal["ok", "falhou", "atrasada", "nunca_rodou", "fora_da_agenda"]
SEGUNDOS_POR_HORA = 3600


@dataclass(frozen=True)
class Marca:
    """As marcas de uma tarefa: hora do último `.ok` e do `.falha`, quando existem."""

    ok_em: datetime | None = None
    falha_em: datetime | None = None


@dataclass(frozen=True)
class EstadoDaTarefa:
    """Situação de uma tarefa agora, com o último sucesso, a última falha e quando o sucesso vence."""

    nome: str
    situacao: Situacao
    ultimo_ok: datetime | None
    ultima_falha: datetime | None
    vence_em: datetime | None
    prazo: timedelta | None

    def como_dicionario(self) -> dict[str, str | float | None]:
        """Devolve o estado em tipos simples (datas em ISO 8601), pronto para virar JSON."""
        return {
            "nome": self.nome,
            "situacao": self.situacao,
            "ultimo_ok": _iso(self.ultimo_ok),
            "ultima_falha": _iso(self.ultima_falha),
            "vence_em": _iso(self.vence_em),
            "prazo_em_horas": self.prazo.total_seconds() / SEGUNDOS_POR_HORA
            if self.prazo
            else None,
        }


def estado_das_tarefas(
    agenda: list[TarefaAgendada], marcas: dict[str, Marca], agora: datetime
) -> list[EstadoDaTarefa]:
    """Devolve o estado de cada tarefa da agenda e, no fim, das marcas que não estão mais nela.

    `agora` e as horas das marcas precisam ter fuso (o `rodar-tarefa.sh` grava `date -Is`).
    O sucesso vale até `ultimo_ok + prazo`, inclusive.
    """
    estados = [
        _estado(tarefa, marcas.get(tarefa.nome, Marca()), agora) for tarefa in agenda
    ]
    agendadas = {tarefa.nome for tarefa in agenda}
    for nome in sorted(set(marcas) - agendadas):
        marca = marcas[nome]
        estados.append(
            EstadoDaTarefa(
                nome, "fora_da_agenda", marca.ok_em, marca.falha_em, None, None
            )
        )
    return estados


def _estado(tarefa: TarefaAgendada, marca: Marca, agora: datetime) -> EstadoDaTarefa:
    vence_em = marca.ok_em + tarefa.prazo if marca.ok_em else None
    return EstadoDaTarefa(
        tarefa.nome,
        _situacao(marca, vence_em, agora),
        marca.ok_em,
        marca.falha_em,
        vence_em,
        tarefa.prazo,
    )


def _situacao(marca: Marca, vence_em: datetime | None, agora: datetime) -> Situacao:
    falhou_por_ultimo = marca.falha_em is not None and (
        marca.ok_em is None or marca.falha_em >= marca.ok_em
    )
    if falhou_por_ultimo:
        return "falhou"
    if vence_em is None:
        return "nunca_rodou"
    return "ok" if agora <= vence_em else "atrasada"


def _iso(momento: datetime | None) -> str | None:
    return momento.isoformat() if momento else None
