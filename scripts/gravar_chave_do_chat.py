"""Grava a chave do modelo do chat de IA (`ANTHROPIC_API_KEY_CHAT`) no `.env` do servidor.

A chave é só do chat (linha 903, `docs/chat-de-ia.md`): a geral (`ANTHROPIC_API_KEY`) liga outros usos
pagos, e por isso o chat não a lê. Este script:

- pede a chave no terminal, sem eco (`getpass`); ela nunca é impressa, nem vai para log ou para o
  histórico do shell;
- confere só o formato (não vazia; só letras, números, `-` e `_`), nunca o valor;
- grava no `.env` que já existe (nunca num link nem num arquivo novo na pasta errada), com
  permissão 600, de uma vez só (arquivo temporário e troca), mantendo as outras linhas, o dono e o grupo;
- recusa trocar uma chave que já existe sem `--trocar`;
- **não liga o chat**: `TICKERLAB_CHAT` fica como estava (ligar é outro passo, só do Tiago).

Só usa a biblioteca padrão do Python, para rodar direto no VPS, fora do contêiner:

    cd /opt/stacks/tickerlab && python3 scripts/gravar_chave_do_chat.py
    docker compose up -d --force-recreate tickerlab-api

Roda: manual, pelo Tiago no VPS (ao pôr a chave do chat e ao trocá-la).
"""

# o python3 do sistema no VPS pode ser mais velho que o do contêiner: `X | None` sem avaliar
from __future__ import annotations

import argparse
import contextlib
import getpass
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path

VARIAVEL = "ANTHROPIC_API_KEY_CHAT"
VARIAVEL_DE_LIGAR = (
    "TICKERLAB_CHAT"  # só citada nas mensagens: este script nunca a escreve
)
ARQUIVO_PADRAO = ".env"
PERMISSAO = 0o600
DESCRICAO = (
    "Grava a chave do modelo do chat no .env (sem eco, permissão 600). Não liga o chat."
)
PROXIMO_PASSO = "docker compose up -d --force-recreate tickerlab-api"
# letras, números, "-" e "_": fecha a porta a quebra de linha, "#" e "$" (que o compose interpreta)
FORMATO_DA_CHAVE = re.compile(r"[A-Za-z0-9_-]+")


class ChaveRecusada(ValueError):
    """A chave colada não serve (a mensagem nunca leva o valor)."""


def conferir_chave(texto: str) -> str:
    """A chave sem as pontas em branco, se o formato serve; senão `ChaveRecusada`, sem o valor."""
    limpo = texto.strip()
    if not limpo:
        raise ChaveRecusada("a chave veio vazia")
    if not FORMATO_DA_CHAVE.fullmatch(limpo):
        raise ChaveRecusada(
            "a chave tem caractere que não é letra, número, '-' ou '_' (espaço, quebra de linha...)"
        )
    return limpo


def _e_a_linha_da_chave(linha: str) -> bool:
    """Reconhece a variável também com espaço antes, `export ` ou espaço antes do `=`."""
    nome = linha.strip().removeprefix("export ").split("=", 1)[0].strip()
    return "=" in linha and nome == VARIAVEL


def _conferir_o_arquivo(arquivo: Path) -> None:
    """Só grava num `.env` que já existe e é arquivo de verdade (nem link, nem pasta errada)."""
    if arquivo.is_symlink():
        raise FileExistsError(
            f"{arquivo.absolute()} é um link; rode apontando para o arquivo de verdade."
        )
    if not arquivo.is_file():
        raise FileExistsError(
            f"{arquivo.absolute()} não existe. Rode na pasta do servidor (a que tem o .env)."
        )


def gravar(arquivo: Path, chave: str, *, trocar: bool) -> None:
    """Grava a chave no arquivo com permissão 600, sem mexer nas outras linhas."""
    _conferir_o_arquivo(arquivo)
    original = arquivo.stat()
    linhas = arquivo.read_text(encoding="utf-8").splitlines()
    if any(_e_a_linha_da_chave(linha) for linha in linhas) and not trocar:
        raise FileExistsError(
            f"{arquivo} já tem a {VARIAVEL}. Para trocá-la, rode de novo com --trocar."
        )
    outras = [linha for linha in linhas if not _e_a_linha_da_chave(linha)]
    conteudo = "\n".join([*outras, f"{VARIAVEL}={chave}"]) + "\n"
    temporario = arquivo.with_name(f".{arquivo.name}.novo")
    temporario.unlink(missing_ok=True)
    descritor = os.open(temporario, os.O_WRONLY | os.O_CREAT | os.O_EXCL, PERMISSAO)
    with os.fdopen(descritor, "w", encoding="utf-8") as saida:
        saida.write(conteudo)
    # o dono e o grupo do .env de antes: rodar com sudo não tira o arquivo do usuário do deploy;
    # sem sudo, o arquivo já é de quem roda e a troca de dono é recusada sem mudar nada
    if hasattr(os, "chown"):
        with contextlib.suppress(PermissionError):
            os.chown(temporario, original.st_uid, original.st_gid)
    os.replace(temporario, arquivo)
    os.chmod(arquivo, PERMISSAO)


def principal(
    argumentos: list[str] | None = None,
    perguntar: Callable[[str], str] = getpass.getpass,
) -> int:
    """Lê as opções, pede a chave e grava; devolve o código de saída."""
    leitor = argparse.ArgumentParser(description=DESCRICAO)
    leitor.add_argument("--arquivo", type=Path, default=Path(ARQUIVO_PADRAO))
    leitor.add_argument(
        "--trocar", action="store_true", help="troca a chave que já existe"
    )
    opcoes = leitor.parse_args(argumentos)
    try:
        chave = conferir_chave(perguntar("Chave do modelo do chat (não aparece): "))
        gravar(opcoes.arquivo, chave, trocar=opcoes.trocar)
    except (ChaveRecusada, FileExistsError) as erro:
        print(f"Nada foi gravado: {erro}", file=sys.stderr)
        return 1
    print(
        f"Chave do chat gravada em {opcoes.arquivo.absolute()} (permissão 600). O chat continua como estava: "
        f"{VARIAVEL_DE_LIGAR} não foi mexida. Para a API ler a chave: {PROXIMO_PASSO}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(principal())
