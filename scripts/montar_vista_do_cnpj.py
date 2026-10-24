"""Monta a vista do CNPJ que vai para o servidor (`base/vista_do_cnpj.py`) e mede a busca nela. Roda em casa.

    python -m scripts.montar_vista_do_cnpj --base <base do CNPJ> --destino <pasta nova>
    python -m scripts.montar_vista_do_cnpj --destino <vista pronta> --medir 200   (só mede)

A vista leva só o que a busca por CNPJ mostra (cadastro até o município, Simples e MEI, quadro de sócios sem
o pseudônimo, mudanças de 12 meses). `--medir N` lê o cadastro de N empresas sorteadas, como a busca faz, e
escreve o tamanho da vista e o tempo de cada consulta (mediana, p95 e máximo). Nenhum CNPJ é escrito.
"""

import argparse
import json
import logging
import random
import statistics
import sys
import time
from pathlib import Path

import pyarrow.parquet as pq

from base import vista_do_cnpj
from src.cadastro_da_receita import cadastro_do_cnpj

log = logging.getLogger("tickerlab.montar_vista_do_cnpj")
SEMENTE = 20261024  # o mesmo sorteio a cada medição, para comparar uma com a outra
PERCENTIL_ALTO = 0.95
MEGA = 1024 * 1024


def _sortear_cnpjs(vista: Path, quantos: int) -> list[str]:
    """`quantos` CNPJs da vista, de prefixos sorteados (lê só a coluna `cnpj`)."""
    sorteio = random.Random(SEMENTE)
    arquivos = sorted((vista / "vigente" / "estabelecimentos").glob("*.parquet"))
    escolhidos: list[str] = []
    while len(escolhidos) < quantos and arquivos:
        arquivo = sorteio.choice(arquivos)
        coluna = pq.read_table(arquivo, columns=["cnpj"]).column("cnpj").to_pylist()
        escolhidos.append(sorteio.choice(coluna))
    return escolhidos


def medir(vista: Path, quantos: int) -> dict[str, float]:
    """O tempo, em milissegundos, de `cadastro_do_cnpj` para `quantos` empresas da vista."""
    tempos = []
    for cnpj in _sortear_cnpjs(vista, quantos):
        inicio = time.perf_counter()
        cadastro_do_cnpj(cnpj, vista)
        tempos.append((time.perf_counter() - inicio) * 1000)
    tempos.sort()
    return {
        "consultas": len(tempos),
        "mediana_ms": round(statistics.median(tempos), 1),
        "p95_ms": round(tempos[int(PERCENTIL_ALTO * (len(tempos) - 1))], 1),
        "maximo_ms": round(tempos[-1], 1),
    }


def main(argv: list[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    analisador.add_argument("--base", type=Path, default=None)
    analisador.add_argument("--destino", type=Path, required=True)
    analisador.add_argument(
        "--medir", type=int, default=0, help="quantas consultas medir"
    )
    opcoes = analisador.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if opcoes.base is not None:
        inicio = time.perf_counter()
        manifesto = vista_do_cnpj.montar(opcoes.base, opcoes.destino)
        log.info("vista montada em %.0f s", time.perf_counter() - inicio)
    else:
        manifesto = json.loads(
            (opcoes.destino / "manifesto.json").read_text(encoding="utf-8")
        )
    for tabela, numeros in manifesto["tabelas"].items():
        log.info(
            "%s: %d linhas, %.1f MB", tabela, numeros["linhas"], numeros["bytes"] / MEGA
        )
    if opcoes.medir:
        log.info("consulta: %s", medir(opcoes.destino, opcoes.medir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
