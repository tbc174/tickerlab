"""Lista a marca de licença de cada tabela da base (ADR 0008, Emenda 1). Só lê.

    python -m scripts.marcas_da_base --base <acervo>/base [--so-barradas]

Para cada tabela (a pasta, ou a pasta e o nome quando a pasta guarda várias), a marca mais restrita
dos arquivos dela, as fontes e os endereços sem fonte conhecida (`base/licenca.py`). As que ficam
fora dos usos (fonte da B3, ADR 0102) vêm primeiro; a marca das outras é informação. Versões antigas
(`.vN`) ficam de fora.
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

from base.licenca import Licenca, licenca_da_tabela
from src.banco.coletas import fora_dos_usos, marca_mais_restrita

POR_PERIODO = re.compile(r"^\d{4}(-?\d{2}){0,2}$")  # 2024, 2024-09, 200003, 2026-10-13
VERSAO_ANTIGA = re.compile(r"\.v\d+$")
EXEMPLOS = 3  # endereços sem fonte mostrados por tabela


def nome_da_tabela(arquivo: Path, base: Path) -> str:
    pasta = arquivo.parent.relative_to(base).as_posix()
    return pasta if POR_PERIODO.match(arquivo.stem) else f"{pasta}/{arquivo.stem}"


def licencas_por_tabela(base: Path) -> dict[str, Licenca]:
    juntas: dict[str, Licenca] = defaultdict(Licenca)
    for arquivo in sorted(base.rglob("*.parquet")):
        if (
            VERSAO_ANTIGA.search(arquivo.stem)
            or not arquivo.with_suffix(".json").exists()
        ):
            continue
        nome = nome_da_tabela(arquivo, base)
        juntas[nome] = juntas[nome].junta(licenca_da_tabela(arquivo))
    return dict(juntas)


def em_texto(licencas: dict[str, Licenca], so_barradas: bool = False) -> str:
    def barrada(licenca: Licenca) -> bool:
        return any(fora_dos_usos(fonte) for fonte in licenca.fontes)

    linhas = []
    for nome, licenca in sorted(
        licencas.items(), key=lambda i: (not barrada(i[1]), i[0])
    ):
        if so_barradas and not barrada(licenca):
            continue
        fontes = ", ".join(f"{f}={m}" for f, m in sorted(licenca.fontes.items()))
        linha = f"{licenca.marca.value:<14} {nome}  [{fontes}]"
        if licenca.sem_fonte:
            exemplos = ", ".join(licenca.sem_fonte[:EXEMPLOS])
            linha += f"  sem fonte ({len(licenca.sem_fonte)}): {exemplos}"
        linhas.append(linha)
    marcas = [licenca.marca for licenca in licencas.values()]
    barradas = sum(barrada(licenca) for licenca in licencas.values())
    linhas.append(
        f"{len(licencas)} tabelas; {barradas} fora dos usos (B3); "
        f"a base inteira: {marca_mais_restrita(marcas).value}"
    )
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--base", type=Path, required=True)
    argumentos.add_argument("--so-barradas", action="store_true")
    opcoes = argumentos.parse_args(argv)
    print(em_texto(licencas_por_tabela(opcoes.base), opcoes.so_barradas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
