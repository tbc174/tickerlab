"""Cascata 0.2.0 (src/securitizacao/cascata.py): juros que acumulam, pro rata, gatilho de perda e turbo.

Um teste por regra, escrito antes do código, e as propriedades: o caixa conserva ao centavo, nenhuma classe
recebe mais do que deve e, com as regras novas desligadas, o resultado é o da 0.1.0. Toda estrutura aqui é
sintética (nenhuma operação real).
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.securitizacao.cascata import (
    REGRAS_DA_0_1_0,
    VERSAO_DO_CALCULO,
    Classe,
    Operacao,
    Periodo,
    Regras,
    ratear,
    reconciliar,
    rodar,
)
from tests.ajudantes_da_cascata import rodar_0_1_0

R = 100  # centavos por real


def _so_juros(juros: int) -> Periodo:
    return Periodo(
        principal_recebido=0, juros_recebidos=juros, recuperacoes=0, perda=0, despesas=0
    )


def _tres_classes(regras: Regras, reserva_minima: int = 0) -> Operacao:
    return Operacao(
        classes=[
            Classe("senior", 1, 800_000 * R, 0.010),
            Classe("mezanino", 2, 150_000 * R, 0.015),
            Classe("subordinada", 3, 50_000 * R, 0.0),
        ],
        saldo_do_pool=1_000_000 * R,
        reserva_minima=reserva_minima,
        regras=regras,
    )


def test_versao_e_a_0_2_0():
    assert VERSAO_DO_CALCULO == "cascata 0.2.0"


# Regra 1: juros não pagos acumulam


def test_juros_nao_pagos_acumulam_corrigidos_pela_taxa_e_saem_antes_do_principal():
    op = _tres_classes(Regras(juros_acumulam=True))
    primeiro, segundo = rodar(
        op,
        [
            _so_juros(9_000 * R),  # sênior leva 8.000; o mezanino só 1.000 dos 2.250
            Periodo(5_000 * R, 11_000 * R, 0, 0, 0),
        ],
    )
    assert primeiro.juros_pagos["mezanino"] == 1_000 * R
    assert primeiro.juros_em_atraso == {
        "senior": 0,
        "mezanino": 1_250 * R,
        "subordinada": 0,
    }
    # 2.250 do mês + 1.250 em atraso + 1,5% sobre o atraso (18,75)
    assert segundo.juros_devidos["mezanino"] == 225_000 + 125_000 + 1_875
    assert segundo.juros_pagos["mezanino"] == 351_875
    assert segundo.juros_em_atraso["mezanino"] == 0
    # 16.000 de caixa - 8.000 (sênior) - 3.518,75 (mezanino) = 4.481,25 de principal, menos que os 5.000
    assert segundo.principal_pago["senior"] == 1_600_000 - 800_000 - 351_875


def test_sem_a_regra_o_juro_que_falta_se_perde_como_na_0_1_0():
    primeiro, segundo = rodar(
        _tres_classes(Regras()), [_so_juros(9_000 * R), _so_juros(20_000 * R)]
    )
    assert primeiro.juros_em_atraso["mezanino"] == 0
    assert segundo.juros_pagos["mezanino"] == 2_250 * R


def test_atraso_continua_devido_quando_o_caixa_nao_chega():
    op = _tres_classes(Regras(juros_acumulam=True))
    resultados = rodar(op, [_so_juros(8_000 * R), _so_juros(8_000 * R)])
    # o mezanino nada recebe: 2.250 viram atraso; no mês seguinte, 2.250 + 2.250 + 33,75
    assert resultados[1].juros_em_atraso["mezanino"] == 225_000 + 225_000 + 3_375


# Regra 2: pro rata entre classes da mesma senioridade


def _duas_seniores(regras: Regras = REGRAS_DA_0_1_0) -> Operacao:
    return Operacao(
        classes=[
            Classe("senior_a", 1, 600_000 * R, 0.010),
            Classe("senior_b", 1, 200_000 * R, 0.010),
            Classe("subordinada", 2, 200_000 * R, 0.0),
        ],
        saldo_do_pool=1_000_000 * R,
        reserva_minima=0,
        regras=regras,
    )


def test_mesma_senioridade_divide_juros_curtos_pelo_devido():
    [r] = rodar(_duas_seniores(), [_so_juros(4_000 * R)])
    assert r.juros_pagos == {
        "senior_a": 3_000 * R,
        "senior_b": 1_000 * R,
        "subordinada": 0,
    }


def test_mesma_senioridade_divide_o_principal_pelo_saldo():
    [r] = rodar(_duas_seniores(), [Periodo(40_000 * R, 8_000 * R, 0, 0, 0)])
    assert r.principal_pago == {
        "senior_a": 30_000 * R,
        "senior_b": 10_000 * R,
        "subordinada": 0,
    }


def test_mesma_senioridade_divide_a_perda_pelo_saldo():
    [r] = rodar(_duas_seniores(), [Periodo(0, 0, 0, 300_000 * R, 0)])
    assert r.perda_alocada == {
        "senior_a": 75_000 * R,
        "senior_b": 25_000 * R,
        "subordinada": 200_000 * R,
    }


def test_rateio_fecha_ao_centavo_pelos_maiores_restos():
    assert ratear(100, {"a": 1, "b": 1, "c": 1}) == {"a": 34, "b": 33, "c": 33}
    assert ratear(10, {"a": 3, "b": 0}) == {"a": 10, "b": 0}
    assert ratear(7, {"a": 0, "b": 0}) == {"a": 0, "b": 0}


# Regra 3: gatilho de perda acumulada


def _senior_e_sub(regras: Regras) -> Operacao:
    return Operacao(
        classes=[
            Classe("senior", 1, 800_000 * R, 0.0),
            Classe("subordinada", 2, 200_000 * R, 0.0),
        ],
        saldo_do_pool=1_000_000 * R,
        reserva_minima=0,
        regras=regras,
    )


def test_gatilho_de_perda_troca_pro_rata_por_sequencial_e_nao_volta():
    op = _senior_e_sub(Regras(principal="pro_rata", gatilho_de_perda=0.05))
    um, dois, tres = rodar(
        op,
        [
            Periodo(10_000 * R, 0, 0, 60_000 * R, 0),  # 6% do pool original
            Periodo(10_000 * R, 0, 0, 0, 0),
            Periodo(10_000 * R, 0, 0, 0, 0),
        ],
    )
    # no mês da perda, o gatilho ainda não conhece a perda: pro rata pelo saldo (80% e 20%)
    assert um.regime == "pro_rata" and not um.gatilho_disparado
    assert um.principal_pago == {"senior": 8_000 * R, "subordinada": 2_000 * R}
    assert dois.regime == "sequencial" and dois.gatilho_disparado
    assert dois.principal_pago == {"senior": 10_000 * R, "subordinada": 0}
    assert tres.regime == "sequencial"


def test_perda_igual_ao_limite_nao_dispara():
    op = _senior_e_sub(Regras(principal="pro_rata", gatilho_de_perda=0.05))
    _, dois = rodar(
        op, [Periodo(0, 0, 0, 50_000 * R, 0), Periodo(10_000 * R, 0, 0, 0, 0)]
    )
    assert dois.regime == "pro_rata"


# Regra 4: sobrecolateralização com turbo


def test_turbo_usa_o_excesso_de_juros_para_amortizar_a_senior_ate_a_meta():
    op = Operacao(
        classes=[
            Classe("senior", 1, 800_000 * R, 0.010),
            Classe("subordinada", 2, 200_000 * R, 0.0),
        ],
        saldo_do_pool=1_000_000 * R,
        reserva_minima=0,
        regras=Regras(meta_de_sobrecolateralizacao=0.25),
    )
    [r] = rodar(op, [_so_juros(30_000 * R)])
    # meta: a sênior ≤ 75% do pool (750.000); faltam 50.000 e sobram 22.000 depois dos juros
    assert r.turbo_pago == {"senior": 22_000 * R, "subordinada": 0}
    assert r.principal_pago["senior"] == 22_000 * R
    assert r.residual == 0


def test_turbo_para_quando_a_meta_esta_cumprida():
    op = Operacao(
        classes=[
            Classe("senior", 1, 800_000 * R, 0.010),
            Classe("subordinada", 2, 200_000 * R, 0.0),
        ],
        saldo_do_pool=1_000_000 * R,
        reserva_minima=0,
        regras=Regras(meta_de_sobrecolateralizacao=0.15),
    )
    [r] = rodar(op, [_so_juros(30_000 * R)])
    assert sum(r.turbo_pago.values()) == 0
    assert r.residual == 22_000 * R


@pytest.mark.parametrize(
    "regras",
    [
        {"principal": "turbo"},
        {"gatilho_de_perda": 0.0},
        {"gatilho_de_perda": 1.5},
        {"meta_de_sobrecolateralizacao": -0.1},
        {"meta_de_sobrecolateralizacao": 1.0},
    ],
)
def test_regras_invalidas_sao_recusadas(regras):
    with pytest.raises(ValueError):
        Regras(**regras)


# Propriedades

centavos = st.integers(min_value=0, max_value=200_000 * R)
fluxos = st.lists(
    st.tuples(centavos, centavos, centavos, centavos, centavos), min_size=1, max_size=24
)
regras_quaisquer = st.builds(
    Regras,
    juros_acumulam=st.booleans(),
    principal=st.sampled_from(["sequencial", "pro_rata"]),
    gatilho_de_perda=st.none() | st.floats(min_value=0.001, max_value=1.0),
    meta_de_sobrecolateralizacao=st.none() | st.floats(min_value=0.0, max_value=0.9),
)
classes_quaisquer = st.lists(
    st.tuples(
        st.integers(min_value=0, max_value=1_000_000 * R),
        st.integers(min_value=1, max_value=3),  # senioridade repetida vale
        st.floats(min_value=0.0, max_value=0.05),
    ),
    min_size=1,
    max_size=5,
)


def _operacao(classes, reserva_minima, regras) -> Operacao:
    return Operacao(
        classes=[
            Classe(f"c{i}", sen, saldo, taxa)
            for i, (saldo, sen, taxa) in enumerate(classes)
        ],
        saldo_do_pool=sum(saldo for saldo, _, _ in classes),
        reserva_minima=reserva_minima,
        regras=regras,
    )


@settings(max_examples=300, deadline=None)
@given(
    classes=classes_quaisquer,
    reserva_minima=st.integers(min_value=0, max_value=50_000 * R),
    regras=regras_quaisquer,
    periodos=fluxos,
)
def test_propriedade_caixa_conserva_ao_centavo_com_qualquer_regra(
    classes, reserva_minima, regras, periodos
):
    resultados = rodar(
        _operacao(classes, reserva_minima, regras), [Periodo(*p) for p in periodos]
    )
    assert reconciliar(0, resultados)["diferenca"] == 0
    for r in resultados:
        assert r.reserva_inicial + r.entradas == r.saidas + r.reserva_final
        dinheiro = [r.residual, r.reserva_final, r.despesas_pagas]
        for campo in (
            r.juros_pagos,
            r.principal_pago,
            r.perda_alocada,
            r.juros_em_atraso,
        ):
            dinheiro.extend(campo.values())
        assert all(type(v) is int and v >= 0 for v in dinheiro)  # centavos inteiros


@settings(max_examples=300, deadline=None)
@given(
    classes=classes_quaisquer,
    reserva_minima=st.integers(min_value=0, max_value=50_000 * R),
    regras=regras_quaisquer,
    periodos=fluxos,
)
def test_propriedade_nenhuma_classe_recebe_mais_do_que_deve(
    classes, reserva_minima, regras, periodos
):
    op = _operacao(classes, reserva_minima, regras)
    resultados = rodar(op, [Periodo(*p) for p in periodos])
    for r in resultados:
        for c in op.classes:
            assert r.juros_pagos[c.nome] <= r.juros_devidos[c.nome]
            saldo_antes = (
                r.saldo_das_classes[c.nome]
                + r.principal_pago[c.nome]
                + r.perda_alocada[c.nome]
            )
            assert r.principal_pago[c.nome] <= saldo_antes
            assert r.turbo_pago[c.nome] <= r.principal_pago[c.nome]
    for c in op.classes:
        assert sum(r.principal_pago[c.nome] for r in resultados) <= c.saldo_inicial


@settings(max_examples=300, deadline=None)
@given(
    saldos=st.lists(
        st.integers(min_value=0, max_value=1_000_000 * R), min_size=1, max_size=5
    ),
    taxas=st.lists(st.floats(min_value=0.0, max_value=0.05), min_size=5, max_size=5),
    reserva_minima=st.integers(min_value=0, max_value=50_000 * R),
    reserva_inicial=st.integers(min_value=0, max_value=50_000 * R),
    periodos=fluxos,
)
def test_propriedade_regras_desligadas_dao_o_resultado_da_0_1_0(
    saldos, taxas, reserva_minima, reserva_inicial, periodos
):
    classes = [(f"c{i}", i + 1, s, taxas[i]) for i, s in enumerate(saldos)]
    op = Operacao(
        classes=[Classe(*c) for c in classes],
        saldo_do_pool=sum(saldos),
        reserva_minima=reserva_minima,
        reserva_inicial=reserva_inicial,
    )
    novos = rodar(op, [Periodo(*p) for p in periodos])
    antigos = rodar_0_1_0(
        classes, sum(saldos), reserva_minima, periodos, reserva_inicial
    )
    assert [
        {k: vars(r)[k] for k in a} for r, a in zip(novos, antigos, strict=True)
    ] == antigos
