"""LBO determinístico (B-25): dois casos de gabarito conferidos à mão (a "planilha" está nos
comentários) e as propriedades do critério de aceite: fontes = usos, MOIC = recebido ÷ investido e
mais alavancagem, com o mesmo resultado, não baixa a TIR quando a dívida custa menos que o ativo rende.
"""

import json
from datetime import date

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from src import lbo as l
from src.divida.simulador import BULLET, PRE, SAC, Instrumento

DIA = date(2026, 1, 2)


def _divida(
    principal: float, taxa: float, prazo_meses: int, amortizacao: str
) -> Instrumento:
    return Instrumento(
        principal, PRE, taxa, prazo_meses, amortizacao, meses_por_periodo=12
    )


# Caso 1: acumula o caixa, dívida pré bullet que vence depois da saída (paga com a venda).
#
# | uso / fonte            | R$  |   Ano | EBITDA | LAIR = EBITDA − 20 − 50 | imposto 34% | fluxo* |
# | preço (100 × 8)        | 800 |     1 |    110 |                      40 |        13,6 |   16,4 |
# | custos                 |  20 |     2 |    120 |                      50 |        17,0 |   23,0 |
# | caixa mínimo           |  30 |     3 |    130 |                      60 |        20,4 |   29,6 |
# | dívida 10% a.a.        | 500 |     4 |    140 |                      70 |        23,8 |   36,2 |
# | capital do acionista   | 350 |     5 |    150 |                      80 |        27,2 |   42,8 |
#
# *fluxo = EBITDA − imposto − capex 25 − capital de giro 5 − juros 50; soma 148 → caixa 30 + 148 = 178.
# Saída: 150 × 8 = 1.200 − dívida 500 + caixa 178 = 878. MOIC = 878 ÷ 350 = 2,508571...;
# TIR = (878 ÷ 350) ^ (1/5) − 1 = 20,19469...%.
CASO_1 = l.PremissasDoLbo(
    ebitda_de_entrada=100.0,
    multiplo_de_entrada=8.0,
    multiplo_de_saida=8.0,
    ebitda=(110.0, 120.0, 130.0, 140.0, 150.0),
    depreciacao=(20.0,) * 5,
    capex=(25.0,) * 5,
    capital_de_giro=(5.0,) * 5,
    aliquota=0.34,
    custos_da_transacao=20.0,
    caixa_minimo=30.0,
    dividas=(_divida(500.0, 0.10, 84, BULLET),),
    politica=l.ACUMULA,
)

# Caso 2: distribui todo ano, dívida pré SAC de 3 anos, sem imposto.
#
# | Ano | EBITDA | saldo inicial | juros 12% | amortização | fluxo = 150 − juros − amortização |
# |   1 |    150 |           300 |        36 |         100 |                                14 |
# |   2 |    150 |           200 |        24 |         100 |                                26 |
# |   3 |    150 |           100 |        12 |         100 |                                38 |
#
# Usos: 100 × 6 = 600; fontes: dívida 300 + acionista 300. Saída: 150 × 6 = 900, sem dívida.
# Fluxo do acionista: −300, 14, 26, 38 + 900 = 938. MOIC = (14 + 26 + 938) ÷ 300 = 3,26.
# TIR: a raiz de −300 + 14/(1+r) + 26/(1+r)² + 938/(1+r)³ = 0 → 49,795319...% (raízes do polinômio).
CASO_2 = l.PremissasDoLbo(
    ebitda_de_entrada=100.0,
    multiplo_de_entrada=6.0,
    multiplo_de_saida=6.0,
    ebitda=(150.0,) * 3,
    depreciacao=(0.0,) * 3,
    capex=(0.0,) * 3,
    capital_de_giro=(0.0,) * 3,
    aliquota=0.0,
    dividas=(_divida(300.0, 0.12, 36, SAC),),
    politica=l.DISTRIBUI,
)


def test_caso_1_acumula_com_divida_bullet():
    r = l.lbo(CASO_1, DIA)
    fu = r.fontes_e_usos
    assert (fu.preco, fu.usos, fu.capital_do_acionista) == (800.0, 850.0, 350.0)
    assert [a.imposto for a in r.anos] == pytest.approx([13.6, 17.0, 20.4, 23.8, 27.2])
    assert [a.fluxo_ao_acionista for a in r.anos] == pytest.approx(
        [16.4, 23.0, 29.6, 36.2, 42.8]
    )
    assert all(a.distribuido == 0 for a in r.anos)
    assert (r.saida.valor_da_empresa, r.saida.divida) == pytest.approx((1200.0, 500.0))
    assert r.saida.caixa == pytest.approx(178.0)
    assert r.fluxos_do_acionista == pytest.approx((-350.0, 0, 0, 0, 0, 878.0))
    assert r.moic == pytest.approx(878 / 350)
    assert r.tir == pytest.approx(0.2019469349355878, abs=1e-9)


def test_caso_2_distribui_com_divida_sac():
    r = l.lbo(CASO_2, DIA)
    assert r.fontes_e_usos.capital_do_acionista == 300.0
    assert [a.juros_pagos for a in r.anos] == pytest.approx([36.0, 24.0, 12.0])
    assert [a.amortizacao for a in r.anos] == pytest.approx([100.0, 100.0, 100.0])
    assert [a.divida_final for a in r.anos] == pytest.approx([200.0, 100.0, 0.0])
    assert r.fluxos_do_acionista == pytest.approx((-300.0, 14.0, 26.0, 938.0))
    assert r.moic == pytest.approx(3.26)
    assert r.tir == pytest.approx(0.49795319648845204, abs=1e-9)
    assert l.valor_presente(r.fluxos_do_acionista, r.tir) == pytest.approx(0, abs=1e-6)


def test_fluxo_negativo_vira_aporte_do_acionista():
    # sem EBITDA no ano 1, os juros de 50 saem do bolso do acionista (o caixa está no mínimo)
    premissas = l.PremissasDoLbo(
        100.0, 8.0, 8.0, (0.0, 200.0), (0.0,) * 2, (0.0,) * 2, (0.0,) * 2, 0.0,
        caixa_minimo=10.0, dividas=(_divida(500.0, 0.10, 84, BULLET),),
    )  # fmt: skip
    r = l.lbo(premissas, DIA)
    assert r.anos[0].distribuido == pytest.approx(-50.0)
    assert r.anos[0].caixa_final == pytest.approx(10.0)
    assert r.investido == pytest.approx(310.0 + 50.0)


def test_saida_negativa_nao_cobra_do_acionista():
    premissas = l.PremissasDoLbo(
        100.0, 8.0, 1.0, (100.0,), (0.0,), (0.0,), (0.0,), 0.0,
        dividas=(_divida(700.0, 0.10, 84, BULLET),),
    )  # fmt: skip
    r = l.lbo(premissas, DIA)
    assert (
        r.saida.valor_do_acionista == 0.0
    )  # 100 − 700 + 30 de caixa: negativo vira zero


def test_rastros_completos_e_json():
    r = l.lbo(CASO_1, DIA)
    for nome, rastro in r.rastros.items():
        assert rastro.o_que_falta() == [], nome
    assert {"tir", "moic", "usos", "juros", "amortizacao"} <= set(r.rastros)
    assert json.loads(json.dumps(r.como_dict()))["como_era_em"] == "2026-01-02"


def test_premissas_vem_do_json_da_api():
    dados = json.loads(json.dumps(CASO_1.como_dict()))
    assert l.PremissasDoLbo.de_dict(dados) == CASO_1


@pytest.mark.parametrize(
    "mudanca",
    [
        {"ebitda": ()},
        {"capex": (1.0,)},
        {"aliquota": 1.0},
        {"multiplo_de_saida": 0.0},
        {"politica": "sacar"},
        {"caixa_minimo": -1.0},
    ],
)
def test_premissas_invalidas_levantam_erro(mudanca: dict):
    with pytest.raises(ValueError):
        l.PremissasDoLbo(**(CASO_1.como_dict() | {"dividas": CASO_1.dividas} | mudanca))


def test_divida_maior_que_os_usos_levanta_erro():
    premissas = l.PremissasDoLbo(
        100.0, 1.0, 1.0, (100.0,), (0.0,), (0.0,), (0.0,), 0.0,
        dividas=(_divida(200.0, 0.10, 12, BULLET),),
    )  # fmt: skip
    with pytest.raises(ValueError, match="passam dos usos"):
        l.lbo(premissas, DIA)


def test_tir_sem_raiz_unica_fica_vazia():
    assert l.tir((-100.0, -10.0)) is None  # só saída de dinheiro
    assert l.tir((-100.0, 230.0, -132.0)) is None  # duas TIRs: 10% e 20%
    assert l.tir((-100.0, 110.0)) == pytest.approx(0.10, abs=1e-9)


def test_nada_aqui_e_preco_alvo_nem_recomendacao():
    texto = (" ".join(l.LIMITES) + (l.__doc__ or "")).lower()
    assert "nada aqui é recomendação" in texto
    for proibido in ("preço-alvo", "recomendamos", "vale r$"):
        assert proibido not in texto


# propriedades

ANOS = st.integers(min_value=1, max_value=8)
DINHEIRO = st.floats(min_value=50.0, max_value=500.0, allow_nan=False)


@st.composite
def _cenarios(desenho: st.DrawFn) -> tuple[l.PremissasDoLbo, float, float, float]:
    """Premissas sem dívida, a taxa da dívida e duas frações de alavancagem (a menor primeiro).

    EBITDA e múltiplo de saída perto dos de entrada (0,7 a 1,5 vez): a TIR fica dentro da faixa
    que a busca cobre (até 1.000% ao ano)."""
    anos = desenho(ANOS)
    entrada, multiplo = desenho(DINHEIRO), desenho(st.floats(4.0, 12.0))
    ebitda = tuple(entrada * desenho(st.floats(0.7, 1.5)) for _ in range(anos))
    capex = tuple(e * desenho(st.floats(0.0, 0.3)) for e in ebitda)
    premissas = l.PremissasDoLbo(
        ebitda_de_entrada=entrada,
        multiplo_de_entrada=multiplo,
        multiplo_de_saida=multiplo * desenho(st.floats(0.7, 1.5)),
        ebitda=ebitda,
        depreciacao=tuple(c * 0.8 for c in capex),
        capex=capex,
        capital_de_giro=(0.0,) * anos,
        aliquota=desenho(st.sampled_from((0.0, 0.34))),
        custos_da_transacao=desenho(st.floats(0.0, 30.0)),
        caixa_minimo=desenho(st.floats(0.0, 30.0)),
        politica=desenho(st.sampled_from(l.POLITICAS)),
    )
    taxa = desenho(st.floats(0.0, 0.3))
    menor = desenho(st.floats(0.0, 0.7))
    maior = desenho(st.floats(menor, 0.8))
    return premissas, taxa, menor, maior


def _com_divida(premissas: l.PremissasDoLbo, taxa: float, fracao: float, anos: int):
    usos = l.lbo(premissas, DIA).fontes_e_usos.usos
    if fracao * usos <= 0:
        return premissas
    # bullet que vence depois da saída: só juros até lá, o principal sai da venda
    divida = _divida(fracao * usos, taxa, 12 * (anos + 1), BULLET)
    return l.PremissasDoLbo(**(premissas.como_dict() | {"dividas": (divida,)}))


def _convencional(fluxos: tuple[float, ...]) -> bool:
    """Investe no ano 0 e só recebe depois (uma troca de sinal): a TIR é única."""
    return fluxos[0] < 0 and all(f >= 0 for f in fluxos[1:]) and fluxos[-1] > 0


@settings(max_examples=200, deadline=None)
@given(cenario=_cenarios())
def test_mais_alavancagem_nao_baixa_a_tir_quando_a_divida_custa_menos(cenario):
    premissas, taxa, menor, maior = cenario
    sem_divida = l.lbo(premissas, DIA)
    assume(_convencional(sem_divida.fluxos_do_acionista))
    assume(sem_divida.tir is not None and taxa < sem_divida.tir - 1e-6)
    resultados = [
        l.lbo(_com_divida(premissas, taxa, f, premissas.anos), DIA)
        for f in (menor, maior)
    ]
    assume(all(_convencional(r.fluxos_do_acionista) for r in resultados))
    pouca, muita = resultados
    assert pouca.tir is not None and muita.tir is not None
    assert muita.tir >= pouca.tir - 1e-9
    assert pouca.tir >= sem_divida.tir - 1e-9


@settings(max_examples=200, deadline=None)
@given(cenario=_cenarios())
def test_fontes_iguais_aos_usos_e_moic_e_recebido_sobre_investido(cenario):
    premissas, taxa, _, maior = cenario
    r = l.lbo(_com_divida(premissas, taxa, maior, premissas.anos), DIA)
    assert r.fontes_e_usos.fontes == pytest.approx(r.fontes_e_usos.usos)
    if r.moic is not None:
        assert r.moic == pytest.approx(r.recebido / r.investido)
        assert r.investido >= r.fontes_e_usos.capital_do_acionista - 1e-9
