"""Cascata de pagamentos (src/securitizacao/cascata.py), regras da 0.1.0: ordem, perda, determinismo e caixa.

Toda estrutura aqui é sintética (nenhuma operação real).
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.securitizacao.cascata import (
    VERSAO_DO_CALCULO,
    Classe,
    Operacao,
    Periodo,
    juros_devidos,
    reconciliar,
    rodar,
)

R = 100  # centavos por real


def operacao_exemplo() -> Operacao:
    return Operacao(
        classes=[
            Classe("senior", 1, 800_000 * R, 0.010),
            Classe("mezanino", 2, 150_000 * R, 0.015),
            Classe("subordinada", 3, 50_000 * R, 0.0),
        ],
        saldo_do_pool=1_000_000 * R,
        reserva_minima=10_000 * R,
    )


def test_mes_sem_perda_paga_despesas_juros_reserva_e_principal_na_ordem():
    p = Periodo(
        principal_recebido=50_000 * R,
        juros_recebidos=20_000 * R,
        recuperacoes=0,
        perda=0,
        despesas=1_000 * R,
    )
    [r] = rodar(operacao_exemplo(), [p])
    assert r.despesas_pagas == 1_000 * R
    assert r.juros_pagos == {
        "senior": 8_000 * R,
        "mezanino": 2_250 * R,
        "subordinada": 0,
    }
    assert r.reserva_final == 10_000 * R
    # 70.000 - 1.000 (despesas) - 8.000 - 2.250 (juros) - 10.000 (reserva) = 48.750 para principal
    assert r.principal_pago == {"senior": 48_750 * R, "mezanino": 0, "subordinada": 0}
    assert r.residual == 0
    assert r.saldo_das_classes["senior"] == (800_000 - 48_750) * R
    assert r.versao_do_calculo == VERSAO_DO_CALCULO


def test_juros_nao_amortizam_o_que_sobra_vai_ao_residual():
    p = Periodo(
        principal_recebido=0,
        juros_recebidos=30_000 * R,
        recuperacoes=0,
        perda=0,
        despesas=0,
    )
    [r] = rodar(operacao_exemplo(), [p])
    assert sum(r.principal_pago.values()) == 0
    assert r.residual == (30_000 - 8_000 - 2_250 - 10_000) * R


def test_caixa_curto_paga_senior_antes_do_mezanino():
    p = Periodo(
        principal_recebido=0,
        juros_recebidos=9_000 * R,
        recuperacoes=0,
        perda=0,
        despesas=0,
    )
    [r] = rodar(operacao_exemplo(), [p])
    assert r.juros_pagos["senior"] == 8_000 * R
    assert r.juros_pagos["mezanino"] == 1_000 * R  # só o que sobrou
    assert r.reserva_final == 0 and r.residual == 0


def test_perda_abate_a_subordinada_primeiro():
    p = Periodo(
        principal_recebido=0,
        juros_recebidos=0,
        recuperacoes=0,
        perda=80_000 * R,
        despesas=0,
    )
    [r] = rodar(operacao_exemplo(), [p])
    assert r.perda_alocada == {
        "senior": 0,
        "mezanino": 30_000 * R,
        "subordinada": 50_000 * R,
    }
    assert r.saldo_das_classes["subordinada"] == 0
    assert r.saldo_das_classes["mezanino"] == 120_000 * R
    assert r.saldo_do_pool == 920_000 * R


def test_reserva_passa_de_um_periodo_ao_outro():
    periodos = [
        Periodo(0, 12_000 * R, 0, 0, 0),  # sobra 1.750 para a reserva (10.250 de juros)
        Periodo(0, 0, 0, 0, 0),  # nada entra: a reserva paga parte dos juros
    ]
    primeiro, segundo = rodar(operacao_exemplo(), periodos)
    assert primeiro.reserva_final == 1_750 * R
    assert segundo.reserva_inicial == 1_750 * R
    assert segundo.juros_pagos == {"senior": 1_750 * R, "mezanino": 0, "subordinada": 0}
    assert segundo.reserva_final == 0


def test_mesma_entrada_mesmo_resultado():
    periodos = [Periodo(30_000 * R, 15_000 * R, 500 * R, 2_000 * R, 800 * R)] * 12
    a = rodar(operacao_exemplo(), periodos)
    b = rodar(operacao_exemplo(), periodos)
    assert [vars(x) for x in a] == [vars(x) for x in b]


def test_reconciliacao_fecha_em_12_meses():
    periodos = [Periodo(30_000 * R, 15_000 * R, 500 * R, 2_000 * R, 800 * R)] * 12
    totais = reconciliar(0, rodar(operacao_exemplo(), periodos))
    assert totais["diferenca"] == 0
    assert totais["entradas"] == 12 * (30_000 + 15_000 + 500) * R


@pytest.mark.parametrize(
    "classes",
    [
        [],
        [Classe("a", 1, 1, 0.0), Classe("a", 2, 1, 0.0)],
        [Classe("a", 1, -1, 0.0)],
    ],
)
def test_estrutura_invalida_e_recusada(classes):
    with pytest.raises(ValueError):
        Operacao(classes=classes, saldo_do_pool=2, reserva_minima=0)


def test_fluxo_negativo_e_recusado():
    with pytest.raises(ValueError):
        rodar(operacao_exemplo(), [Periodo(-1, 0, 0, 0, 0)])


def test_juros_arredondam_para_baixo_ao_centavo():
    assert juros_devidos(Classe("a", 1, 999, 0.01), 999) == 9


centavos = st.integers(min_value=0, max_value=200_000 * R)


@settings(max_examples=300, deadline=None)
@given(
    saldos=st.lists(
        st.integers(min_value=0, max_value=1_000_000 * R), min_size=1, max_size=5
    ),
    taxas=st.lists(st.floats(min_value=0.0, max_value=0.05), min_size=5, max_size=5),
    reserva_minima=st.integers(min_value=0, max_value=50_000 * R),
    periodos=st.lists(
        st.tuples(centavos, centavos, centavos, centavos, centavos),
        min_size=1,
        max_size=24,
    ),
)
def test_propriedade_conservacao_de_caixa_e_prioridade(
    saldos, taxas, reserva_minima, periodos
):
    classes = [Classe(f"c{i}", i + 1, s, taxas[i]) for i, s in enumerate(saldos)]
    op = Operacao(
        classes=classes, saldo_do_pool=sum(saldos), reserva_minima=reserva_minima
    )
    resultados = rodar(op, [Periodo(*p) for p in periodos])
    # conservação do total ao centavo
    assert reconciliar(0, resultados)["diferenca"] == 0
    for r in resultados:
        # uma classe só recebe juros se a mais sênior recebeu tudo o que lhe era devido
        for c_mais, c_menos in zip(op.ordenadas, op.ordenadas[1:], strict=False):
            if r.juros_pagos[c_menos.nome] > 0:
                saldo_antes = (
                    r.saldo_das_classes[c_mais.nome]
                    + r.principal_pago[c_mais.nome]
                    + r.perda_alocada[c_mais.nome]
                )
                assert r.juros_pagos[c_mais.nome] == juros_devidos(c_mais, saldo_antes)
        assert all(v >= 0 for v in r.saldo_das_classes.values())
        assert r.residual >= 0 and r.reserva_final >= 0
        assert sum(r.saldo_das_classes.values()) <= r.saldo_do_pool
