"""Roda o validador de tape (B-10) num arquivo de ativos de ABS-EE da SEC e mostra os achados por regra.

Uso: python -m scripts.validar_abs_ee ARQUIVO.xml [--limite N]

Só lê um arquivo local (o baixado do EDGAR, com `User-Agent` declarado e no máximo 10 pedidos por segundo).
O ABS-EE não tem CNPJ: o adaptador marca os ids como `externo`, então T07 e T08 só acusam id externo
malformado; o resumo continua separando esses dois do resto.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from src.securitizacao.abs_ee import tape_de_abs_ee
from src.securitizacao.tape import CEDENTE_INVALIDO, SACADO_INVALIDO, validar_tape

DE_IDENTIFICADOR = (CEDENTE_INVALIDO, SACADO_INVALIDO)


def resumo(arquivo: Path, limite: int | None) -> list[str]:
    with arquivo.open("rb") as aberto:
        tape = tape_de_abs_ee(aberto, limite)
    achados = validar_tape(tape)
    por_regra = Counter(a.regra for a in achados)
    linhas = [
        f"data de corte {tape['data_de_corte']} · {len(tape['recebiveis'])} ativos",
    ]
    linhas += [f"{regra}: {n}" for regra, n in sorted(por_regra.items())]
    outros = sum(n for r, n in por_regra.items() if r not in DE_IDENTIFICADOR)
    linhas.append(f"achados fora T07/T08 (identificador): {outros}")
    return linhas


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("arquivo", type=Path)
    argumentos.add_argument(
        "--limite", type=int, default=None, help="primeiros N ativos"
    )
    opcoes = argumentos.parse_args(argv)
    print("\n".join(resumo(opcoes.arquivo, opcoes.limite)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
