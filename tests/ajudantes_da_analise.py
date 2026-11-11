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
from unittest import mock

from src import demonstracoes as dm
from src import dossie
from src import relatorio_empresa as re_
from src.analise_escrita import entrada as en
from tests import test_relatorio_empresa_v2 as ficha_v2
from tests.ajudantes_da_ficha import FICHA_DE_17_10

CORTE = date(2026, 10, 17)  # o dia da ficha do dossiê de exemplo
PAR_DA_CPFL = Path(__file__).parent / "arquivos" / "analise" / "cpfl"


def _dados_com_o_capex_de_17_10():
    """Os dados da CPFL com o capex como a ficha de 17/10 o calculava (só imobilizado e intangível).

    As análises que o Tiago aprovou (gabarito de 18/10) citam esse capex (R$ 0,39 bi em 2025). A linha
    594 passou a somar o ativo contratual da concessão (R$ 5,35 bi): o texto novo só entra na próxima
    rodada de textos, como o título da ponte; até lá o par dados → texto fica congelado.
    """
    with (
        mock.patch.object(dm, "_ATIVO_DE_CAPEX", r"imobiliz|intangiv"),
        mock.patch.object(
            dm,
            "_COMPRA_DE_ATIVO",
            r"^(?:aquisic|compra|adic|investiment|aplicac|no |em |imobilizado|intangivel"
            r"|ativo imobilizado|ativo intangivel)",
        ),
    ):
        return ficha_v2._dados()


@cache
def entradas_da_cpfl() -> re_.Entradas:
    ficha = dossie.ler_ficha(FICHA_DE_17_10)
    assert ficha is not None
    return re_.Entradas(
        dados=_dados_com_o_capex_de_17_10(),
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
