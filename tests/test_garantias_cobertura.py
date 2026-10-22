"""Cobertura das garantias (B-17): a conta pura, com a fórmula exposta e as bordas.

Propriedades que valem para qualquer entrada: haircut maior nunca aumenta a cobertura, sem valor
avaliado a cobertura é zero, e garantia em outra moeda não muda a conta.
"""

from datetime import date
from decimal import Decimal

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.garantias import cobertura
from src.garantias.cobertura import GarantiaParaAConta, calcular_cobertura

HOJE = date(2026, 10, 21)
D = Decimal

valores = st.decimals(min_value=0, max_value=10**9, places=2)
haircuts = st.decimals(min_value=0, max_value=1, places=4)


def _garantia(id="g1", valor="1000", haircut="0.30", onus="100", moeda="BRL", ate=None):
    return GarantiaParaAConta(id, D(valor), D(haircut), D(onus), moeda, ate)


def _conta(garantias, exposicao="500", moeda="BRL"):
    return calcular_cobertura(
        exposicao=None if exposicao is None else D(exposicao),
        moeda=moeda,
        garantias=garantias,
        hoje=HOJE,
    )


def test_caso_fixo_com_resultado_conhecido():
    # 1000 × (1 − 0,30) − 100 = 600; 600 ÷ 500 = 1,2
    resultado = _conta([_garantia()])
    assert D(resultado["cobertura"]) == D("1.2")
    assert resultado["parcelas"][0]["valor_protegido"] == "600.00"
    assert resultado["formula"] == cobertura.FORMULA
    assert resultado["fora_da_conta"] == []


def test_varias_garantias_somam_na_mesma_exposicao():
    resultado = _conta(
        [_garantia("a", "1000", "0", "0"), _garantia("b", "500", "0.5", "0")]
    )
    assert D(resultado["valor_protegido_vigente"]) == D("1250")
    assert D(resultado["cobertura"]) == D("2.5")


def test_onus_maior_que_o_valor_nao_deixa_valor_protegido_negativo():
    assert cobertura.valor_protegido(D(100), D("0.1"), D(500)) == 0


def test_sem_valor_avaliado_a_cobertura_e_zero():
    assert D(_conta([_garantia(valor="0")])["cobertura"]) == 0


def test_sem_exposicao_ou_com_exposicao_zero_nao_calcula():
    for exposicao in (None, "0"):
        resultado = _conta([_garantia()], exposicao=exposicao)
        assert resultado["cobertura"] is None
        assert resultado["cobertura_contando_as_vencidas"] is None


def test_garantia_em_outra_moeda_fica_de_fora_e_diz_por_que():
    resultado = _conta([_garantia("g1"), _garantia("g2", moeda="USD")])
    assert resultado["fora_da_conta"] == [
        {"garantia_id": "g2", "motivo": cobertura.MOTIVO_MOEDA_DIFERENTE}
    ]
    assert D(resultado["cobertura"]) == D("1.2")


def test_validade_so_avisa_e_a_vencida_sai_da_cobertura_vigente():
    vencida = _garantia("velha", ate=date(2026, 10, 20))
    nova = _garantia("nova", ate=date(2027, 12, 31))
    resultado = _conta([vencida, nova])
    assert D(resultado["cobertura"]) == D("1.2")
    assert D(resultado["cobertura_contando_as_vencidas"]) == D("2.4")
    assert resultado["fora_da_conta"] == [
        {"garantia_id": "velha", "motivo": cobertura.MOTIVO_VENCIDA}
    ]
    assert {p["garantia_id"]: p["validade"] for p in resultado["parcelas"]} == {
        "velha": cobertura.VENCIDA,
        "nova": cobertura.VIGENTE,
    }


def test_situacao_da_validade_nos_limites():
    assert cobertura.situacao_da_validade(None, HOJE) == cobertura.SEM_VALIDADE
    assert cobertura.situacao_da_validade(date(2026, 10, 20), HOJE) == cobertura.VENCIDA
    assert cobertura.situacao_da_validade(HOJE, HOJE) == cobertura.VENCE_EM_30_DIAS
    assert (
        cobertura.situacao_da_validade(date(2026, 11, 20), HOJE)
        == cobertura.VENCE_EM_30_DIAS
    )
    assert cobertura.situacao_da_validade(date(2026, 11, 21), HOJE) == cobertura.VIGENTE


@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(valores, haircuts, haircuts, valores, valores)
def test_haircut_maior_nunca_aumenta_a_cobertura(valor, h1, h2, onus, exposicao):
    menor, maior = sorted((h1, h2))
    a = _conta(
        [_garantia(valor=str(valor), haircut=str(menor), onus=str(onus))],
        str(exposicao),
    )
    b = _conta(
        [_garantia(valor=str(valor), haircut=str(maior), onus=str(onus))],
        str(exposicao),
    )
    if a["cobertura"] is None:
        assert b["cobertura"] is None
    else:
        assert D(b["cobertura"]) <= D(a["cobertura"])


@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(haircuts, valores, st.decimals(min_value=1, max_value=10**9, places=2))
def test_cobertura_zero_sem_valor_avaliado_e_nunca_negativa(haircut, onus, exposicao):
    resultado = _conta(
        [_garantia(valor="0", haircut=str(haircut), onus=str(onus))], str(exposicao)
    )
    assert D(resultado["cobertura"]) == 0


@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(valores, haircuts, valores, st.decimals(min_value=1, max_value=10**9, places=2))
def test_acrescentar_garantia_vigente_nunca_diminui_e_moeda_diferente_nao_muda(
    valor, haircut, onus, exposicao
):
    base = [_garantia("a")]
    mais = base + [
        _garantia("b", valor=str(valor), haircut=str(haircut), onus=str(onus))
    ]
    outra_moeda = base + [_garantia("c", moeda="USD", valor=str(valor))]
    assert D(_conta(mais, str(exposicao))["cobertura"]) >= D(
        _conta(base, str(exposicao))["cobertura"]
    )
    assert (
        _conta(outra_moeda, str(exposicao))["cobertura"]
        == _conta(base, str(exposicao))["cobertura"]
    )
