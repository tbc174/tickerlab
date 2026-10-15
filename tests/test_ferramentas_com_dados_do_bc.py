"""As ferramentas que usam dados do Banco Central: conversor de moedas, renda fixa com IR, juro real
e correção pela inflação (src/ferramentas/moedas.py, renda_fixa.py, taxas.py e inflacao.py)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.ferramentas import inflacao, moedas, renda_fixa, taxas

COTACOES = {"USD": 5.0, "EUR": 5.5, "JPY": 0.033}  # em reais (a PTAX de venda)


# --- conversor ------------------------------------------------------------------------------
def test_converte_de_e_para_o_real():
    assert moedas.converter(100, "USD", "BRL", COTACOES) == pytest.approx(500)
    assert moedas.converter(500, "BRL", "USD", COTACOES) == pytest.approx(100)


def test_converte_entre_duas_moedas_passando_pelo_real():
    assert moedas.converter(100, "EUR", "USD", COTACOES) == pytest.approx(110)
    assert moedas.converter(1, "USD", "JPY", COTACOES) == pytest.approx(5 / 0.033)


def test_moeda_sem_cotacao_da_erro():
    with pytest.raises(ValueError, match="ARS"):
        moedas.converter(1, "ARS", "BRL", COTACOES)


@given(valor=st.floats(0, 1e9), de=st.sampled_from(["BRL", "USD", "EUR", "JPY"]))
def test_ida_e_volta_da_o_mesmo_valor(valor, de):
    ida = moedas.converter(valor, de, "EUR", COTACOES)
    assert moedas.converter(ida, "EUR", de, COTACOES) == pytest.approx(valor)


# --- juro real e taxa nominal ---------------------------------------------------------------
def test_juro_real_e_de_fisher_nao_a_subtracao():
    assert taxas.juro_real(0.1375, 0.05) == pytest.approx(1.1375 / 1.05 - 1)
    assert taxas.juro_real(0.1375, 0.05) < 0.1375 - 0.05


def test_taxa_nominal_desfaz_o_juro_real():
    assert taxas.taxa_nominal(taxas.juro_real(0.12, 0.045), 0.045) == pytest.approx(
        0.12
    )


def test_inflacao_de_menos_100_por_cento_nao_existe():
    with pytest.raises(ValueError, match="inflação"):
        taxas.juro_real(0.1, -1)


# --- correção pela inflação -----------------------------------------------------------------
MESES = [
    ["2024-11", 0.0039],
    ["2024-12", 0.0052],
    ["2025-01", 0.0016],
    ["2025-02", 0.0131],
]


def test_corrige_do_comeco_do_mes_inicial_ao_fim_do_mes_final():
    r = inflacao.corrigir(100, "2024-12", "2025-02", MESES)
    fator = 1.0052 * 1.0016 * 1.0131
    assert r.fator == pytest.approx(fator)
    assert r.valor_corrigido == pytest.approx(100 * fator)
    assert r.variacao == pytest.approx(fator - 1)
    assert r.meses == 3


def test_um_mes_so():
    assert inflacao.corrigir(100, "2024-11", "2024-11", MESES).fator == pytest.approx(
        1.0039
    )


@pytest.mark.parametrize(
    ("inicio", "fim", "mensagem"),
    [
        ("2025-02", "2024-12", "depois"),
        ("2024-10", "2024-12", "2024-11"),  # antes do primeiro mês
        ("2024-12", "2025-03", "2025-02"),  # depois do último
        ("2024-13", "2025-01", "mês"),
    ],
)
def test_periodo_fora_dos_dados(inicio, fim, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        inflacao.corrigir(100, inicio, fim, MESES)


def test_inflacao_em_12_meses():
    meses = [[f"2025-{m:02d}", 0.01] for m in range(1, 13)]
    assert inflacao.em_12_meses(meses) == pytest.approx(1.01**12 - 1)
    with pytest.raises(ValueError, match="12"):
        inflacao.em_12_meses(meses[:11])


# --- renda fixa -----------------------------------------------------------------------------
CDI = 0.1365
POUPANCA = 0.006704


def _opcao(opcoes, nome):
    (o,) = [o for o in opcoes if o.nome == nome]
    return o


def test_cdb_paga_ir_e_lci_nao():
    opcoes = renda_fixa.comparar(10_000, 365, [CDI], 1.0, 0.9, POUPANCA)
    cdb, lci = _opcao(opcoes, "CDB"), _opcao(opcoes, "LCI ou LCA")
    dias_uteis = 365 * 252 / 365
    bruto = 10_000 * (1 + CDI) ** (dias_uteis / 252)
    assert cdb.bruto == pytest.approx(bruto)
    assert cdb.aliquota == 0.175  # 365 dias está na faixa de 361 a 720 dias
    assert lci.imposto == 0
    assert lci.aliquota == 0


def test_aliquota_segue_a_tabela_regressiva_pelo_prazo():
    assert (
        _opcao(renda_fixa.comparar(1000, 90, [CDI], 1, 0.9, POUPANCA), "CDB").aliquota
        == 0.225
    )
    assert (
        _opcao(renda_fixa.comparar(1000, 400, [CDI], 1, 0.9, POUPANCA), "CDB").aliquota
        == 0.175
    )
    assert (
        _opcao(renda_fixa.comparar(1000, 800, [CDI], 1, 0.9, POUPANCA), "CDB").aliquota
        == 0.15
    )


def test_percentual_do_cdi_vale_sobre_a_taxa_de_cada_dia():
    opcoes = renda_fixa.comparar(1000, 365, [CDI], 1.1, 0.9, POUPANCA)
    diaria = ((1 + CDI) ** (1 / 252) - 1) * 1.1
    assert _opcao(opcoes, "CDB").bruto == pytest.approx(1000 * (1 + diaria) ** 252)


def test_tesouro_selic_rende_100_por_cento_e_paga_ir():
    opcoes = renda_fixa.comparar(1000, 365, [CDI], 1.1, 0.9, POUPANCA)
    tesouro = _opcao(opcoes, "Tesouro Selic")
    assert tesouro.bruto == pytest.approx(1000 * (1 + CDI))
    assert tesouro.aliquota > 0


def test_poupanca_so_rende_no_aniversario():
    assert (
        _opcao(renda_fixa.comparar(1000, 29, [CDI], 1, 0.9, POUPANCA), "Poupança").bruto
        == 1000
    )
    poupanca = _opcao(
        renda_fixa.comparar(1000, 95, [CDI], 1, 0.9, POUPANCA), "Poupança"
    )
    assert poupanca.bruto == pytest.approx(1000 * (1 + POUPANCA) ** 3)
    assert poupanca.imposto == 0


def test_imposto_e_sobre_o_rendimento_nao_sobre_o_total():
    cdb = _opcao(renda_fixa.comparar(10_000, 800, [CDI], 1, 0.9, POUPANCA), "CDB")
    assert cdb.imposto == pytest.approx((cdb.bruto - 10_000) * 0.15)
    assert cdb.liquido == pytest.approx(cdb.bruto - cdb.imposto)


@pytest.mark.parametrize(
    ("args", "mensagem"),
    [
        ((-1, 365, [CDI], 1, 0.9, POUPANCA), "valor"),
        ((1000, 0, [CDI], 1, 0.9, POUPANCA), "prazo"),
        ((1000, renda_fixa.DIAS_MAXIMOS + 1, [CDI], 1, 0.9, POUPANCA), "prazo"),
        ((1000, 365, [CDI], -0.1, 0.9, POUPANCA), "percentual"),
    ],
)
def test_entradas_invalidas(args, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        renda_fixa.comparar(*args)


# --- ferramentas v2: a trajetória mês a mês e os anos em que a poupança perdeu --------------
def test_evolucao_comeca_no_valor_e_termina_na_correcao():
    caminho = inflacao.evolucao(100, "2024-12", "2025-02", MESES)
    assert caminho[0] == 100
    assert len(caminho) == 4  # o começo e o fim de cada um dos 3 meses
    assert caminho[1] == pytest.approx(100 * 1.0052)
    assert caminho[-1] == pytest.approx(
        inflacao.corrigir(100, "2024-12", "2025-02", MESES).valor_corrigido
    )


def _ano(ano: int, ao_mes: float) -> list[list]:
    return [[f"{ano}-{m:02d}", ao_mes] for m in range(1, 13)]


def test_anos_em_que_o_rendimento_perdeu_para_a_inflacao():
    rendimento = _ano(2023, 0.005) + _ano(2024, 0.004) + _ano(2025, 0.006)
    inflacao_mes = _ano(2023, 0.004) + _ano(2024, 0.005) + _ano(2025, 0.005)
    # 2024: 0,4% ao mês contra 0,5% de inflação; 2023 e 2025 ganharam
    assert inflacao.anos_abaixo(rendimento, inflacao_mes, 2025, 3) == [1, 3]


def test_ano_incompleto_nao_entra_na_conta():
    rendimento = _ano(2024, 0.004) + _ano(2025, 0.004)[:6]
    inflacao_mes = _ano(2024, 0.005) + _ano(2025, 0.005)
    assert inflacao.anos_abaixo(rendimento, inflacao_mes, 2025, 2) == [1, 1]
