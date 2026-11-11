"""Exporta as novidades da pesquisa (fontes provadas pelo bot conferente) para `novidades.json`.

    python -m scripts.exportar_novidades [--pasta ~/TickerLab-Pesquisa] [--saida novidades.json] [--dias 7]

Lê a memória do bot, grava o arquivo e imprime quantos itens saíram e quantos foram descartados, e por quê. Se
achar um CPF num trecho, para com erro (nada é gravado). O envio do arquivo ao servidor é outro passo.

Roda: manual (no PC, depois das rodadas do bot).
"""

import argparse
import sys
from pathlib import Path

from pesquisa.memoria import Memoria
from pesquisa.novidades import DIAS_PADRAO, CpfNoTrechoError, exportar, gravar

PASTA_PADRAO = Path.home() / "TickerLab-Pesquisa"


def main(argv: list[str] | None = None) -> int:
    leitor = argparse.ArgumentParser(description=__doc__)
    leitor.add_argument("--pasta", type=Path, default=PASTA_PADRAO)
    leitor.add_argument("--saida", type=Path, default=Path("novidades.json"))
    leitor.add_argument("--dias", type=int, default=DIAS_PADRAO)
    argumentos = leitor.parse_args(argv)
    caminho = argumentos.pasta / "memoria.sqlite"
    if not caminho.exists():
        print(f"sem memória do bot em {caminho}", file=sys.stderr)
        return 1
    try:
        exportacao = exportar(Memoria(caminho), dias=argumentos.dias)
    except CpfNoTrechoError as erro:
        print(f"PAROU: {erro}", file=sys.stderr)
        return 2
    gravar(exportacao, argumentos.saida)
    print(f"{len(exportacao.itens)} itens em {argumentos.saida}")
    for motivo, quantos in sorted(exportacao.descartados.items()):
        print(f"descartados: {quantos} ({motivo})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
