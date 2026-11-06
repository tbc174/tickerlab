"""Validade das ligações e cadeia de controle (B-03 do backlog do dossiê da plataforma; ADR 0077).

**Validade.** O `valido_de`/`valido_ate` da B-03 já são colunas de `ligacoes`, sem coluna nova:
`aconteceu_em` é o início (o FRE de referência D mostra a ligação valendo em D) e `ate` é o fim, sem
incluir o dia (D17: participação que muda fecha um período e abre outro). O que faltava era a pergunta
com duas datas: **o que valia no dia D, sabendo o que se sabia no dia K** (`conhecido_em`):

- conhecida em K: `publico_em ≤ K`;
- começou até D: `aconteceu_em ≤ D` (sem ele, vale o `publico_em`);
- não tinha acabado em D, pelo que se sabia em K: o `ate` só conta se `ate_publico_em ≤ K`.

Com K = D (o padrão) é o "como era em D" da porta, sem olhar o futuro, menos o que ainda não tinha
começado. Com K depois de D (hoje, por exemplo) é "quem controlava em D, pelo que se sabe agora": o
FRE de referência D só é entregue meses depois, e é com ele que a resposta deve bater. K antes de D
é erro (seria saber de um dia que ainda não chegou).

**Cadeia de controle.** Só `controlada_de` (coligada e participada não são controle): da entidade a
quem a controla, e assim por diante, até a controladora final (quem não é controlada de ninguém
naquele grafo). O grafo é um `networkx.DiGraph` (BSD-3; dossiê da plataforma, `ADOPT`), aresta
controlada → controladora. Duas controladoras ao mesmo tempo (acordo de acionistas, cadastro errado)
param a cadeia como `ambigua`, com as candidatas: o código não escolhe. Volta a uma entidade já vista
(participação cruzada mal informada) para como `ciclo`.

**Limite:** "final" quer dizer final **na base**. O FRE só mostra as controladas de quem é companhia
aberta; acima dela (holding fechada, fundo, pessoa) a base ainda não vê, até os acionistas do FRE
(série T, PR T3).
"""

from collections.abc import Iterable
from dataclasses import dataclass

import networkx as nx
import pandas as pd

CONTROLADA_DE = "controlada_de"
FINAL, AMBIGUA, CICLO = "final", "ambigua", "ciclo"


@dataclass(frozen=True)
class Cadeia:
    """Da entidade à controladora final, em tipos simples (vira JSON como está)."""

    entidade: str
    dia: str  # em que dia valia (ISO)
    conhecido_em: str  # sabendo o que se sabia neste dia (ISO)
    caminho: tuple[str, ...]  # da entidade até onde a cadeia chegou, inclusive
    participacoes: tuple[
        float | None, ...
    ]  # a % de cada elo do caminho (o FRE informa)
    final: str | None  # vazia se a cadeia parou (ambígua ou ciclo)
    situacao: str  # final, ambigua ou ciclo
    candidatas: tuple[str, ...] = ()  # na ambígua, as controladoras do último elo


def _dias(dia: object, conhecido_em: object) -> tuple[pd.Timestamp, pd.Timestamp]:
    dia_ = pd.Timestamp(dia).normalize()  # type: ignore[arg-type]
    sabido = (
        dia_ if conhecido_em is None else pd.Timestamp(conhecido_em).normalize()  # type: ignore[arg-type]
    )
    if sabido < dia_:
        raise ValueError(
            f"conhecido_em {sabido.date()} antes do dia {dia_.date()}: não dá para saber "
            "de um dia que ainda não chegou"
        )
    return dia_, sabido


def valiam_em(
    ligacoes: pd.DataFrame, dia: object, conhecido_em: object = None
) -> pd.DataFrame:
    """As ligações que valiam no `dia`, pelo que se sabia em `conhecido_em` (padrão: o próprio dia).

    O fim que só ficou público depois de `conhecido_em` não aparece (`ate` e `ate_publico_em`
    vazios nas linhas devolvidas), como na porta.
    """
    dia_, sabido = _dias(dia, conhecido_em)
    inicio = ligacoes["aconteceu_em"].fillna(ligacoes["publico_em"])
    fim_sabido = ligacoes["ate_publico_em"] <= sabido
    fim = ligacoes["ate"].where(fim_sabido)
    valia = (
        (ligacoes["publico_em"] <= sabido)
        & (inicio <= dia_)
        & (fim.isna() | (fim > dia_))
    )
    resultado = ligacoes[valia].copy()
    resultado.loc[~fim_sabido[valia], ["ate", "ate_publico_em"]] = pd.NaT
    return resultado


def grafo_de_controle(
    ligacoes: pd.DataFrame, dia: object, conhecido_em: object = None
) -> nx.DiGraph:
    """Controlada → controladora, com o que valia no dia (aresta com `participacao` e `fonte`)."""
    valiam = valiam_em(ligacoes, dia, conhecido_em)
    controle = valiam[valiam["tipo"] == CONTROLADA_DE]
    grafo = nx.DiGraph()
    for de, para, participacao, fonte in controle[
        ["de", "para", "participacao", "fonte"]
    ].itertuples(index=False):
        grafo.add_edge(
            de,
            para,
            participacao=None if pd.isna(participacao) else float(participacao),
            fonte=fonte,
        )
    return grafo


def _subir(
    grafo: nx.DiGraph, entidade: str
) -> tuple[list[str], list[float | None], str, tuple[str, ...]]:
    """Sobe a cadeia: (caminho, participações, situação, candidatas)."""
    caminho, participacoes = [entidade], []
    atual = entidade
    while True:
        acima = sorted(grafo.successors(atual)) if atual in grafo else []
        if not acima:
            return caminho, participacoes, FINAL, ()
        if len(acima) > 1:
            return caminho, participacoes, AMBIGUA, tuple(acima)
        proxima = acima[0]
        if proxima in caminho:
            return caminho, participacoes, CICLO, ()
        participacoes.append(grafo.edges[atual, proxima]["participacao"])
        caminho.append(proxima)
        atual = proxima


def _cadeia(
    grafo: nx.DiGraph, entidade: str, dia: pd.Timestamp, sabido: pd.Timestamp
) -> Cadeia:
    caminho, participacoes, situacao, candidatas = _subir(grafo, entidade)
    return Cadeia(
        entidade=entidade,
        dia=dia.date().isoformat(),
        conhecido_em=sabido.date().isoformat(),
        caminho=tuple(caminho),
        participacoes=tuple(participacoes),
        final=caminho[-1] if situacao == FINAL else None,
        situacao=situacao,
        candidatas=candidatas,
    )


def cadeia_de_controle(
    ligacoes: pd.DataFrame, entidade: str, dia: object, conhecido_em: object = None
) -> Cadeia:
    """A cadeia da entidade até a controladora final no dia (pelo que se sabia em `conhecido_em`)."""
    dia_, sabido = _dias(dia, conhecido_em)
    return _cadeia(grafo_de_controle(ligacoes, dia_, sabido), entidade, dia_, sabido)


def controladoras_finais(
    ligacoes: pd.DataFrame,
    entidades: Iterable[str],
    dia: object,
    conhecido_em: object = None,
) -> pd.DataFrame:
    """Uma linha por entidade: `entidade`, `final`, `situacao` e `saltos` (o grafo é montado uma vez)."""
    dia_, sabido = _dias(dia, conhecido_em)
    grafo = grafo_de_controle(ligacoes, dia_, sabido)
    cadeias = [_cadeia(grafo, e, dia_, sabido) for e in entidades]
    return pd.DataFrame(
        {
            "entidade": [c.entidade for c in cadeias],
            "final": [c.final for c in cadeias],
            "situacao": [c.situacao for c in cadeias],
            "saltos": [len(c.caminho) - 1 for c in cadeias],
        }
    )


def grupo_de_controle(
    ligacoes: pd.DataFrame, entidade: str, dia: object, conhecido_em: object = None
) -> set[str]:
    """A controladora final da entidade e tudo o que ela controla, direta ou indiretamente, no dia.

    Cadeia parada (ambígua ou ciclo): só o caminho até onde ela chegou.
    """
    dia_, sabido = _dias(dia, conhecido_em)
    grafo = grafo_de_controle(ligacoes, dia_, sabido)
    cadeia = _cadeia(grafo, entidade, dia_, sabido)
    if cadeia.final is None:
        return set(cadeia.caminho)
    abaixo = nx.ancestors(grafo, cadeia.final) if cadeia.final in grafo else set()
    return {cadeia.final, *abaixo}
