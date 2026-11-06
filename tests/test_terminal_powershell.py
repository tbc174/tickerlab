"""O painel `tl` (scripts/terminal/) tem os próprios testes em PowerShell; aqui só os rodamos pelo pytest.

Pula quando o PowerShell 7 (pwsh) não está instalado: o painel é opcional e só existe para quem
trabalha no terminal. No CI (Ubuntu) o pwsh vem instalado, então os testes rodam lá também.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
TESTES_DO_PAINEL = RAIZ / "scripts" / "terminal" / "testes" / "rodar.ps1"
PWSH = shutil.which("pwsh")
SEGUNDOS_DE_LIMITE = 300


@pytest.mark.skipif(PWSH is None, reason="PowerShell 7 (pwsh) não está instalado")
def test_painel_do_terminal_passa_nos_proprios_testes() -> None:
    assert PWSH is not None
    resultado = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-File", str(TESTES_DO_PAINEL)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=SEGUNDOS_DE_LIMITE,
        check=False,
    )
    assert resultado.returncode == 0, (
        f"saída:\n{resultado.stdout}\nerros:\n{resultado.stderr}"
    )
