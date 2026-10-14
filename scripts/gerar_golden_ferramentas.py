"""Grava os casos "golden" das ferramentas do site: `web/testes/golden_ferramentas.json`.

    python -m scripts.gerar_golden_ferramentas

Cada caso é uma chamada de uma conta de `src/ferramentas/` (nome, argumentos na ordem) e o que o
Python devolveu, ou `{"erro": true}` quando a entrada é recusada. O vitest
(`web/testes/ferramentas/golden.test.ts`) chama a mesma conta em TypeScript e compara; o
`tests/test_golden_ferramentas.py` confere que o arquivo está em dia com o Python.

Rodar depois de mudar uma conta de propósito (e a cópia em TS) ou de acrescentar casos.
"""

import dataclasses
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.ferramentas import aportes, custos, juros
from src.ferramentas import viver_de_renda as vr

ARQUIVO = (
    Path(__file__).resolve().parents[1] / "web" / "testes" / "golden_ferramentas.json"
)

Conta = Callable[..., Any]

CONTAS: dict[str, Conta] = {
    "juros.montante": juros.montante,
    "juros.evolucao": juros.evolucao,
    "juros.taxa_equivalente": juros.taxa_equivalente,
    "juros.taxa_por_mes": juros.taxa_por_mes,
    "aportes.valor_futuro": aportes.valor_futuro,
    "aportes.aporte_para_meta": aportes.aporte_para_meta,
    "aportes.meses_ate_meta": aportes.meses_ate_meta,
    "aportes.evolucao": aportes.evolucao,
    "custos.custo_da_taxa": custos.custo_da_taxa,
    "custos.evolucao_da_taxa": custos.evolucao_da_taxa,
    "custos.alta_para_recuperar": custos.alta_para_recuperar,
    "viver_de_renda.patrimonio_necessario": vr.patrimonio_necessario,
    "viver_de_renda.duracao_em_meses": vr.duracao_em_meses,
    "viver_de_renda.renda_da_regra_dos_4": vr.renda_da_regra_dos_4,
}

# (conta, argumentos na ordem da função); entram também entradas que devem ser recusadas
CASOS: list[tuple[str, list[Any]]] = [
    ("juros.montante", [1000, 0.01, 12, True]),
    ("juros.montante", [1000, 0.01, 12, False]),
    ("juros.montante", [1000, 0.01, 0, True]),
    ("juros.montante", [1000, 0, 120, True]),
    ("juros.montante", [1000, -0.01, 24, True]),
    ("juros.montante", [250.5, 0.0087, 1, True]),
    ("juros.montante", [1e6, 0.0095, 600, True]),
    ("juros.montante", [1e6, 0.0095, 600, False]),
    ("juros.montante", [50000, 0.15, 30, True]),
    ("juros.montante", [0, 0.01, 12, True]),
    ("juros.montante", [-1, 0.01, 12, True]),
    ("juros.montante", [1000, -1, 12, True]),
    ("juros.montante", [1000, 0.01, -1, True]),
    ("juros.montante", [1000, 0.01, juros.PRAZO_MAXIMO + 1, True]),
    ("juros.evolucao", [1000, 0.01, 12, True]),
    ("juros.evolucao", [1000, 0.01, 12, False]),
    ("juros.evolucao", [5000, 0.012, 3, True]),
    ("juros.evolucao", [1000, 0.01, 0, True]),
    ("juros.taxa_equivalente", [0.01, 1, 12]),
    ("juros.taxa_equivalente", [0.1065, 12, 1]),
    ("juros.taxa_equivalente", [0.15, 12, 6]),
    ("juros.taxa_equivalente", [-0.05, 12, 1]),
    ("juros.taxa_equivalente", [0.01, 0, 12]),
    ("juros.taxa_equivalente", [-1, 1, 12]),
    ("juros.taxa_por_mes", [0.01, "mes"]),
    ("juros.taxa_por_mes", [0.1265, "ano"]),
    ("juros.taxa_por_mes", [0.01, "semana"]),
    ("aportes.valor_futuro", [0, 500, 0.008, 120, False]),
    ("aportes.valor_futuro", [0, 500, 0.008, 120, True]),
    ("aportes.valor_futuro", [10000, 500, 0.008, 120, False]),
    ("aportes.valor_futuro", [1000, 100, 0, 12, False]),
    ("aportes.valor_futuro", [1000, 100, 1e-15, 12, False]),
    ("aportes.valor_futuro", [0, 1000, 0.0085, 360, False]),
    ("aportes.valor_futuro", [50000, 0, -0.005, 60, True]),
    ("aportes.valor_futuro", [0, 300, 0.01, 0, False]),
    ("aportes.valor_futuro", [-1, 300, 0.01, 12, False]),
    ("aportes.valor_futuro", [0, -300, 0.01, 12, False]),
    ("aportes.aporte_para_meta", [100000, 0, 0.008, 120, False]),
    ("aportes.aporte_para_meta", [1000000, 20000, 0.007, 300, True]),
    ("aportes.aporte_para_meta", [2200, 1000, 0, 12, False]),
    ("aportes.aporte_para_meta", [1000, 5000, 0.01, 12, False]),
    ("aportes.aporte_para_meta", [1000, 0, 0.01, 0, False]),
    ("aportes.aporte_para_meta", [-5, 0, 0.01, 12, False]),
    ("aportes.meses_ate_meta", [100000, 0, 500, 0.008, False]),
    ("aportes.meses_ate_meta", [100000, 0, 500, 0.008, True]),
    ("aportes.meses_ate_meta", [1000, 5000, 0, 0.01, False]),
    ("aportes.meses_ate_meta", [2000, 1000, 0, -0.01, False]),
    ("aportes.meses_ate_meta", [1e9, 0, 1, 0, False]),
    ("aportes.meses_ate_meta", [1e6, 10000, 2000, 0.009, False]),
    ("aportes.evolucao", [1000, 100, 0.01, 6, False]),
    ("aportes.evolucao", [1000, 100, 0.01, 6, True]),
    ("aportes.evolucao", [0, 250, 0, 3, False]),
    ("custos.custo_da_taxa", [100000, 0.08, 0.01, 20]),
    ("custos.custo_da_taxa", [100000, 0.08, 0.02, 30]),
    ("custos.custo_da_taxa", [50000, 0.1065, 0.005, 10]),
    ("custos.custo_da_taxa", [1000, 0.1, 0, 10]),
    ("custos.custo_da_taxa", [0, 0.1, 0.01, 10]),
    ("custos.custo_da_taxa", [1000, -0.05, 0.01, 5]),
    ("custos.custo_da_taxa", [1000, 0.08, 1, 5]),
    ("custos.custo_da_taxa", [1000, 0.08, 0.01, 101]),
    ("custos.evolucao_da_taxa", [1000, 0.1, 0.02, 3]),
    ("custos.evolucao_da_taxa", [10000, 0.07, 0.015, 15]),
    ("custos.alta_para_recuperar", [-0.1]),
    ("custos.alta_para_recuperar", [-0.5]),
    ("custos.alta_para_recuperar", [-0.8]),
    ("custos.alta_para_recuperar", [-0.333]),
    ("custos.alta_para_recuperar", [0]),
    ("custos.alta_para_recuperar", [-1]),
    ("custos.alta_para_recuperar", [0.2]),
    ("viver_de_renda.patrimonio_necessario", [5000, 0.04, None]),
    ("viver_de_renda.patrimonio_necessario", [5000, 0.04, 30]),
    ("viver_de_renda.patrimonio_necessario", [10000, 0.035, 25]),
    ("viver_de_renda.patrimonio_necessario", [1000, 0, 10]),
    ("viver_de_renda.patrimonio_necessario", [3000, -0.01, 20]),
    ("viver_de_renda.patrimonio_necessario", [1000, 0, None]),
    ("viver_de_renda.patrimonio_necessario", [1000, 0.04, 0]),
    ("viver_de_renda.patrimonio_necessario", [-5, 0.04, 30]),
    ("viver_de_renda.duracao_em_meses", [1_000_000, 5000, [0.04]]),
    ("viver_de_renda.duracao_em_meses", [1_000_000, 5000, [-0.3, 0.04]]),
    ("viver_de_renda.duracao_em_meses", [1_500_000, 5000, [0.04]]),
    ("viver_de_renda.duracao_em_meses", [120_000, 1000, [0]]),
    ("viver_de_renda.duracao_em_meses", [500_000, 4000, [0.1, -0.2, 0.05, 0.03]]),
    ("viver_de_renda.duracao_em_meses", [1000, 0, [0.04]]),
    ("viver_de_renda.duracao_em_meses", [1000, 100, []]),
    ("viver_de_renda.renda_da_regra_dos_4", [1_200_000]),
]


def _simples(valor: object) -> object:
    """Dataclasses viram dicionários, listas seguem listas (o formato que o TS também devolve)."""
    if dataclasses.is_dataclass(valor) and not isinstance(valor, type):
        return dataclasses.asdict(valor)
    if isinstance(valor, list):
        return [_simples(item) for item in valor]
    return valor


def calcular() -> list[dict[str, Any]]:
    """Os casos com o resultado do Python de agora."""
    resultado = []
    for conta, argumentos in CASOS:
        try:
            saida: Any = {"valor": _simples(CONTAS[conta](*argumentos))}
        except ValueError:
            saida = {"erro": True}
        resultado.append({"conta": conta, "argumentos": argumentos, **saida})
    return resultado


def main() -> None:
    texto = json.dumps(calcular(), ensure_ascii=False, indent=1, sort_keys=True)
    ARQUIVO.write_text(texto + "\n", encoding="utf-8", newline="\n")
    print(f"{len(CASOS)} casos em {ARQUIVO}")


if __name__ == "__main__":
    main()
