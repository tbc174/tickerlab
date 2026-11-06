"""Leitura do robots.txt com os curingas `*` e `$` (o `RobotFileParser` do Python não os entende).

Vale a regra do Google (RFC 9309): entre as regras `Allow` e `Disallow` do grupo que cita o nosso
agente (ou, na falta, o `*`), ganha a de padrão mais longo; em empate, a `Allow`.
"""

import re

from base.arquivo.agente import AGENTE

_NOME_DO_AGENTE = AGENTE.split(" ", 1)[0].lower()


def _padrao(regra: str) -> re.Pattern[str]:
    ancorado = regra.endswith("$")
    corpo = re.escape(regra.removesuffix("$")).replace(r"\*", ".*")
    return re.compile(corpo + ("$" if ancorado else ""))


def _regras_do_grupo(robots: str) -> list[tuple[str, str]]:
    """As regras (`allow`/`disallow`, caminho) do grupo do nosso agente, ou do `*`."""
    grupos: dict[str, list[tuple[str, str]]] = {}
    agentes: list[str] = []
    ultima_foi_agente = False
    for linha in robots.splitlines():
        campo, _, valor = linha.split("#", 1)[0].partition(":")
        campo, valor = campo.strip().lower(), valor.strip()
        if campo == "user-agent":
            if not ultima_foi_agente:
                agentes = []
            agentes.append(valor.lower())
            grupos.setdefault(valor.lower(), [])
            ultima_foi_agente = True
            continue
        ultima_foi_agente = False
        if campo in ("allow", "disallow", "crawl-delay") and valor:
            for agente in agentes:
                grupos[agente].append((campo, valor))
    return grupos.get(_NOME_DO_AGENTE) or grupos.get("*") or []


def pode_buscar(robots: str, caminho: str) -> bool:
    """O robots.txt deixa o TickerLab buscar `caminho` (com a query, sem o domínio)?"""
    vencedora = ("allow", "")
    for tipo, regra in _regras_do_grupo(robots):
        if tipo == "crawl-delay":
            continue
        if _padrao(regra).match(caminho) and (
            len(regra) > len(vencedora[1])
            or (len(regra) == len(vencedora[1]) and tipo == "allow")
        ):
            vencedora = (tipo, regra)
    return vencedora[0] == "allow"


def pausa_pedida(robots: str) -> float | None:
    """O `Crawl-delay` (segundos entre pedidos) que o robots.txt pede ao nosso agente, ou None."""
    for tipo, valor in _regras_do_grupo(robots):
        if tipo == "crawl-delay":
            try:
                return max(float(valor), 0.0)
            except ValueError:
                return None
    return None
