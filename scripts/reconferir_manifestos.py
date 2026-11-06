"""Refaz a conferência do contrato nos manifestos das tabelas da API (CNPJ e DFP/ITR "como eram").

    python -m scripts.reconferir_manifestos --base <acervo>/base [--tabelas cnpj_qsa ...] [--so-ver]

Lê cada Parquet de cada tabela, confere contra o dicionário e grava `conferencia_do_contrato` no manifesto
ao lado (`base/reconferir.py`). Sem `--tabelas`, as da API. Saída 0 se todas passaram; 1 se alguma reprovou.

Roda: manual (python -m scripts.reconferir_manifestos); sem uso registrado em 05/11/2026.
"""

import argparse
import logging
import sys
from pathlib import Path

from base.reconferir import reconferir_tabela

log = logging.getLogger("tickerlab.reconferir_manifestos")

TABELAS_DA_API = (
    "demonstracoes_como_era",
    "dmpl_como_era",
    "cnpj_estabelecimentos",
    "cnpj_estabelecimentos_mudancas",
    "cnpj_simples",
    "cnpj_simples_mudancas",
    "cnpj_qsa",
    "cnpj_qsa_mudancas",
)


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--base", type=Path, required=True)
    argumentos.add_argument("--tabelas", nargs="+", default=list(TABELAS_DA_API))
    argumentos.add_argument(
        "--so-ver", action="store_true", help="não grava os manifestos"
    )
    dados = argumentos.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    tudo_certo = True
    for nome in dados.tabelas:
        resumo = reconferir_tabela(dados.base, nome, gravar=not dados.so_ver)
        print(
            f"{nome}: {resumo.aprovados}/{resumo.arquivos} aprovados, {len(resumo.sem_manifesto)} sem manifesto"
        )
        for arquivo, problemas in resumo.reprovados.items():
            tudo_certo = False
            print(f"  reprovado {arquivo}: {'; '.join(problemas[:3])}")
    return 0 if tudo_certo else 1


if __name__ == "__main__":
    sys.exit(main())
