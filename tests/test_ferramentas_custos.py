"""Custo das taxas e da queda (src/ferramentas/custos.py)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.ferramentas import custos


def test_taxa_de_1_por_cento_em_20_anos():
    r = custos.custo_da_taxa(100_000, 0.08, 0.01, 20)
    assert r.sem_taxa == pytest.approx(100_000 * 1.08**20)
    assert r.com_taxa == pytest.approx(100_000 * (1.08 * 0.99) ** 20)
    assert r.ficou_com_a_taxa == pytest.approx(r.sem_taxa - r.com_taxa)
    # 1% ao ano leva quase um quinto do resultado em 20 anos
    assert r.fracao_do_resultado == pytest.approx(1 - 0.99**20)


def test_taxa_zero_nao_custa_nada():
    r = custos.custo_da_taxa(1000, 0.1, 0, 10)
    assert r.ficou_com_a_taxa == 0
    assert r.fracao_do_resultado == 0


def test_evolucao_ano_a_ano():
    linhas = custos.evolucao_da_taxa(1000, 0.1, 0.02, 3)
    assert [linha.ano for linha in linhas] == [0, 1, 2, 3]
    assert linhas[0] == custos.LinhaDaTaxa(ano=0, sem_taxa=1000, com_taxa=1000)
    assert linhas[1].com_taxa == pytest.approx(1000 * 1.1 * 0.98)
    assert linhas[3].sem_taxa == pytest.approx(1331)


@pytest.mark.parametrize(
    ("queda", "alta"),
    [(-0.1, 1 / 0.9 - 1), (-0.2, 0.25), (-0.5, 1.0), (-0.8, 4.0), (0, 0)],
)
def test_alta_para_recuperar_a_queda(queda, alta):
    assert custos.alta_para_recuperar(queda) == pytest.approx(alta)


@pytest.mark.parametrize("queda", [-1, -1.5, 0.1])
def test_queda_fora_da_faixa_da_erro(queda):
    with pytest.raises(ValueError, match="queda"):
        custos.alta_para_recuperar(queda)


@pytest.mark.parametrize(
    ("capital", "retorno", "taxa", "anos", "mensagem"),
    [
        (-1, 0.08, 0.01, 20, "capital"),
        (1000, -1, 0.01, 20, "retorno"),
        (1000, 0.08, -0.01, 20, "taxa"),
        (1000, 0.08, 1, 20, "taxa"),
        (1000, 0.08, 0.01, -1, "prazo"),
        (1000, 0.08, 0.01, custos.ANOS_MAXIMOS + 1, "prazo"),
    ],
)
def test_entradas_invalidas(capital, retorno, taxa, anos, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        custos.custo_da_taxa(capital, retorno, taxa, anos)


@given(queda=st.floats(-0.99, 0))
def test_subir_o_que_a_queda_pede_volta_ao_valor_de_antes(queda):
    assert (1 + queda) * (1 + custos.alta_para_recuperar(queda)) == pytest.approx(1)
