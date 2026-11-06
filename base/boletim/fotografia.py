"""Fotografia da base: o retrato dos manifestos de um dia, para dizer o que mudou desde o anterior.

Só lê os manifestos (`base/parquet.py`) e o tamanho dos arquivos: nenhuma tabela é aberta. Cada
tabela é um Parquet atual (sem as versões guardadas `.vN`), identificado pelo caminho relativo à
raiz da base sem a extensão (`cda/2026`). A fotografia é um JSON pequeno guardado por dia; a do dia
seguinte é comparada com a última que houver (dia pulado ou primeiro dia não quebram nada).
"""

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from base.parquet import VERSAO_GUARDADA, gravar_atomico

FORMATO = "tickerlab-fotografia-da-base-v1"


def _contrato(manifesto: dict[str, Any]) -> tuple[str | None, int]:
    conferencia = manifesto.get("conferencia_do_contrato")
    if not isinstance(conferencia, dict):
        return None, 0
    problemas = len(conferencia.get("problemas") or []) + int(
        conferencia.get("problemas_a_mais") or 0
    )
    return ("aprovada" if conferencia.get("aprovada") else "com_problemas"), problemas


def _licenca(manifesto: dict[str, Any]) -> str | None:
    licenca = manifesto.get("licenca")
    return licenca.get("marca") if isinstance(licenca, dict) else None


def _retrato_da_tabela(arquivo: Path) -> dict[str, Any]:
    caminho_do_manifesto = arquivo.with_suffix(".json")
    try:
        manifesto = json.loads(caminho_do_manifesto.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifesto = {}
    contrato, problemas = _contrato(manifesto)
    guardadas = sum(
        1 for outro in arquivo.parent.glob(f"{arquivo.stem}.v*.parquet")
        if VERSAO_GUARDADA.search(outro.stem)
    )  # fmt: skip
    return {
        "linhas": manifesto.get("linhas"),
        "sha256": manifesto.get("sha256_da_tabela"),
        "bytes": arquivo.stat().st_size,
        "versoes_guardadas": guardadas,
        "licenca": _licenca(manifesto),
        "contrato": contrato,
        "problemas_do_contrato": problemas,
        "versao_do_codigo": manifesto.get("versao_do_codigo"),
    }


def fotografar(raiz: Path) -> dict[str, Any]:
    """O retrato de todas as tabelas atuais debaixo de `raiz` (a pasta `base/` do acervo)."""
    tabelas = {}
    for arquivo in sorted(raiz.rglob("*.parquet")):
        if VERSAO_GUARDADA.search(arquivo.stem):
            continue
        nome = arquivo.relative_to(raiz).with_suffix("").as_posix()
        tabelas[nome] = _retrato_da_tabela(arquivo)
    return {"formato": FORMATO, "tabelas": tabelas}


def por_grupo(foto: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Tabelas, linhas e bytes por pasta de cima (`cda`, `fidc`, `rede`...)."""
    grupos: dict[str, dict[str, int]] = {}
    for nome, t in foto["tabelas"].items():
        g = grupos.setdefault(
            nome.split("/")[0], {"tabelas": 0, "linhas": 0, "bytes": 0}
        )
        g["tabelas"] += 1
        g["linhas"] += t["linhas"] or 0
        g["bytes"] += t["bytes"]
    return grupos


@dataclass(frozen=True)
class Mudanca:
    tabela: str
    linhas_antes: int | None
    linhas_agora: int | None
    versoes_novas: int


@dataclass(frozen=True)
class Diferencas:
    primeira: bool  # não havia fotografia anterior
    novas: list[str] = field(default_factory=list)
    sumidas: list[str] = field(default_factory=list)
    mudaram: list[Mudanca] = field(default_factory=list)  # conteúdo (hash) diferente
    linhas_antes: int = 0
    linhas_agora: int = 0
    bytes_antes: int = 0
    bytes_agora: int = 0


def _total(foto: dict[str, Any], campo: str) -> int:
    return sum(t[campo] or 0 for t in foto["tabelas"].values())


def comparar(antes: dict[str, Any] | None, agora: dict[str, Any]) -> Diferencas:
    linhas_agora, bytes_agora = _total(agora, "linhas"), _total(agora, "bytes")
    if antes is None:
        return Diferencas(True, linhas_agora=linhas_agora, bytes_agora=bytes_agora)
    a, b = antes["tabelas"], agora["tabelas"]
    mudaram = [
        Mudanca(
            nome,
            a[nome]["linhas"],
            b[nome]["linhas"],
            max(0, b[nome]["versoes_guardadas"] - a[nome]["versoes_guardadas"]),
        )
        for nome in sorted(a.keys() & b.keys())
        if a[nome]["sha256"] != b[nome]["sha256"]
    ]
    return Diferencas(
        False,
        novas=sorted(b.keys() - a.keys()),
        sumidas=sorted(a.keys() - b.keys()),
        mudaram=mudaram,
        linhas_antes=_total(antes, "linhas"),
        linhas_agora=linhas_agora,
        bytes_antes=_total(antes, "bytes"),
        bytes_agora=bytes_agora,
    )


def guardar(foto: dict[str, Any], pasta: Path, dia: date) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{dia.isoformat()}.json"
    texto = json.dumps(foto, ensure_ascii=False, indent=1)
    gravar_atomico(
        destino, lambda caminho: Path(caminho).write_text(texto, encoding="utf-8")
    )
    return destino


def ultima_antes(pasta: Path, dia: date) -> tuple[date, dict[str, Any]] | None:
    """A fotografia mais nova de um dia anterior a `dia` (None se não houver)."""
    dias = []
    for arquivo in pasta.glob("????-??-??.json") if pasta.is_dir() else []:
        try:
            d = date.fromisoformat(arquivo.stem)
        except ValueError:
            continue
        if d < dia:
            dias.append((d, arquivo))
    if not dias:
        return None
    d, arquivo = max(dias)
    return d, json.loads(arquivo.read_text(encoding="utf-8"))
