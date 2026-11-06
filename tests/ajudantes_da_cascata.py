"""A cascata 0.1.0 congelada (#504), só para os testes: o oráculo da propriedade "regras desligadas = 0.1.0".

Cópia fiel do motor sequencial da versão 0.1.0, em tipos simples. Não é usada pelo app; se a 0.2.0 mudar
o resultado de uma estrutura sem as regras novas, o teste que compara com esta cópia falha.
"""

from __future__ import annotations


def rodar_0_1_0(
    classes: list[tuple[str, int, int, float]],
    saldo_do_pool: int,
    reserva_minima: int,
    periodos: list[tuple[int, int, int, int, int]],
    reserva_inicial: int = 0,
) -> list[dict]:
    """Classes como (nome, senioridade, saldo, taxa); períodos como (principal, juros, recuperações, perda, despesas)."""
    ordenadas = sorted(classes, key=lambda c: c[1])
    saldos = {nome: saldo for nome, _, saldo, _ in classes}
    taxas = {nome: taxa for nome, _, _, taxa in classes}
    reserva = reserva_inicial
    resultados = []
    for principal, juros_recebidos, recuperacoes, perda, despesas in periodos:
        entradas = principal + juros_recebidos + recuperacoes
        caixa = reserva + entradas
        despesas_pagas = min(caixa, despesas)
        caixa -= despesas_pagas
        juros_pagos = {}
        for nome, *_ in ordenadas:
            juros_pagos[nome] = min(caixa, int(saldos[nome] * taxas[nome]))
            caixa -= juros_pagos[nome]
        reserva_final = min(caixa, reserva_minima)
        caixa -= reserva_final
        para_principal = min(caixa, principal + recuperacoes)
        principal_pago = {}
        for nome, *_ in ordenadas:
            principal_pago[nome] = min(para_principal, saldos[nome])
            para_principal -= principal_pago[nome]
            saldos[nome] -= principal_pago[nome]
        caixa -= sum(principal_pago.values())
        saldo_do_pool = max(0, saldo_do_pool - principal - perda)
        perda_alocada = {nome: 0 for nome, *_ in classes}
        excesso = sum(saldos.values()) - saldo_do_pool
        for nome, *_ in reversed(ordenadas):
            if excesso <= 0:
                break
            corte = min(excesso, saldos[nome])
            perda_alocada[nome] = corte
            saldos[nome] -= corte
            excesso -= corte
        resultados.append(
            {
                "entradas": entradas,
                "reserva_inicial": reserva,
                "despesas_pagas": despesas_pagas,
                "juros_pagos": juros_pagos,
                "reserva_final": reserva_final,
                "principal_pago": principal_pago,
                "residual": caixa,
                "perda_alocada": perda_alocada,
                "saldo_das_classes": dict(saldos),
                "saldo_do_pool": saldo_do_pool,
            }
        )
        reserva = reserva_final
    return resultados
