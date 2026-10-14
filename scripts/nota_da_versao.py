"""Nota da versão (GitHub Release) de uma atualização, com o mesmo texto da página Novidades.

python -m scripts.nota_da_versao 2026-10-13 --saida nota.md
gh release create v2026.10.13 --title "..." --notes-file nota.md
"""

import argparse
import sys
from datetime import date
from pathlib import Path

from src.novidades import ATUALIZACOES, Atualizacao

PAGINA = "https://tickerlab.com.br/novidades.html"
AVISO = "Nada aqui é recomendação de investimento."


def nota(atualizacao: Atualizacao) -> str:
    linhas = [
        f"## {atualizacao.titulo}",
        "",
        atualizacao.resumo,
        "",
        "### Novidades",
        "",
    ]
    linhas += [f"- {t}" for t in atualizacao.novidades]
    if atualizacao.correcoes:
        linhas += ["", "### Correções", ""]
        linhas += [f"- {t}" for t in atualizacao.correcoes]
    linhas += ["", f"Todas as atualizações: {PAGINA}. {AVISO}", ""]
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("data", type=date.fromisoformat)
    argumentos.add_argument(
        "--saida",
        type=Path,
        help="grava neste arquivo, em UTF-8 (sem ela, na tela: no Windows os acentos podem quebrar)",
    )
    opcoes = argumentos.parse_args(argv)
    escolhida = next((a for a in ATUALIZACOES if a.data == opcoes.data), None)
    if escolhida is None:
        print(f"Nenhuma atualização em {opcoes.data:%d/%m/%Y}.", file=sys.stderr)
        return 1
    if opcoes.saida is None:
        sys.stdout.write(nota(escolhida))
    else:  # LF também no Windows: o GitHub mostra o texto como o CI o geraria
        opcoes.saida.write_text(nota(escolhida), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
