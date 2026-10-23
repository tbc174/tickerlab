"""Diz ao CI se uma mudança é só de texto, para ele pular a suíte inteira.

Uso no CI: `git diff --name-only BASE HEAD | python3 scripts/mudou_so_texto.py` (imprime `true` ou
`false`). Roda antes de instalar as dependências, por isso só usa a biblioteca padrão.

Na dúvida, a resposta é `false` e a suíte inteira roda: um arquivo só entra em `SO_TEXTO` se nenhum
teste e nenhuma parte do app o lê.
"""

import sys
from collections.abc import Iterable
from fnmatch import fnmatch

# Textos que ninguém lê em execução (no fnmatch, "*" também atravessa "/").
SO_TEXTO = (
    "CLAUDE.md",
    "*/CLAUDE.md",
    "AGENTS.md",
    "*/AGENTS.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "notas/*.md",
    "guias/*.md",
    "docs/*.md",
    ".github/ISSUE_TEMPLATE/*",
    ".github/PULL_REQUEST_TEMPLATE.md",
    # lidos só pelo tests/test_publicacao.py, que o CI roda também nas mudanças só de texto
    "README.md",
    "docs/imagens/*",
)

# Textos conferidos por teste: o trader guarda a impressão digital (SHA-256) do critério da M2.
NUNCA_SO_TEXTO = ("docs/pre-registro-*",)


def e_so_texto(caminho: str) -> bool:
    """Diz se um arquivo mudado pode ficar sem a suíte inteira."""
    if any(fnmatch(caminho, padrao) for padrao in NUNCA_SO_TEXTO):
        return False
    return any(fnmatch(caminho, padrao) for padrao in SO_TEXTO)


def mudou_so_texto(caminhos: Iterable[str]) -> bool:
    """Diz se todos os arquivos mudados são só texto (uma lista vazia não conta)."""
    lista = [caminho.strip() for caminho in caminhos if caminho.strip()]
    return bool(lista) and all(e_so_texto(caminho) for caminho in lista)


if __name__ == "__main__":
    print("true" if mudou_so_texto(sys.stdin) else "false")
