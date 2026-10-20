"""Confere a cópia da B3 do VPS contra a de casa (ADR 0073; `base/arquivo/copia_b3.py`).

    python - --trabalho /app/dados_locais/acervo/.temporario/b3-vps < scripts/reconciliar_b3_vps.py

Roda no servidor de casa, depois do `~/bin/reconciliar-b3.sh`, que deixa em `--trabalho`:
`lista.txt` (o que o VPS tem, com o SHA-256 calculado lá na hora) e `recebidos/AAAA-MM-DD/<sha>.zip`
(as versões que o VPS tem e o acervo de casa não). Aqui: confere o SHA-256 dos arquivos de casa,
compara a última versão de cada dia da janela nas duas máquinas e põe no acervo o que veio do VPS.

Saída 0 tudo igual; 1 dia faltando ou diferente numa das máquinas (ou arquivo estragado), com a
última linha `FALHAS: ...` (vai para o aviso do Kuma).
"""

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from base.arquivo.copia_b3 import (
    comparar,
    conferir_casa,
    dias_da_janela,
    guardar_recebidos,
    ler_lista_do_vps,
    ultimas_da_casa,
)
from src import acervo

log = logging.getLogger("reconciliar_b3_vps")

TAMANHO_MAXIMO_DO_RESUMO = 300  # o resumo vai no endereço do push do Kuma


def agora() -> datetime:
    """O relógio do script; um ponto só para os testes fixarem o momento."""
    return datetime.now(UTC)


def main(argv: list[str] | None = None) -> int:
    argumentos = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    argumentos.add_argument("--trabalho", required=True, type=Path)
    opcoes = argumentos.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    pasta = acervo.pasta_do_acervo()
    if pasta is None:
        print("FALHAS: B3 casa x VPS: o acervo está desligado")
        return 1

    momento = agora()
    dias = dias_da_janela(momento)
    # a comparação olha o estado de antes de trazer: o dia trazido agora ainda é alarme hoje
    casa = ultimas_da_casa(pasta, dias)
    problemas = conferir_casa(pasta, casa)
    vps, do_vps = ler_lista_do_vps(
        (opcoes.trabalho / "lista.txt").read_text(encoding="utf-8")
    )
    problemas += do_vps + comparar(casa, vps, dias)
    trazidos, na_chegada = guardar_recebidos(opcoes.trabalho / "recebidos", momento)
    problemas += na_chegada

    log.info(
        "B3 casa x VPS: %d dias na janela, %d em casa, %d no VPS, %d trazidos do VPS, "
        "%d problemas",
        len(dias),
        len(casa),
        len(vps),
        trazidos,
        len(problemas),
    )
    if problemas:
        linha = "FALHAS: B3 casa x VPS: " + "; ".join(problemas)
        print(linha[:TAMANHO_MAXIMO_DO_RESUMO])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
