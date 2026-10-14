"""Proventos recebidos e custo médio a partir da movimentação da B3 (já normalizada).

Os casos foram feitos à mão pela regra da Receita: a compra soma o que se pagou ao custo, a venda
baixa a quantidade pelo preço médio (o médio não muda), desdobro e grupamento mudam a quantidade
sem mudar o custo total.
"""

from datetime import date

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.carteira_b3 import CarteiraB3
from src.dividendos_e_custo import (
    NOMES_DOS_PROVENTOS,
    NOTA_DOS_PROVENTOS,
    Lancamento,
    com_a_posicao,
    custo_medio,
    custos_de_hoje,
    formatar_reais,
    proventos,
    total_por_ano,
)


def _l(tipo, quantidade=0.0, valor=0.0, codigo="PETR4", data=date(2024, 1, 2)):
    return Lancamento(
        data=data, codigo=codigo, tipo=tipo, quantidade=quantidade, valor=valor
    )


def _um(lancamentos):
    (custo,) = custo_medio(lancamentos)
    return custo


# ---- custo médio ----


def test_compras_fazem_media_ponderada():
    custo = _um(
        [_l("compra", 100, 1000), _l("compra", 100, 2000, data=date(2024, 2, 1))]
    )
    assert custo.quantidade == 200
    assert custo.custo_total == pytest.approx(3000)
    assert custo.preco_medio == pytest.approx(15)
    assert custo.completo


def test_venda_nao_muda_o_medio():
    custo = _um(
        [
            _l("compra", 100, 1000),
            _l("compra", 100, 2000, data=date(2024, 2, 1)),
            _l("venda", 50, 1200, data=date(2024, 3, 1)),  # vendeu a R$ 24: não importa
        ]
    )
    assert custo.quantidade == 150
    assert custo.preco_medio == pytest.approx(15)
    assert custo.custo_total == pytest.approx(2250)


def test_desdobro_divide_o_medio_e_mantem_o_custo():
    # desdobro 1 para 2: a B3 credita as 100 ações novas
    custo = _um([_l("compra", 100, 1000), _l("desdobro", 100, data=date(2024, 5, 2))])
    assert custo.quantidade == 200
    assert custo.custo_total == pytest.approx(1000)
    assert custo.preco_medio == pytest.approx(5)


def test_grupamento_multiplica_o_medio_e_mantem_o_custo():
    # grupamento 10 para 1: saem 90 das 100 ações
    custo = _um([_l("compra", 100, 1000), _l("grupamento", 90, data=date(2024, 5, 2))])
    assert custo.quantidade == 10
    assert custo.custo_total == pytest.approx(1000)
    assert custo.preco_medio == pytest.approx(100)


def test_vender_tudo_zera_e_recomeca():
    custo = _um(
        [
            _l("compra", 100, 1000),
            _l("venda", 100, 1500, data=date(2024, 2, 1)),
            _l("compra", 10, 300, data=date(2024, 3, 1)),
        ]
    )
    assert custo.quantidade == 10
    assert custo.preco_medio == pytest.approx(30)


def test_a_ordem_e_pela_data_e_no_mesmo_dia_compra_vem_antes():
    custo = _um(
        [
            _l("venda", 10, 200, data=date(2024, 2, 1)),
            _l("compra", 10, 100, data=date(2024, 2, 1)),
            _l("compra", 10, 300, data=date(2024, 1, 2)),
        ]
    )
    assert custo.completo
    assert custo.quantidade == 10
    assert custo.preco_medio == pytest.approx(20)


def test_bonificacao_entra_na_quantidade_com_aviso():
    custo = _um([_l("compra", 100, 1000), _l("bonificacao", 10, data=date(2024, 5, 2))])
    assert custo.quantidade == 110
    assert custo.custo_total == pytest.approx(1000)
    assert custo.completo
    assert any("bonificação" in aviso for aviso in custo.avisos)


def test_venda_maior_que_compras_fica_incompleto():
    custo = _um([_l("compra", 10, 100), _l("venda", 50, 600, data=date(2024, 2, 1))])
    assert not custo.completo
    assert custo.preco_medio is None
    assert "começa depois" in custo.motivo


def test_depois_de_incompleto_continua_incompleto():
    custo = _um(
        [
            _l("venda", 50, 600),
            _l("compra", 10, 100, data=date(2024, 2, 1)),
        ]
    )
    assert not custo.completo
    assert custo.preco_medio is None


def test_compra_sem_valor_fica_incompleto():
    custo = _um([_l("compra", 100, 0.0)])
    assert not custo.completo
    assert "sem o valor" in custo.motivo


def test_um_resultado_por_ativo_ordenado_pelo_codigo():
    custos = custo_medio(
        [_l("compra", 1, 10, codigo="VALE3"), _l("compra", 1, 10, codigo="BBAS3")]
    )
    assert [c.codigo for c in custos] == ["BBAS3", "VALE3"]


def test_proventos_nao_mexem_no_custo():
    custo = _um(
        [_l("compra", 100, 1000), _l("dividendo", 0, 50, data=date(2024, 6, 1))]
    )
    assert custo.preco_medio == pytest.approx(10)


def test_ativo_so_com_proventos_nao_aparece_no_custo():
    assert custo_medio([_l("dividendo", 0, 50)]) == ()


def test_tipo_desconhecido_e_recusado():
    with pytest.raises(ValueError, match="tipo"):
        _l("doacao", 1, 1)


# propriedades: valem para qualquer sequência de compras e vendas possíveis
compras = st.lists(
    st.tuples(st.integers(1, 10_000), st.floats(0.01, 1_000)), min_size=1, max_size=20
)


@given(compras=compras, fracao=st.floats(0.0, 1.0))
def test_qualquer_venda_possivel_nao_muda_o_medio(compras, fracao):
    lancamentos = [
        _l("compra", q, q * p, data=date(2024, 1, 1 + i))
        for i, (q, p) in enumerate(compras)
    ]
    antes = _um(lancamentos)
    vendida = int(antes.quantidade * fracao)
    if vendida == 0 or vendida == antes.quantidade:
        return  # vender nada não muda nada; vender tudo zera (outro teste)
    depois = _um([*lancamentos, _l("venda", vendida, 1.0, data=date(2025, 1, 1))])
    assert depois.preco_medio == pytest.approx(antes.preco_medio, rel=1e-9)
    assert depois.quantidade == antes.quantidade - vendida


@given(compras=compras, fator=st.integers(2, 10), desdobro=st.booleans())
def test_desdobro_e_grupamento_mantem_o_custo_total(compras, fator, desdobro):
    lancamentos = [
        _l("compra", q * fator, q * p, data=date(2024, 1, 1 + i))
        for i, (q, p) in enumerate(compras)
    ]
    antes = _um(lancamentos)
    if desdobro:
        evento = _l("desdobro", antes.quantidade * (fator - 1), data=date(2025, 1, 1))
    else:
        evento = _l(
            "grupamento", antes.quantidade * (fator - 1) / fator, data=date(2025, 1, 1)
        )
    depois = _um([*lancamentos, evento])
    assert depois.custo_total == pytest.approx(antes.custo_total, rel=1e-9)


# ---- proventos ----


def test_proventos_por_ativo_por_ano_e_por_tipo():
    lancamentos = [
        _l("compra", 100, 1000),
        _l("dividendo", 0, 10, data=date(2023, 5, 1)),
        _l("jcp", 0, 20, data=date(2024, 5, 1)),
        _l("dividendo", 0, 5, data=date(2024, 8, 1)),
        _l("rendimento", 0, 7, codigo="HGLG11", data=date(2024, 9, 1)),
    ]
    resultado = proventos(lancamentos, hoje=date(2024, 12, 31))
    assert [p.codigo for p in resultado] == [
        "PETR4",
        "HGLG11",
    ]  # do maior total ao menor
    petr = resultado[0]
    assert petr.total == pytest.approx(35)
    assert petr.por_ano == {2023: pytest.approx(10), 2024: pytest.approx(25)}
    assert petr.por_tipo == {"dividendo": pytest.approx(15), "jcp": pytest.approx(20)}
    assert petr.ultimos_12_meses == pytest.approx(25)


def test_ultimos_12_meses_nao_conta_o_que_esta_depois_de_hoje():
    lancamentos = [
        _l("dividendo", 0, 10, data=date(2023, 12, 31)),  # fora: mais de 12 meses
        _l("dividendo", 0, 20, data=date(2024, 1, 1)),
        _l("dividendo", 0, 40, data=date(2025, 1, 1)),  # depois de hoje (provisionado)
    ]
    (petr,) = proventos(lancamentos, hoje=date(2024, 12, 31))
    assert petr.ultimos_12_meses == pytest.approx(20)


def test_total_por_ano_soma_todos_os_ativos():
    lancamentos = [
        _l("dividendo", 0, 10, data=date(2023, 5, 1)),
        _l("rendimento", 0, 7, codigo="HGLG11", data=date(2023, 9, 1)),
        _l("jcp", 0, 20, data=date(2024, 5, 1)),
    ]
    resultado = total_por_ano(proventos(lancamentos, hoje=date(2024, 12, 31)))
    assert resultado == {2023: pytest.approx(17), 2024: pytest.approx(20)}


def test_compra_e_venda_nao_sao_proventos():
    assert (
        proventos([_l("compra", 1, 10), _l("venda", 1, 12)], hoje=date(2024, 12, 31))
        == ()
    )


# ---- com a posição de hoje ----


def _carteira(*linhas):
    """Posição da B3 com (código, quantidade, valor de hoje)."""
    posicoes = pd.DataFrame(linhas, columns=["codigo", "quantidade", "valor"])
    posicoes.insert(1, "ticker", posicoes["codigo"] + ".SA")
    posicoes.insert(2, "tipo", "Ações")
    return CarteiraB3(posicoes, pd.DataFrame(columns=["tipo", "produto", "valor"]))


def test_ganho_ou_perda_ainda_nao_realizados():
    custos = custo_medio([_l("compra", 100, 1000)])
    (petr,) = com_a_posicao(custos, _carteira(("PETR4", 100, 1500)))
    assert petr.custo_total == pytest.approx(1000)
    assert petr.resultado == pytest.approx(500)
    assert petr.resultado_percentual == pytest.approx(0.5)
    assert petr.motivo is None


def test_quantidade_diferente_da_posicao_fica_sem_resultado():
    custos = custo_medio([_l("compra", 100, 1000)])
    (petr,) = com_a_posicao(custos, _carteira(("PETR4", 150, 1500)))
    assert petr.resultado is None
    assert petr.quantidade_na_movimentacao == 100
    assert "não bate" in petr.motivo


def test_ativo_sem_compra_na_movimentacao():
    (vale,) = com_a_posicao((), _carteira(("VALE3", 10, 600)))
    assert vale.resultado is None
    assert "antes do período" in vale.motivo


def test_custo_incompleto_passa_o_motivo_adiante():
    custos = custo_medio([_l("venda", 10, 100)])
    (petr,) = com_a_posicao(custos, _carteira(("PETR4", 10, 150)))
    assert petr.resultado is None
    assert petr.motivo == custos[0].motivo


def test_so_os_ativos_da_posicao_na_ordem_dela():
    custos = custo_medio(
        [_l("compra", 1, 10, codigo="BBAS3"), _l("compra", 1, 10, codigo="VALE3")]
    )
    resultado = com_a_posicao(custos, _carteira(("VALE3", 1, 20), ("ITUB4", 1, 5)))
    assert [r.codigo for r in resultado] == ["VALE3", "ITUB4"]


@pytest.mark.parametrize(
    ("valor", "texto"),
    [
        (1234.56, "R$ 1.234,56"),
        (0, "R$ 0,00"),
        (-1500, "-R$ 1.500,00"),
        (0.005, "R$ 0,01"),
    ],
)
def test_formatar_reais(valor, texto):
    assert formatar_reais(valor) == texto


def test_custos_de_hoje_tira_os_vendidos_inteiros_e_mantem_os_incompletos():
    custos = custo_medio(
        [
            _l("compra", 10, 100, codigo="HGLG11"),
            _l("venda", 10, 120, codigo="HGLG11", data=date(2024, 2, 1)),
            _l("venda", 5, 60, codigo="WEGE3"),
            _l("compra", 1, 10, codigo="VALE3"),
        ]
    )
    assert [c.codigo for c in custos_de_hoje(custos)] == ["VALE3", "WEGE3"]


def test_taxa_do_aluguel_entra_na_renda_do_ativo_com_nome_proprio():
    lancamentos = [
        Lancamento(date(2026, 8, 19), "VGIR11", "reembolso", 0, 100.0),
        Lancamento(date(2026, 8, 28), "VGIR11", "aluguel", 0, 7.0),
    ]
    (ativo,) = proventos(lancamentos, hoje=date(2026, 10, 13))
    assert ativo.total == pytest.approx(107.0)
    assert ativo.por_tipo == {"aluguel": 7.0, "reembolso": 100.0}
    assert "aluguel" in NOMES_DOS_PROVENTOS
    assert "aluguel" in NOTA_DOS_PROVENTOS.lower()


def test_taxa_do_aluguel_nao_mexe_no_custo_medio():
    lancamentos = [
        Lancamento(date(2026, 1, 5), "VGIR11", "compra", 100, 1000.0),
        Lancamento(date(2026, 8, 28), "VGIR11", "aluguel", 0, 7.0),
    ]
    (custo,) = custo_medio(lancamentos)
    assert custo.completo and custo.quantidade == 100
    assert custo.custo_total == pytest.approx(1000.0)


# ---- amortização de FII: devolução de capital, reduz o custo e não muda a quantidade ----


def test_amortizacao_reduz_o_custo_total_e_o_medio_sem_mudar_a_quantidade():
    custo = _um(
        [_l("compra", 100, 1000), _l("amortizacao", 0, 100, data=date(2024, 3, 1))]
    )
    assert custo.quantidade == 100
    assert custo.custo_total == pytest.approx(900)
    assert custo.preco_medio == pytest.approx(9)
    assert custo.completo


def test_amortizacao_nao_conta_como_provento():
    lancamentos = [_l("compra", 100, 1000), _l("amortizacao", 0, 100)]
    assert proventos(lancamentos, hoje=date(2024, 6, 1)) == ()


def test_amortizacao_maior_que_o_custo_zera_o_custo_e_avisa():
    custo = _um(
        [_l("compra", 10, 100), _l("amortizacao", 0, 130, data=date(2024, 3, 1))]
    )
    assert custo.custo_total == 0
    assert custo.completo
    assert any("ganho de capital" in aviso for aviso in custo.avisos)


def test_venda_depois_da_amortizacao_baixa_pelo_medio_ja_reduzido():
    custo = _um(
        [
            _l("compra", 100, 1000),
            _l("amortizacao", 0, 200, data=date(2024, 2, 1)),
            _l("venda", 50, 900, data=date(2024, 3, 1)),
        ]
    )
    assert custo.quantidade == 50
    assert custo.custo_total == pytest.approx(400)  # médio de R$ 8


def test_amortizacao_sem_compra_no_periodo_deixa_o_ativo_incompleto():
    custo = _um([_l("amortizacao", 0, 100)])
    assert not custo.completo
    assert "antes do período" in custo.motivo
