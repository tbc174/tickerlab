"""Procura chaves da API externa (`tld_<prefixo>_<segredo>`) nos arquivos versionados.

O GitHub só avisa de chave vazada se conhecer o padrão, e padrão próprio de secret scanning depende do
plano da conta (N7, linha 170 da fila). Este passo do CI cobre o buraco: falha se um arquivo do
repositório público tiver algo com o formato de uma chave de `src/chaves_da_api.py`.

Uso: `python3 scripts/procurar_chaves_da_api.py [arquivo ...]` (sem argumentos, todos os arquivos que
o Git versiona). Imprime `arquivo:linha` e **nunca** a chave achada; sai com 1 se achar alguma.
Só stdlib, porque roda no CI antes de instalar as dependências.
"""

import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

# O prefixo fixo `tld_` e o formato inteiro, não o último "_" (o segredo em base64 para URL também
# tem "_" e "-"). Antes e depois só vale o que não faria parte de uma chave maior.
PADRAO = re.compile(
    r"(?<![A-Za-z0-9])tld_[a-z2-7]{8}_[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])"
)

# Texto do padrão para cadastrar no GitHub (Settings > Advanced Security > Custom patterns): o
# GitHub pede o formato do segredo e o que vem antes e depois em campos separados.
PADRAO_DO_GITHUB = {
    "antes": r"(^|[^A-Za-z0-9])",
    "segredo": r"tld_[a-z2-7]{8}_[A-Za-z0-9_-]{43}",
    "depois": r"($|[^A-Za-z0-9_-])",
}


def linhas_com_chave(texto: str) -> list[int]:
    """Os números (a partir de 1) das linhas que têm algo com o formato de uma chave."""
    return [
        n for n, linha in enumerate(texto.splitlines(), start=1) if PADRAO.search(linha)
    ]


def arquivos_versionados() -> list[str]:
    saida = subprocess.run(
        ["git", "ls-files", "-z"], capture_output=True, check=True, text=True
    ).stdout
    return [caminho for caminho in saida.split("\0") if caminho]


def procurar(caminhos: Iterable[str]) -> list[str]:
    """`arquivo:linha` de cada achado; arquivo ilegível como texto (binário) é pulado."""
    achados = []
    for caminho in caminhos:
        try:
            texto = Path(caminho).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        achados += [f"{caminho}:{n}" for n in linhas_com_chave(texto)]
    return achados


def main(argumentos: list[str]) -> int:
    achados = procurar(argumentos or arquivos_versionados())
    for achado in achados:
        print(f"Chave da API no repositório: {achado}")
    if achados:
        print(
            "Revogue a chave (tela de admin) e tire-a do arquivo; só apagar não basta, o Git guarda."
        )
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
