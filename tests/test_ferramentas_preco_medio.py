"""A calculadora de preço médio do site (src/ferramentas/preco_medio.py): as mesmas regras do custo
médio do app (src/dividendos_e_custo.py), com a corretagem e as taxas no custo, como a Receita manda.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.ferramentas import preco_medio as pm


def _op(tipo, quantidade, preco=0.0, custos=0.0):
    return pm.Operacao(tipo, quantidade, preco, custos)


def test_compras_fazem_a_media_com_as_taxas_no_custo():
    linhas = pm.calcular([_op("compra", 100, 10, 5), _op("compra", 100, 20, 5)])
    assert linhas[-1].quantidade == 200
    assert linhas[-1].custo_total == pytest.approx(1000 + 5 + 2000 + 5)
    assert linhas[-1].preco_medio == pytest.approx(3010 / 200)


def test_venda_nao_muda_o_preco_medio_e_da_o_resultado():
    linhas = pm.calcular([_op("compra", 100, 10, 0), _op("venda", 40, 15, 2)])
    venda = linhas[-1]
    assert venda.preco_medio == pytest.approx(10)
    assert venda.quantidade == 60
    assert venda.resultado == pytest.approx(40 * 15 - 2 - 40 * 10)


def test_vender_tudo_zera_e_a_proxima_compra_recomeca_a_media():
    linhas = pm.calcular(
        [_op("compra", 10, 10), _op("venda", 10, 12), _op("compra", 10, 30)]
    )
    assert linhas[1].preco_medio is None
    assert linhas[2].preco_medio == pytest.approx(30)


def test_bonificacao_entra_com_o_valor_atribuido_pela_empresa():
    linhas = pm.calcular([_op("compra", 100, 10), _op("bonificacao", 10, 5)])
    assert linhas[-1].quantidade == 110
    assert linhas[-1].custo_total == pytest.approx(1000 + 50)


def test_desdobro_e_grupamento_so_mudam_a_quantidade():
    linhas = pm.calcular(
        [_op("compra", 100, 10), _op("desdobro", 100), _op("grupamento", 150)]
    )
    assert linhas[1].preco_medio == pytest.approx(5)
    assert linhas[2].quantidade == 50
    assert linhas[2].custo_total == pytest.approx(1000)


def test_amortizacao_de_fii_reduz_o_custo_sem_mudar_a_quantidade():
    # R$ 0,50 por cota amortizados em 100 cotas: o custo cai R$ 50
    linhas = pm.calcular([_op("compra", 100, 10), _op("amortizacao", 0, 0.5)])
    assert linhas[-1].quantidade == 100
    assert linhas[-1].custo_total == pytest.approx(950)
    assert linhas[-1].preco_medio == pytest.approx(9.5)


def test_amortizacao_acima_do_custo_para_em_zero():
    linhas = pm.calcular([_op("compra", 10, 1), _op("amortizacao", 0, 5)])
    assert linhas[-1].custo_total == 0


def test_vender_mais_do_que_tem_e_erro_claro():
    with pytest.raises(ValueError, match="mais ações do que"):
        pm.calcular([_op("compra", 10, 10), _op("venda", 11, 10)])


def test_tipo_desconhecido_e_erro():
    with pytest.raises(ValueError, match="tipo"):
        pm.calcular([_op("aluguel", 10, 10)])


@given(
    st.lists(
        st.tuples(st.integers(1, 1000), st.floats(0.01, 1000)), min_size=1, max_size=10
    ),
    st.data(),
)
def test_vender_uma_parte_nunca_muda_o_preco_medio(compras, dados):
    ops = [_op("compra", q, p) for q, p in compras]
    antes = pm.calcular(ops)[-1]
    vendida = (
        dados.draw(st.integers(1, int(antes.quantidade) - 1))
        if antes.quantidade > 1
        else None
    )
    if vendida is None:
        return
    depois = pm.calcular([*ops, _op("venda", vendida, 1.0)])[-1]
    assert depois.preco_medio == pytest.approx(antes.preco_medio)


def test_venda_sem_acoes_na_posicao_e_recusada():
    with pytest.raises(ValueError, match="posição"):
        pm.calcular([_op("venda", 0, 10)])


def test_amortizacao_sem_cotas_e_recusada():
    with pytest.raises(ValueError, match="cotas"):
        pm.calcular([_op("amortizacao", 0, 5)])


def test_amortizacao_acima_do_custo_zera_o_custo_e_o_que_passa_e_ganho():
    # 10 cotas a R$ 20 (custo 200); amortização de R$ 30 por cota = 300: 100 passam do custo
    linhas = pm.calcular([_op("compra", 10, 20), _op("amortizacao", 0, 30)])
    assert linhas[-1].custo_total == 0
    assert linhas[-1].resultado == pytest.approx(100)
