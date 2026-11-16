"""Todo `scripts/*.py` diz quem o roda (casa em ordem, 05/11/2026; fila 701).

A docstring do módulo termina com uma linha "Roda: ..." dizendo por onde o script é chamado: cron do VPS,
cron de casa, CI, hook, outro script, app, Docker, migração ou manual (com o comando). Assim ninguém
precisa adivinhar se um script ainda serve, e o que ninguém roda fica à vista ("sem uso registrado").
"""

import ast
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPTS = sorted(p for p in (RAIZ / "scripts").glob("*.py") if p.name != "__init__.py")
QUEM_RODA = (
    "cron do VPS",
    "cron de casa",
    "CI",
    "hook",
    "manual",
    "outro script",
    "app",
    "Docker",
    "migração",
)
PALAVRA = (
    "(?<![A-Za-zÀ-ú])("
    + "|".join(re.escape(quem) for quem in QUEM_RODA)
    + ")(?![A-Za-zÀ-ú])"
)


def trecho_do_roda(codigo: str) -> str | None:
    """Da linha "Roda:" da docstring do módulo até o fim dela, numa linha só; None se não houver."""
    docstring = ast.get_docstring(ast.parse(codigo)) or ""
    linhas = docstring.splitlines()
    for indice, linha in enumerate(linhas):
        if linha.startswith("Roda:"):
            return " ".join(parte.strip() for parte in linhas[indice:])
    return None


def test_ha_scripts_para_conferir() -> None:
    assert len(SCRIPTS) > 50


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.stem)
def test_script_diz_quem_o_roda(script: Path) -> None:
    roda = trecho_do_roda(script.read_text(encoding="utf-8"))
    assert roda, (
        f"{script.name}: a docstring precisa terminar com 'Roda: ...' (quem chama: {', '.join(QUEM_RODA)})."
    )
    assert re.search(PALAVRA, roda), (
        f"{script.name}: a linha 'Roda:' precisa dizer por onde roda ({', '.join(QUEM_RODA)}): {roda}"
    )


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        (
            '"""Faz X.\n\nRoda: cron do VPS (todo dia às 7h00).\n"""\n',
            "Roda: cron do VPS (todo dia às 7h00).",
        ),
        (
            '"""Faz X.\n\nRoda: manual (python -m scripts.x),\nquando precisa.\n"""\n',
            "Roda: manual (python -m scripts.x), quando precisa.",
        ),
        ('"""Faz X. Rodada: nada a ver."""\n', None),
        ("x = 1\n", None),
    ],
)
def test_trecho_do_roda(codigo: str, esperado: str | None) -> None:
    assert trecho_do_roda(codigo) == esperado
