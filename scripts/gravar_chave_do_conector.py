"""Grava a chave do servidor do conector remoto (`TICKERLAB_MCP_CHAVE_DOS_TOKENS`) no `.env.mcp`.

A chave sela os tokens do OAuth dos analistas (linha 570, `docs/conector-remoto.md`). Este script:

- cria uma chave nova (32 bytes aleatórios, em base64url) ou, com `--colar`, pede uma no terminal sem
  eco (`getpass`); a chave nunca é impressa, nem vai para log ou para o histórico do shell;
- grava no `.env.mcp` com permissão 600, de uma vez só (arquivo temporário e troca), e mantém as outras
  linhas do arquivo;
- recusa trocar uma chave que já existe sem `--trocar`: trocar a chave derruba o acesso de todos os
  analistas (é o passo 1 do incidente "a chave do servidor vazou").

Só usa a biblioteca padrão do Python, para rodar direto no VPS, fora do contêiner:

    cd /opt/stacks/tickerlab && python3 scripts/gravar_chave_do_conector.py
    docker compose -f compose.yaml -f compose.conector.yaml up -d tickerlab-mcp

Roda: manual, pelo Tiago no VPS (antes do primeiro "up" do tickerlab-mcp e no incidente de chave vazada).
"""

import argparse
import base64
import binascii
import getpass
import os
import sys
from collections.abc import Callable
from pathlib import Path

VARIAVEL = "TICKERLAB_MCP_CHAVE_DOS_TOKENS"
ARQUIVO_PADRAO = ".env.mcp"
TAMANHO_DA_CHAVE = 32  # AES-256, o mesmo de conector_remoto/selo.py
PERMISSAO = 0o600
DESCRICAO = (
    "Grava a chave do servidor do conector remoto no .env.mcp (sem eco, permissão 600)."
)


class ChaveRecusada(ValueError):
    """A chave colada não serve (a mensagem nunca leva o valor)."""


def nova_chave() -> str:
    """Uma chave nova em base64url sem `=`, o formato que o conector lê."""
    return base64.urlsafe_b64encode(os.urandom(TAMANHO_DA_CHAVE)).decode().rstrip("=")


def conferir_chave(texto: str) -> str:
    """A chave limpa, se ela tem 32 bytes em base64url; senão `ChaveRecusada`, sem o valor."""
    limpo = texto.strip()
    try:
        bruta = base64.urlsafe_b64decode(limpo + "=" * (-len(limpo) % 4))
    except (binascii.Error, ValueError):
        raise ChaveRecusada("a chave não é base64url") from None
    if len(bruta) != TAMANHO_DA_CHAVE:
        raise ChaveRecusada(f"a chave precisa ter {TAMANHO_DA_CHAVE} bytes")
    return limpo


def _ja_tem_chave(linhas: list[str]) -> bool:
    return any(linha.startswith(f"{VARIAVEL}=") for linha in linhas)


def gravar(arquivo: Path, chave: str, *, trocar: bool) -> None:
    """Grava a chave no arquivo com permissão 600, sem mexer nas outras linhas."""
    linhas = (
        arquivo.read_text(encoding="utf-8").splitlines() if arquivo.exists() else []
    )
    if _ja_tem_chave(linhas) and not trocar:
        raise FileExistsError(
            f"{arquivo} já tem a {VARIAVEL}; trocar derruba todos os analistas. "
            "Se é isso mesmo (incidente), rode de novo com --trocar."
        )
    outras = [linha for linha in linhas if not linha.startswith(f"{VARIAVEL}=")]
    conteudo = "\n".join([*outras, f"{VARIAVEL}={chave}"]) + "\n"
    temporario = arquivo.with_name(f".{arquivo.name}.novo")
    temporario.unlink(missing_ok=True)
    descritor = os.open(temporario, os.O_WRONLY | os.O_CREAT | os.O_EXCL, PERMISSAO)
    with os.fdopen(descritor, "w", encoding="utf-8") as saida:
        saida.write(conteudo)
    os.replace(temporario, arquivo)
    os.chmod(arquivo, PERMISSAO)


def principal(
    argumentos: list[str] | None = None,
    perguntar: Callable[[str], str] = getpass.getpass,
) -> int:
    """Lê as opções, cria ou pede a chave e grava; devolve o código de saída."""
    leitor = argparse.ArgumentParser(description=DESCRICAO)
    leitor.add_argument("--arquivo", type=Path, default=Path(ARQUIVO_PADRAO))
    leitor.add_argument(
        "--colar", action="store_true", help="pede a chave no terminal, sem eco"
    )
    leitor.add_argument(
        "--trocar", action="store_true", help="troca a chave que já existe"
    )
    opcoes = leitor.parse_args(argumentos)
    try:
        chave = (
            conferir_chave(perguntar("Chave do servidor (não aparece): "))
            if opcoes.colar
            else nova_chave()
        )
        gravar(opcoes.arquivo, chave, trocar=opcoes.trocar)
    except (ChaveRecusada, FileExistsError) as erro:
        print(f"Nada foi gravado: {erro}", file=sys.stderr)
        return 1
    print(
        f"Chave do conector gravada em {opcoes.arquivo} (permissão 600). "
        "Agora: docker compose -f compose.yaml -f compose.conector.yaml up -d tickerlab-mcp"
    )
    return 0


if __name__ == "__main__":
    sys.exit(principal())
