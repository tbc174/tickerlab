"""Viver de renda (src/ferramentas/viver_de_renda.py): tudo em dinheiro de hoje (taxa real)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.ferramentas import viver_de_renda as vr
from src.ferramentas.juros import taxa_equivalente


def test_so_com_os_juros_o_dinheiro_nao_acaba():
    i = taxa_equivalente(0.04, 12, 1)
    p = vr.patrimonio_necessario(5000, 0.04, None)
    # a retirada sai no começo do mês e o resto rende: o saldo volta ao mesmo valor
    assert p == pytest.approx(5000 * (1 + i) / i)
    assert vr.duracao_em_meses(p, 5000, [0.04]) is None  # dura mais de 100 anos


def test_gastando_o_principal_em_30_anos_precisa_de_menos():
    perpetuo = vr.patrimonio_necessario(5000, 0.04, None)
    em_30 = vr.patrimonio_necessario(5000, 0.04, 30)
    assert em_30 < perpetuo
    assert vr.duracao_em_meses(em_30, 5000, [0.04]) == 360


def test_sem_rendimento_dura_o_patrimonio_dividido_pela_retirada():
    assert vr.patrimonio_necessario(1000, 0, 10) == pytest.approx(120_000)
    assert vr.duracao_em_meses(120_000, 1000, [0]) == 120
    with pytest.raises(ValueError, match="sem rendimento"):
        vr.patrimonio_necessario(1000, 0, None)


def test_regra_dos_4_por_cento_e_um_caso():
    assert vr.renda_da_regra_dos_4(1_200_000) == pytest.approx(4000)


def test_comecar_num_ano_ruim_encurta_a_duracao():
    p = vr.patrimonio_necessario(5000, 0.04, 30)
    normal = vr.duracao_em_meses(p, 5000, [0.04])
    com_queda = vr.duracao_em_meses(p, 5000, [-0.3, 0.04])
    assert normal == 360
    assert com_queda is not None and com_queda < normal
    # a mesma queda no último ano quase não muda nada
    queda_no_fim = vr.duracao_em_meses(p, 5000, [0.04] * 29 + [-0.3, 0.04])
    assert queda_no_fim is not None and queda_no_fim > com_queda


def test_o_ultimo_retorno_da_lista_vale_para_os_anos_seguintes():
    assert vr.duracao_em_meses(100_000, 1000, [0.1, 0]) == vr.duracao_em_meses(
        100_000, 1000, [0.1, 0, 0, 0]
    )


@pytest.mark.parametrize(
    ("args", "mensagem"),
    [
        ((-1, 0.04, 30), "renda"),
        ((5000, -1, 30), "rendimento"),
        ((5000, 0.04, 0), "prazo"),
        ((5000, 0.04, vr.ANOS_MAXIMOS + 1), "prazo"),
    ],
)
def test_entradas_invalidas(args, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        vr.patrimonio_necessario(*args)


def test_duracao_recusa_lista_vazia_e_retirada_zero():
    with pytest.raises(ValueError, match="retorno"):
        vr.duracao_em_meses(1000, 100, [])
    with pytest.raises(ValueError, match="retirada"):
        vr.duracao_em_meses(1000, 0, [0.04])


@given(
    renda=st.floats(100, 50_000),
    taxa=st.floats(-0.02, 0.08),
    anos=st.integers(1, 60),
)
def test_o_patrimonio_calculado_dura_exatamente_o_prazo(renda, taxa, anos):
    p = vr.patrimonio_necessario(renda, taxa, anos)
    assert vr.duracao_em_meses(p, renda, [taxa]) == anos * 12


# --- ferramentas v2: a trajetória do patrimônio mês a mês ---------------------------------------
def test_trajetoria_so_com_os_juros_fica_reta():
    patrimonio = vr.patrimonio_necessario(5000, 0.04, None)
    saldos = vr.trajetoria(patrimonio, 5000, [0.04], 360)
    assert len(saldos) == 361
    assert saldos[0] == patrimonio
    assert saldos[-1] == pytest.approx(patrimonio, rel=1e-9)


def test_trajetoria_com_queda_no_comeco_acaba_quando_a_duracao_diz():
    patrimonio = vr.patrimonio_necessario(5000, 0.04, None)
    retornos = [-0.3, 0.04]
    saldos = vr.trajetoria(patrimonio, 5000, retornos, 1200)
    duracao = vr.duracao_em_meses(patrimonio, 5000, retornos)
    assert duracao is not None
    assert len(saldos) == duracao + 1
    assert saldos[-1] < 5000  # no último mês não dá mais para tirar a renda inteira


def test_trajetoria_gastando_o_principal_chega_perto_de_zero_no_prazo():
    patrimonio = vr.patrimonio_necessario(5000, 0.04, 30)
    saldos = vr.trajetoria(patrimonio, 5000, [0.04], 1200)
    assert len(saldos) - 1 == 360
    assert saldos[-1] == pytest.approx(0, abs=1e-6)


def test_trajetoria_recusa_horizonte_fora_da_faixa():
    with pytest.raises(ValueError, match="horizonte"):
        vr.trajetoria(1000, 10, [0.04], 0)
