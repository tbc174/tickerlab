"""A raiz do repositório é trancada: só entram os arquivos e as pastas das listas abaixo (casa em ordem, fila 701).

Arquivo solto na raiz vira costume, e um `git add -A` o leva ao repositório público. Quem precisa de um arquivo
ou de uma pasta nova na raiz diz o motivo no PR e põe o nome aqui; o resto vai para a pasta certa (`docs/`,
`notas/`, `scripts/`, `tests/arquivos/`...). As listas são exatas nos dois sentidos: o que sai do repositório
também sai daqui. O hook de início de sessão do PC avisa as entradas soltas (fora do Git) na raiz da cópia
principal; este teste cuida do que o Git rastreia.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]

ARQUIVOS_DA_RAIZ = frozenset(
    {
        ".coveragerc",
        ".dockerignore",
        ".env.example",
        ".gitattributes",
        ".gitignore",
        "AGENTS.md",
        "CLAUDE.md",
        "Dockerfile",
        "README.md",
        "SECURITY.md",
        "abrir_claude_no_celular.bat",
        "abrir_painel_trader.bat",
        "alembic.ini",
        "app.py",
        "atualizar_b3.bat",
        "compose.yaml",
        # o conector remoto dos analistas (linha 570): à parte, para o "up" comum não o subir
        "compose.conector.yaml",
        "pyrightconfig.json",
        "pytest.ini",
        "requirements-estudos.txt",
        "requirements-prod.txt",
        "requirements-trader.txt",
        "requirements.txt",
        "ruff.toml",
    }
)
PASTAS_DA_RAIZ = frozenset(
    {
        ".github",
        ".streamlit",
        ".vscode",
        "base",
        "cli",
        "conector_remoto",
        "conteudo",
        "dados_de_exemplo",
        "docs",
        "estudos",
        "guias",
        "migracoes",
        "notas",
        "novo",
        "pesquisa",
        "scripts",
        "site",
        "site-api",
        "src",
        "static",
        "telas",
        "tests",
        "trader",
        "web",
    }
)


def _entradas_rastreadas() -> tuple[set[str], set[str]]:
    """Arquivos e pastas de primeiro nível que o Git rastreia (o que há só no disco é assunto do hook)."""
    comando = ["git", "-C", str(RAIZ), "-c", "core.quotepath=off", "ls-files"]
    try:
        saida = subprocess.run(
            comando,
            capture_output=True,
            check=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        ).stdout
    except (OSError, subprocess.SubprocessError) as erro:
        pytest.skip(f"sem git para listar a raiz: {erro}")
    arquivos: set[str] = set()
    pastas: set[str] = set()
    for caminho in saida.splitlines():
        primeiro, barra, _ = caminho.partition("/")
        if primeiro:
            (pastas if barra else arquivos).add(primeiro)
    return arquivos, pastas


def test_arquivos_da_raiz_sao_so_os_da_lista() -> None:
    arquivos, _ = _entradas_rastreadas()
    a_mais = sorted(arquivos - ARQUIVOS_DA_RAIZ)
    assert not a_mais, (
        f"arquivo novo na raiz do repositório: {a_mais}. Mova para a pasta certa ou, com o motivo no PR, "
        "acrescente o nome a ARQUIVOS_DA_RAIZ."
    )
    sumiram = sorted(ARQUIVOS_DA_RAIZ - arquivos)
    assert not sumiram, (
        f"na lista, mas não no Git: {sumiram}. Tire o nome de ARQUIVOS_DA_RAIZ."
    )


def test_pastas_da_raiz_sao_so_as_da_lista() -> None:
    _, pastas = _entradas_rastreadas()
    a_mais = sorted(pastas - PASTAS_DA_RAIZ)
    assert not a_mais, (
        f"pasta nova na raiz do repositório: {a_mais}. Ponha dentro de uma pasta existente ou, com o motivo no "
        "PR, acrescente o nome a PASTAS_DA_RAIZ."
    )
    sumiram = sorted(PASTAS_DA_RAIZ - pastas)
    assert not sumiram, (
        f"na lista, mas não no Git: {sumiram}. Tire o nome de PASTAS_DA_RAIZ."
    )
