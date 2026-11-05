"""O dia de evento do pregão (plano `2026-10-28-raio-x-todo-dia`, PR 4c; linha 444 da fila).

Um pregão é dia de evento quando nele cai o efeito de uma data marcada pela fonte oficial (decisão do
Copom e do Fed, IPCA, emprego nos EUA) ou quando o Ibovespa anda `VARIACAO_FORTE_DO_IBOVESPA` ou mais.
Em dia de evento o Raio-X completo sai como rascunho, esperando o "pode" do Tiago; o relatório curto
do dia sai como sempre.

O calendário (`conteudo/calendario_de_eventos.csv`) tem só as datas que a fonte de cada evento já
publicou, com o endereço dela; quando a fonte publica o ano seguinte, as linhas novas entram por PR.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

CAMINHO_DO_CALENDARIO = (
    Path(__file__).resolve().parent.parent / "conteudo" / "calendario_de_eventos.csv"
)
# O comunicado sai antes de a B3 fechar (o IPCA às 9h, o Fed às 14h de Washington): o efeito é no
# pregão do mesmo dia.
ANTES_DO_FECHAMENTO = "antes_do_fechamento"
# O comunicado sai com a B3 fechada (o Copom, a partir das 18h30) ou num dia sem pregão: o efeito é
# no pregão seguinte.
DEPOIS_DO_FECHAMENTO = "depois_do_fechamento"
MOMENTOS = (ANTES_DO_FECHAMENTO, DEPOIS_DO_FECHAMENTO)
# Alta ou queda do Ibovespa que faz do pregão um dia de evento. Medido na série da B3: 435 de 6.648
# pregões desde 2000 e 9 de 706 desde 2024 (o mais recente, o circuit breaker de 26/10/2026).
VARIACAO_FORTE_DO_IBOVESPA = 0.03


@dataclass(frozen=True)
class EventoMarcado:
    """Uma linha do calendário: quando, o quê, se o efeito é no mesmo pregão e a fonte oficial."""

    data: date
    evento: str
    momento: str
    fonte: str


def ler_calendario(caminho: Path | None = None) -> list[EventoMarcado]:
    """As datas marcadas (as do repositório, sem `caminho`). Levanta `ValueError` se uma linha tiver
    data ou momento que não existe."""
    tabela = pd.read_csv(caminho or CAMINHO_DO_CALENDARIO, comment="#", dtype=str)
    eventos = [
        EventoMarcado(date.fromisoformat(data), evento, momento, fonte)
        for data, evento, momento, fonte in tabela[
            ["data", "evento", "momento", "fonte"]
        ].itertuples(index=False)
    ]
    desconhecidos = {e.momento for e in eventos} - set(MOMENTOS)
    if desconhecidos:
        raise ValueError(f"momento desconhecido no calendário: {sorted(desconhecidos)}")
    return eventos


def eventos_do_pregao(
    dia: date, vespera: date, calendario: list[EventoMarcado]
) -> list[EventoMarcado]:
    """As datas marcadas cujo efeito cai no pregão `dia` (`vespera`: o pregão anterior a ele)."""
    return [
        e
        for e in calendario
        if (e.momento == ANTES_DO_FECHAMENTO and e.data == dia)
        or (e.momento == DEPOIS_DO_FECHAMENTO and vespera <= e.data < dia)
    ]


def motivo_do_evento(
    dia: date,
    vespera: date,
    variacao_do_ibovespa: float,
    calendario: list[EventoMarcado],
) -> dict[str, object] | None:
    """Por que o pregão é dia de evento, em tipos simples; None num dia comum."""
    marcados = eventos_do_pregao(dia, vespera, calendario)
    forte = abs(variacao_do_ibovespa) >= VARIACAO_FORTE_DO_IBOVESPA
    if not marcados and not forte:
        return None
    return {
        "calendario": [
            {"evento": e.evento, "data": e.data.isoformat(), "fonte": e.fonte}
            for e in marcados
        ],
        "variacao_forte_do_ibovespa": forte,
        "variacao_minima": VARIACAO_FORTE_DO_IBOVESPA,
    }
