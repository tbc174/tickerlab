"""A ficha da CPFL de teste para a análise escrita (a mesma de `test_relatorio_empresa_v2.py`).

Rodar como módulo grava a entrada do par da CPFL (o que o modelo recebe na prova):
`python -m tests.ajudantes_da_analise tests/arquivos/analise/cpfl/entrada.json`.
"""

import dataclasses
import json
import sys
from datetime import date
from functools import cache
from pathlib import Path

from src import dossie
from src import relatorio_empresa as re_
from src.analise_escrita import entrada as en
from tests import test_relatorio_empresa_v2 as ficha_v2

CORTE = date(2026, 10, 17)  # o dia da ficha do dossiê de exemplo
PAR_DA_CPFL = Path(__file__).parent / "arquivos" / "analise" / "cpfl"


@cache
def entradas_da_cpfl() -> re_.Entradas:
    ficha = dossie.ler_ficha(dossie.FICHA_DE_EXEMPLO)
    assert ficha is not None
    return re_.Entradas(
        dados=ficha_v2._dados(),
        cnpj=ficha_v2.CPFL,
        empresa="CPFL ENERGIA S.A.",
        ticker="CPFE3.SA",
        preco=ficha_v2.PRECO,
        padroes=ficha_v2._padroes(),
        tickers=ficha_v2.TICKERS,
        dossie=dossie.dossie_da_ficha(dossie.cortar(ficha), ficha_v2.DIA_DA_FICHA),
    )


@cache
def relatorios_da_cpfl() -> tuple[re_.Relatorio, re_.Relatorio]:
    """A ficha com o dossiê (o que o Pro vê) e a mesma ficha sem ele."""
    entradas = entradas_da_cpfl()
    sem_dossie = dataclasses.replace(entradas, dossie=None)
    return re_.montar(entradas, plano="pro"), re_.montar(sem_dossie, plano="pro")


def entrada_da_cpfl() -> dict:
    com, sem = relatorios_da_cpfl()
    return en.entrada_da_ficha(com, CORTE, sem_dossie=sem)


if __name__ == "__main__":
    destino = Path(sys.argv[1])
    destino.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(entrada_da_cpfl(), ensure_ascii=False, indent=1)
    destino.write_text(texto + "\n", encoding="utf-8")
