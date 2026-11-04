"""Custos do Brasil das estratégias quant: negociação, lote, imposto por mês, aluguel e câmbio."""

import pandas as pd
import pytest

from trader import custos_br
from trader.custos_br import CustosBR

CUSTOS = CustosBR(corretagem_por_ordem=5.0)


# --- Negociar e lote -------------------------------------------------------------------


def test_custo_de_negociar_a_vista():
    # R$ 10 mil em ações: 0,03% de emolumentos (R$ 3) + corretagem de R$ 5
    assert custos_br.custo_de_negociar(10_000, "acoes", custos=CUSTOS) == pytest.approx(
        8.0
    )
    # ETF paga o mesmo que ação na negociação (a diferença está no imposto)
    assert custos_br.custo_de_negociar(10_000, "etf", custos=CUSTOS) == pytest.approx(
        8.0
    )


def test_custo_de_negociar_day_trade_usa_a_tarifa_de_day_trade():
    custos = CustosBR(emolumentos_a_vista=0.0003, emolumentos_day_trade=0.0002)
    assert custos_br.custo_de_negociar(10_000, "acoes", custos=custos) == pytest.approx(
        3.0
    )
    assert custos_br.custo_de_negociar(
        10_000, "acoes", day_trade=True, custos=custos
    ) == pytest.approx(2.0)


def test_ordem_no_leilao_paga_a_tarifa_do_leilao_salvo_no_day_trade():
    custos = CustosBR(
        emolumentos_a_vista=0.0003,
        emolumentos_no_leilao=0.00032,
        emolumentos_day_trade=0.00023,
    )
    assert custos_br.custo_de_negociar(
        10_000, "etf", no_leilao=True, custos=custos
    ) == pytest.approx(3.2)
    assert custos_br.custo_de_negociar(
        10_000, "etf", no_leilao=True, day_trade=True, custos=custos
    ) == pytest.approx(2.3)
    estresse = custos.em_estresse()
    assert estresse.emolumentos_no_leilao == pytest.approx(0.00064)


def test_futuro_aceita_fracao_de_contrato():
    custos = CustosBR(corretagem_por_ordem=0.0, tarifa_futuro_por_contrato=0.4)
    assert custos_br.custo_de_negociar(
        50_000, "futuros", contratos=2.5, custos=custos
    ) == pytest.approx(1.0)


def test_futuro_paga_por_contrato_e_nao_pelo_valor():
    custos = CustosBR(corretagem_por_ordem=0.0, tarifa_futuro_por_contrato=0.25)
    assert custos_br.custo_de_negociar(
        1_000_000, "futuros", contratos=4, custos=custos
    ) == pytest.approx(1.0)
    with pytest.raises(ValueError, match="contratos"):
        custos_br.custo_de_negociar(1_000_000, "futuros", custos=custos)


def test_cripto_paga_a_taxa_da_corretora_sobre_o_valor():
    custos = CustosBR(corretagem_por_ordem=0.0, taxa_cripto_por_lado=0.001)
    assert custos_br.custo_de_negociar(
        10_000, "cripto", custos=custos
    ) == pytest.approx(10.0)


def test_classe_desconhecida_e_recusada():
    with pytest.raises(ValueError, match="classe"):
        custos_br.custo_de_negociar(100, "fundo_imobiliario")


def test_valor_negativo_e_recusado():
    with pytest.raises(ValueError, match="negativo"):
        custos_br.custo_de_negociar(-1, "acoes")


def test_lote_padrao_e_fracionario():
    assert custos_br.arredondar_lote(150) == 100
    assert custos_br.arredondar_lote(150, fracionario=True) == 150
    assert custos_br.arredondar_lote(150.9, fracionario=True) == 150
    assert custos_br.arredondar_lote(99) == 0
    # posição vendida arredonda na direção do zero, como a comprada
    assert custos_br.arredondar_lote(-150) == -100
    assert custos_br.arredondar_lote(-150.9, fracionario=True) == -150


# --- Imposto de renda por mês ----------------------------------------------------------


def _serie(valores: dict[str, float]) -> pd.Series:
    return pd.Series({pd.Timestamp(d): v for d, v in valores.items()}, dtype=float)


def test_isencao_de_20_mil_so_em_acoes_swing():
    vendas = _serie({"2026-01-10": 15_000, "2026-02-10": 25_000})
    resultado = _serie({"2026-01-10": 1_000, "2026-02-10": 1_000})
    tabela = custos_br.apurar_ir_mensal(vendas, resultado, "acoes")
    janeiro, fevereiro = tabela.iloc[0], tabela.iloc[1]
    assert bool(janeiro["isento"]) and janeiro["imposto"] == 0
    assert not bool(fevereiro["isento"])
    assert fevereiro["imposto"] == pytest.approx(150.0)  # 15% de R$ 1.000


def test_etf_e_futuro_nao_tem_isencao():
    vendas = _serie({"2026-01-10": 5_000})
    resultado = _serie({"2026-01-10": 1_000})
    for classe in ("etf", "futuros"):
        tabela = custos_br.apurar_ir_mensal(vendas, resultado, classe)
        assert not bool(tabela.iloc[0]["isento"])
        assert tabela.iloc[0]["imposto"] == pytest.approx(150.0)


def test_day_trade_paga_20_por_cento_e_nunca_e_isento():
    vendas = _serie({"2026-01-10": 5_000})
    resultado = _serie({"2026-01-10": 1_000})
    tabela = custos_br.apurar_ir_mensal(vendas, resultado, "acoes", day_trade=True)
    assert not bool(tabela.iloc[0]["isento"])
    assert tabela.iloc[0]["imposto"] == pytest.approx(200.0)


def test_cripto_isenta_ate_35_mil():
    vendas = _serie({"2026-01-10": 35_000, "2026-02-10": 35_000.01})
    resultado = _serie({"2026-01-10": 2_000, "2026-02-10": 2_000})
    tabela = custos_br.apurar_ir_mensal(vendas, resultado, "cripto")
    assert bool(tabela.iloc[0]["isento"])
    assert tabela.iloc[1]["imposto"] == pytest.approx(300.0)  # 15% de R$ 2.000


def test_prejuizo_compensa_so_nos_meses_seguintes():
    # janeiro perde 1.000, fevereiro ganha 600 (compensa 600), março ganha 1.000 (compensa os 400 que sobraram)
    vendas = _serie({"2026-01-10": 50_000, "2026-02-10": 50_000, "2026-03-10": 50_000})
    resultado = _serie({"2026-01-10": -1_000, "2026-02-10": 600, "2026-03-10": 1_000})
    tabela = custos_br.apurar_ir_mensal(vendas, resultado, "acoes")
    assert list(tabela["imposto"]) == pytest.approx(
        [0.0, 0.0, 90.0]
    )  # 15% de (1.000 − 400)
    assert list(tabela["prejuizo_compensado"]) == pytest.approx([0.0, 600.0, 400.0])
    assert list(tabela["prejuizo_acumulado"]) == pytest.approx([1_000.0, 400.0, 0.0])


def test_ganho_em_mes_isento_nao_consome_o_prejuizo_acumulado():
    vendas = _serie({"2026-01-10": 50_000, "2026-02-10": 10_000, "2026-03-10": 50_000})
    resultado = _serie({"2026-01-10": -1_000, "2026-02-10": 500, "2026-03-10": 1_000})
    tabela = custos_br.apurar_ir_mensal(vendas, resultado, "acoes")
    assert bool(tabela.iloc[1]["isento"])
    assert list(tabela["prejuizo_acumulado"]) == pytest.approx([1_000.0, 1_000.0, 0.0])
    assert tabela.iloc[2]["imposto"] == pytest.approx(0.0)  # 1.000 − 1.000 compensados


def test_varios_dias_do_mesmo_mes_somam():
    vendas = _serie(
        {"2026-01-05": 12_000, "2026-01-20": 12_000}
    )  # 24 mil no mês: passa dos 20 mil
    resultado = _serie({"2026-01-05": 300, "2026-01-20": 200})
    tabela = custos_br.apurar_ir_mensal(vendas, resultado, "acoes")
    assert len(tabela) == 1
    assert not bool(tabela.iloc[0]["isento"])
    assert tabela.iloc[0]["imposto"] == pytest.approx(75.0)


def test_imposto_sem_olhar_o_futuro():
    vendas = _serie(
        {
            "2026-01-10": 50_000,
            "2026-02-10": 50_000,
            "2026-03-10": 50_000,
            "2026-04-10": 50_000,
        }
    )
    resultado = _serie(
        {
            "2026-01-10": -1_000,
            "2026-02-10": 600,
            "2026-03-10": 1_000,
            "2026-04-10": -5_000,
        }
    )
    inteira = custos_br.apurar_ir_mensal(vendas, resultado, "acoes")
    cortada = custos_br.apurar_ir_mensal(vendas.iloc[:3], resultado.iloc[:3], "acoes")
    pd.testing.assert_frame_equal(inteira.iloc[:3], cortada)


def test_series_desalinhadas_sao_recusadas():
    vendas = _serie({"2026-01-10": 1.0})
    resultado = _serie({"2026-02-10": 1.0})
    with pytest.raises(ValueError, match="mesmas datas"):
        custos_br.apurar_ir_mensal(vendas, resultado, "acoes")


def test_sem_operacoes_devolve_tabela_vazia_com_as_colunas():
    tabela = custos_br.apurar_ir_mensal(
        pd.Series(dtype=float), pd.Series(dtype=float), "acoes"
    )
    assert tabela.empty
    assert list(tabela.columns) == list(custos_br.COLUNAS_DO_IR)


# --- Aluguel, câmbio e estresse --------------------------------------------------------


def test_aluguel_tem_minimo_de_10_reais():
    # R$ 100 mil a 5% a.a. por 73 dias = R$ 1.000; R$ 1 mil pelo mesmo prazo daria R$ 10, mínimo
    assert custos_br.custo_do_aluguel(
        100_000, dias=73, taxa_anual=0.05
    ) == pytest.approx(1_000.0)
    assert custos_br.custo_do_aluguel(100, dias=73, taxa_anual=0.05) == pytest.approx(
        10.0
    )
    with pytest.raises(ValueError, match="dias"):
        custos_br.custo_do_aluguel(100, dias=0, taxa_anual=0.05)


def test_cambio_cobra_iof_e_spread():
    custos = CustosBR(iof_cambio=0.0038, spread_cambio=0.005)
    assert custos_br.custo_do_cambio(10_000, custos=custos) == pytest.approx(88.0)


def test_estresse_dobra_os_custos_e_nunca_o_imposto():
    normal = CustosBR(corretagem_por_ordem=5.0, iof_cambio=0.0038)
    estresse = normal.em_estresse()
    assert estresse.corretagem_por_ordem == 10.0
    assert estresse.emolumentos_a_vista == 2 * normal.emolumentos_a_vista
    assert estresse.spread_cambio == 2 * normal.spread_cambio
    assert estresse.ir_swing == normal.ir_swing
    assert estresse.isencao_acoes_no_mes == normal.isencao_acoes_no_mes
    assert estresse.iof_cambio == normal.iof_cambio  # IOF é lei, não custo de corretora
    assert estresse.fator_de_estresse == 2.0
    assert normal.fator_de_estresse == 1.0


def test_tabela_tem_versao_e_lista_o_que_falta_confirmar():
    assert custos_br.VERSAO == "v0.2"
    for campo in CustosBR().a_confirmar:
        assert hasattr(CustosBR(), campo), campo
    # Lidos na fonte em 03/11/2026 (tabelas da B3 e da Binance): saíram da lista
    assert "emolumentos_day_trade" not in CustosBR().a_confirmar
    assert "taxa_cripto_por_lado" not in CustosBR().a_confirmar


def test_valores_da_v0_2_lidos_na_tabela_da_b3():
    padrao = CustosBR()
    assert padrao.emolumentos_a_vista == pytest.approx(0.00030)
    assert padrao.emolumentos_no_leilao == pytest.approx(0.00032)
    assert padrao.emolumentos_day_trade == pytest.approx(0.00023)
    assert padrao.tarifa_futuro_por_contrato == pytest.approx(0.394)
