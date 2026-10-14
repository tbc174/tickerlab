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

from src.ferramentas import (
    aleatorio,
    aportes,
    custos,
    darf,
    inflacao,
    juros,
    moedas,
    renda_fixa,
    taxas,
)
from src.ferramentas import sorte_em_serie as sorte
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
    "juros.em_reais_de_hoje": juros.em_reais_de_hoje,
    "juros.liquido_de_ir": juros.liquido_de_ir,
    "aportes.valor_futuro": aportes.valor_futuro,
    "aportes.aporte_para_meta": aportes.aporte_para_meta,
    "aportes.meses_ate_meta": aportes.meses_ate_meta,
    "aportes.evolucao": aportes.evolucao,
    "aportes.mes_da_virada": aportes.mes_da_virada,
    "custos.custo_da_taxa": custos.custo_da_taxa,
    "custos.evolucao_da_taxa": custos.evolucao_da_taxa,
    "custos.alta_para_recuperar": custos.alta_para_recuperar,
    "viver_de_renda.patrimonio_necessario": vr.patrimonio_necessario,
    "viver_de_renda.duracao_em_meses": vr.duracao_em_meses,
    "viver_de_renda.renda_da_regra_dos_4": vr.renda_da_regra_dos_4,
    "viver_de_renda.trajetoria": vr.trajetoria,
    "aleatorio.sequencia": aleatorio.sequencia,
    "sorte_em_serie.sharpe": sorte.sharpe,
    "sorte_em_serie.simular": sorte.simular,
    # o DARF recebe o mês e os saldos como dicionários (os campos que faltam ficam em zero)
    "darf.apurar_mes": lambda mes, saldos: darf.apurar_mes(
        darf.Mes(**mes), darf.Saldos(**saldos)
    ),
    "darf.apurar_meses": lambda meses, saldos: darf.apurar_meses(
        [darf.Mes(**m) for m in meses], darf.Saldos(**saldos)
    ),
    "darf.vencimento": darf.vencimento,
    "moedas.converter": moedas.converter,
    "taxas.juro_real": taxas.juro_real,
    "taxas.taxa_nominal": taxas.taxa_nominal,
    "inflacao.corrigir": inflacao.corrigir,
    "inflacao.em_12_meses": inflacao.em_12_meses,
    "renda_fixa.comparar": renda_fixa.comparar,
}

IPCA_DE_EXEMPLO = [
    ["2024-11", 0.0039],
    ["2024-12", 0.0052],
    ["2025-01", 0.0016],
    ["2025-02", 0.0131],
]
COTACOES_DE_EXEMPLO = {"USD": 5.0096, "EUR": 5.6092, "JPY": 0.03163, "GBP": 6.6387}
DOZE_MESES = [[f"2025-{m:02d}", 0.003 + m / 10000] for m in range(1, 13)]

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
    ("juros.em_reais_de_hoje", [25937.424601, 0.04, 120]),
    ("juros.em_reais_de_hoje", [5000, 0, 120]),
    ("juros.em_reais_de_hoje", [5000, 0.1, 0]),
    ("juros.em_reais_de_hoje", [1e6, 0.0456, 7]),
    ("juros.em_reais_de_hoje", [1000, -0.02, 36]),
    ("juros.em_reais_de_hoje", [1000, -1, 12]),
    ("juros.liquido_de_ir", [10000, 12697.346485319147, 24]),
    ("juros.liquido_de_ir", [10000, 10615.201506010002, 6]),
    ("juros.liquido_de_ir", [10000, 10500, 5]),
    ("juros.liquido_de_ir", [10000, 11500, 12]),
    ("juros.liquido_de_ir", [10000, 11500, 13]),
    ("juros.liquido_de_ir", [10000, 9000, 12]),
    ("juros.liquido_de_ir", [10000, 10000, 0]),
    ("juros.liquido_de_ir", [10000, 10100, 0]),
    ("juros.liquido_de_ir", [1e6, 3e6, 600]),
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
    ("aportes.valor_futuro", [0, 500, 0.005, 24, False, 0.10]),
    ("aportes.valor_futuro", [20000, 1000, 0.007, 360, True, 0.05]),
    ("aportes.valor_futuro", [0, 500, 0.005, 36, False, -0.5]),
    ("aportes.valor_futuro", [0, 500, 0.005, 36, False, -1]),
    ("aportes.aporte_para_meta", [1000000, 10000, 0.006, 300, False, 0.04]),
    ("aportes.aporte_para_meta", [500000, 0, 0, 240, True, 0.03]),
    ("aportes.meses_ate_meta", [100000, 0, 500, 0.005, False, 0.05]),
    ("aportes.meses_ate_meta", [1e6, 5000, 1000, 0.006, True, 0.08]),
    ("aportes.evolucao", [1000, 500, 0.005, 26, False, 0.10]),
    ("aportes.mes_da_virada", [0, 500, 0.005, 1200, False, 0]),
    ("aportes.mes_da_virada", [0, 500, 0.005, 1200, True, 0]),
    ("aportes.mes_da_virada", [10000, 500, 0.008, 600, False, 0.05]),
    ("aportes.mes_da_virada", [0, 500, 0, 600, False, 0]),
    ("aportes.mes_da_virada", [0, 500, 0.005, 100, False, 0]),
    ("aportes.mes_da_virada", [100000, 0, 0.01, 12, False, 0]),
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
    ("viver_de_renda.trajetoria", [1500000, 5000, [0.04], 36]),
    ("viver_de_renda.trajetoria", [500000, 5000, [-0.3, 0.04], 1200]),
    ("viver_de_renda.trajetoria", [100000, 1000, [0], 200]),
    ("viver_de_renda.trajetoria", [3000, 5000, [0.04], 12]),
    ("viver_de_renda.trajetoria", [1000, 10, [0.04], 0]),
    ("viver_de_renda.trajetoria", [1000, 0, [0.04], 12]),
    ("viver_de_renda.trajetoria", [1000, 10, [], 12]),
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
    ("aleatorio.sequencia", [42, 1000]),
    ("aleatorio.sequencia", [0, 50]),
    ("aleatorio.sequencia", [2**32 - 1, 50]),
    ("sorte_em_serie.sharpe", [[0.01, 0.01, -0.01, 0.01]]),
    ("sorte_em_serie.sharpe", [[0.01, -0.01, 0.01, -0.01]]),
    ("sorte_em_serie.simular", [100, 250, 42]),
    ("sorte_em_serie.simular", [20, 60, 7]),
    ("sorte_em_serie.simular", [500, 30, 123456]),
    ("sorte_em_serie.simular", [1, 250, 42]),
    ("sorte_em_serie.simular", [100, 1, 42]),
    ("darf.apurar_mes", [{"vendas_comuns": 15000, "resultado_comum": 2000}, {}]),
    ("darf.apurar_mes", [{"vendas_comuns": 20000, "resultado_comum": 2000}, {}]),
    ("darf.apurar_mes", [{"vendas_comuns": 20000.01, "resultado_comum": 2000}, {}]),
    (
        "darf.apurar_mes",
        [{"vendas_comuns": 30000, "resultado_comum": 3000, "irrf_comum": 1.5}, {}],
    ),
    (
        "darf.apurar_mes",
        [{"vendas_comuns": 15000, "resultado_comum": 2000}, {"prejuizo_comum": 800}],
    ),
    (
        "darf.apurar_mes",
        [
            {"resultado_day_trade": 1000, "irrf_day_trade": 10},
            {"prejuizo_day_trade": 300},
        ],
    ),
    (
        "darf.apurar_mes",
        [
            {
                "vendas_comuns": 50000,
                "resultado_comum": 1000,
                "resultado_day_trade": -1000,
            },
            {"irrf_a_compensar": 3, "imposto_abaixo_do_minimo": 4},
        ],
    ),
    ("darf.apurar_mes", [{"vendas_comuns": 30000, "resultado_comum": 40}, {}]),
    ("darf.apurar_mes", [{"vendas_comuns": -1}, {}]),
    ("darf.apurar_mes", [{}, {"imposto_abaixo_do_minimo": 10}]),
    ("darf.apurar_mes", [{}, {"prejuizo_comum": -5}]),
    (
        "darf.apurar_meses",
        [
            [
                {"vendas_comuns": 25000, "resultado_comum": -2000, "irrf_comum": 1.25},
                {"vendas_comuns": 40000, "resultado_comum": 3000, "irrf_comum": 2},
                {"vendas_comuns": 18000, "resultado_comum": 900},
                {"vendas_comuns": 30000, "resultado_comum": 40},
                {
                    "vendas_comuns": 30000,
                    "resultado_comum": 40,
                    "resultado_day_trade": 500,
                },
            ],
            {},
        ],
    ),
    ("darf.vencimento", [2026, 10]),
    ("darf.vencimento", [2026, 12]),
    ("moedas.converter", [100, "USD", "BRL", COTACOES_DE_EXEMPLO]),
    ("moedas.converter", [1000, "BRL", "EUR", COTACOES_DE_EXEMPLO]),
    ("moedas.converter", [250, "GBP", "JPY", COTACOES_DE_EXEMPLO]),
    ("moedas.converter", [1, "BRL", "BRL", COTACOES_DE_EXEMPLO]),
    ("moedas.converter", [1, "ARS", "BRL", COTACOES_DE_EXEMPLO]),
    ("taxas.juro_real", [0.1375, 0.05]),
    ("taxas.juro_real", [0.06, 0.08]),
    ("taxas.juro_real", [0.1, -1]),
    ("taxas.taxa_nominal", [0.05, 0.045]),
    ("taxas.taxa_nominal", [-1, 0.045]),
    ("inflacao.corrigir", [100, "2024-12", "2025-02", IPCA_DE_EXEMPLO]),
    ("inflacao.corrigir", [2500.5, "2024-11", "2024-11", IPCA_DE_EXEMPLO]),
    ("inflacao.corrigir", [100, "2025-02", "2024-12", IPCA_DE_EXEMPLO]),
    ("inflacao.corrigir", [100, "2024-10", "2024-12", IPCA_DE_EXEMPLO]),
    ("inflacao.corrigir", [100, "2024-12", "2025-03", IPCA_DE_EXEMPLO]),
    ("inflacao.corrigir", [100, "2024-13", "2025-01", IPCA_DE_EXEMPLO]),
    ("inflacao.em_12_meses", [DOZE_MESES]),
    ("inflacao.em_12_meses", [DOZE_MESES[:11]]),
    ("renda_fixa.comparar", [10000, 365, 0.1365, 1.0, 0.9, 0.006704]),
    ("renda_fixa.comparar", [10000, 90, 0.1365, 1.1, 0.92, 0.006704]),
    ("renda_fixa.comparar", [5000, 180, 0.1365, 1.0, 0.9, 0.006704]),
    ("renda_fixa.comparar", [5000, 181, 0.1365, 1.0, 0.9, 0.006704]),
    ("renda_fixa.comparar", [50000, 721, 0.105, 1.15, 0.95, 0.005]),
    ("renda_fixa.comparar", [1000, 29, 0.1365, 1.0, 0.9, 0.006704]),
    ("renda_fixa.comparar", [1000, 3650, 0.1365, 1.0, 0.9, 0.006704]),
    ("renda_fixa.comparar", [1000, 0, 0.1365, 1.0, 0.9, 0.006704]),
    ("renda_fixa.comparar", [1000, 365, 0.1365, -0.1, 0.9, 0.006704]),
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
