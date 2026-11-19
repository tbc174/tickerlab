"""O lançador do Claude Code no terminal (scripts/terminal/claude-tickerlab.ps1) é a única fonte da linha de
comando do `claude`: aqui conferimos, com -SoMostrar, o comando que ele montaria. Pula sem o PowerShell 7."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
LANCADOR = RAIZ / "scripts" / "terminal" / "claude-tickerlab.ps1"
PWSH = shutil.which("pwsh")
SEGUNDOS_DE_LIMITE = 120

pytestmark = pytest.mark.skipif(
    PWSH is None, reason="PowerShell 7 (pwsh) não está instalado"
)


def citar(texto: str) -> str:
    return "'" + texto.replace("'", "''") + "'"


def so_mostrar(*argumentos: str) -> str:
    assert PWSH is not None
    comando = (
        "[Console]::OutputEncoding = [Text.Encoding]::UTF8; & "
        + citar(str(LANCADOR))
        + " -SoMostrar "
        + " ".join(argumentos)
    )
    resultado = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-Command", comando],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=SEGUNDOS_DE_LIMITE,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr
    return resultado.stdout.strip()


def test_comando_padrao_roda_o_claude_no_modo_do_app():
    comando = so_mostrar()
    assert comando.startswith("claude --permission-mode auto --settings ")
    assert "claude-terminal.json" in comando
    assert "bypassPermissions" not in comando


def test_nome_e_prompt_vao_para_o_claude(tmp_path):
    prompt = tmp_path / "passagem.md"
    prompt.write_text("Mesa Dados: coleta nova.\n", encoding="utf-8")
    comando = so_mostrar(
        "-Nome", citar("Dados · coleta nova"), "-Prompt", citar(str(prompt))
    )
    assert '--name "Dados · coleta nova"' in comando
    assert comando.endswith('"Mesa Dados: coleta nova."')


def test_nova_aba_abre_o_perfil_tickerlab_na_pasta(tmp_path):
    comando = so_mostrar(
        "-NovaAba",
        "-Pasta",
        citar(str(tmp_path)),
        "-Nome",
        citar("Dados · coleta nova"),
    )
    assert comando.startswith("wt -w tickerlab nt -p TickerLab -d ")
    assert "--suppressApplicationTitle" in comando
    assert '--title "Dados · coleta nova"' in comando
    assert "claude-tickerlab.ps1" in comando
    assert '-Nome "Dados · coleta nova"' in comando
