"""O par dados → texto do setor elétrico: o relatório do setor de 21/10/2026 e a análise à mão.

O relatório (`relatorio.json`) saiu da base de verdade: a noite de 21/10/2026 (a seção `setor` da
ficha) e o banco do app (membros pela CVM, DFP e ITR do lado a lado), com
`relatorio_setor.montar_relatorio_do_setor(..., plano="pro", hoje=21/10/2026)`. Ele fica guardado
como saiu, porque o banco muda todo dia; a entrada é uma função dele (`setor.entrada_do_setor`).

Rodar como módulo regrava a entrada a partir do relatório guardado:
`python -m tests.ajudantes_da_analise_do_setor`.
"""

import json
from datetime import date
from pathlib import Path
from typing import Any

from src.analise_escrita import saida, setor

PAR_DO_SETOR = Path(__file__).parent / "arquivos" / "analise" / "setor_eletrico"
CORTE = date(2026, 10, 21)  # o dia da noite e do banco de onde o relatório saiu
PARTES_DO_SETOR = saida.PARTES_DO_SETOR


def ler_do_par(nome: str) -> dict[str, Any]:
    return json.loads((PAR_DO_SETOR / nome).read_text(encoding="utf-8"))


def entrada_do_setor(relatorio: dict[str, Any]) -> dict[str, Any]:
    """A entrada do par: o relatório guardado, no corte do dia em que saiu."""
    return setor.entrada_do_setor(relatorio, CORTE)


def gabarito() -> saida.Analise:
    """O gabarito no formato de `saida`, lido como a resposta do modelo, com o roteiro do setor."""
    return saida.ler_analise(ler_do_par("gabarito.json")["analise"], PARTES_DO_SETOR)


def partes_do_gabarito() -> tuple[saida.Parte, ...]:
    return gabarito().partes


if __name__ == "__main__":
    texto = json.dumps(
        entrada_do_setor(ler_do_par("relatorio.json")), ensure_ascii=False, indent=1
    )
    (PAR_DO_SETOR / "entrada.json").write_text(texto + "\n", encoding="utf-8")
