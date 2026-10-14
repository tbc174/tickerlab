"""Traz a `main` para o ramo e refaz o que é gerado, para conflito em pasta gerada não parar ninguém.

    python -m scripts.juntar_main

`site/`, `novo/` e `web/conteudo/` saem dos geradores (Python e `npm`), e o `novo/` é um pacote
minificado com nome que muda a cada build. Dois PRs que mexem em página ou no React regravam os
mesmos arquivos, e o GitHub acusa conflito mesmo quando o código não conflita (13/10/2026: o PR 7
da base travou duas vezes assim). Regra: **pasta gerada não se junta à mão; se refaz.**

O que faz, nesta ordem (merge, nunca rebase: push forçado é proibido):
1. confere que a cópia está limpa e busca a `main`;
2. `git merge origin/main`; se houver conflito **fora** das pastas geradas, desfaz o merge e para;
3. nas pastas geradas, parte da versão da `main` e roda todos os geradores por cima;
4. adiciona só as pastas geradas e faz o commit do merge.
Depois é só `git push` (comum) e esperar o CI.
"""

import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTAS_GERADAS = ("site/", "novo/", "web/conteudo/")
MAIN = "origin/main"


def _python() -> str:
    return sys.executable


GERADORES: tuple[tuple[tuple[str, ...], str], ...] = (
    ((_python(), "-m", "scripts.exportar_conteudo"), "."),
    ((_python(), "-m", "scripts.gerar_site"), "."),
    (("npm", "run", "site"), "web"),
    (("npm", "run", "app"), "web"),
)


def e_gerado(caminho: str) -> bool:
    return caminho.replace("\\", "/").startswith(PASTAS_GERADAS)


def conflitos_fora_dos_gerados(conflitos: list[str]) -> list[str]:
    """Os conflitos que pedem uma pessoa (código, testes, documentos)."""
    return [c for c in conflitos if not e_gerado(c)]


def _git(*args: str, conferir: bool = True) -> str:
    resultado = subprocess.run(
        ["git", *args], cwd=RAIZ, capture_output=True, text=True, check=False
    )
    if conferir and resultado.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {resultado.stderr.strip()}")
    return resultado.stdout


def _rodar(comando: tuple[str, ...], pasta: str) -> None:
    executavel = shutil.which(comando[0]) or comando[0]  # npm é npm.cmd no Windows
    subprocess.run([executavel, *comando[1:]], cwd=RAIZ / pasta, check=True)


def _conflitos() -> list[str]:
    return [l for l in _git("diff", "--name-only", "--diff-filter=U").splitlines() if l]


def _refazer_gerados() -> None:
    for pasta in PASTAS_GERADAS:
        _git("rm", "-r", "-q", "--cached", "--ignore-unmatch", pasta)
        shutil.rmtree(RAIZ / pasta, ignore_errors=True)
        _git("checkout", MAIN, "--", pasta)
    if not (RAIZ / "web" / "node_modules").exists():
        _rodar(("npm", "ci", "--ignore-scripts"), "web")
    for comando, pasta in GERADORES:
        _rodar(comando, pasta)
    _git("add", "-A", "--", *PASTAS_GERADAS)


def main() -> int:
    if _git("status", "--porcelain", "--untracked-files=no").strip():
        print("A cópia tem mudanças sem commit: faça o commit antes de juntar a main.")
        return 1
    _git("fetch", "-q", "origin")
    if not _git("log", "--oneline", f"HEAD..{MAIN}").strip():
        print("O ramo já tem tudo da main.")
        return 0
    _git("merge", "--no-ff", "--no-commit", MAIN, conferir=False)
    pessoais = conflitos_fora_dos_gerados(_conflitos())
    if pessoais:
        _git("merge", "--abort")
        print("Conflito fora das pastas geradas (resolver à mão):")
        print("\n".join(f"  {c}" for c in pessoais))
        return 1
    _refazer_gerados()
    if _conflitos():
        print("Ainda há conflito depois de refazer os gerados: confira com git status.")
        return 1
    _git("commit", "-q", "-m", "merge: main no ramo (pastas geradas refeitas)")
    print(
        "Main juntada e gerados refeitos. Agora: git push (sem --force) e esperar o CI."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
