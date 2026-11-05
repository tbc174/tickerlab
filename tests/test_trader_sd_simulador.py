"""Ficha P0-7: o simulador do Synthetic Dividend e do rebalanceamento, com caminhos feitos à mão."""

import numpy as np
import pandas as pd
import pytest
from pytest import approx

from trader.custos_br import PADRAO, CustosBR, apurar_ir_mensal, custo_de_negociar
from trader.estrategias import sd_simulador as sd

SEM_CUSTO = CustosBR(
    emolumentos_a_vista=0.0, emolumentos_no_leilao=0.0, taxa_cripto_por_lado=0.0
)
R = sd.PASSO_DO_SD
RS = R * sd.PARTILHA
CAPITAL = sd.CAPITAL_INICIAL
UM_PASSO = 100 * (1 + R) * 1.001  # um passo inteiro acima de 100, com folga
BTC = sd.Cenario("teste", 0.20, 0.70, "cripto", 365)


def _caminhos(precos, passos_por_dia=1, inicio=0, caixa=0.0):
    precos = np.asarray(precos, float)
    if precos.ndim == 1:
        precos = precos[:, None]
    dias, n = len(precos) // passos_por_dia, precos.shape[1]
    datas = pd.date_range("2030-01-01", periods=dias, freq="D")
    return sd.Caminhos(
        precos=precos,
        passos_por_dia=passos_por_dia,
        caixa=np.full((dias, n), caixa),
        fim_do_mes=np.repeat(sd.fim_do_mes(datas)[:, None], n, axis=1),
        inicio=inicio,
    )


def _parametros(**mudancas):
    return sd.Parametros(**{"custos": SEM_CUSTO, "com_imposto": False, **mudancas})


# --- imposto e custos ------------------------------------------------------------------------------------


@pytest.mark.parametrize("classe", ["acoes", "etf", "cripto"])
def test_ir_do_mes_segue_a_apuracao_do_custos_br(classe):
    sorteio = np.random.default_rng(3)
    meses = pd.date_range("2030-01-01", periods=36, freq="MS")
    vendas = sorteio.uniform(0, 60_000, len(meses))
    resultado = sorteio.normal(0, 5_000, len(meses))
    esperado = apurar_ir_mensal(
        pd.Series(vendas, meses), pd.Series(resultado, meses), classe
    )["imposto"]
    prejuizo, impostos = np.zeros(1), []
    for v, res in zip(vendas, resultado, strict=True):
        imposto, prejuizo = sd.ir_do_mes(
            np.array([v]),
            np.array([res]),
            prejuizo,
            PADRAO.isencao_no_mes(classe, day_trade=False),
            PADRAO.aliquota(classe, day_trade=False),
        )
        impostos.append(imposto[0])
    np.testing.assert_allclose(impostos, esperado.to_numpy())


def test_comprar_e_segurar_rende_o_preco_menos_os_custos_de_cada_ordem():
    custos = CustosBR(corretagem_por_ordem=5.0)
    parametros = sd.Parametros(
        regra="comprar_e_segurar", classe="acoes", custos=custos, com_imposto=False
    )
    resultado = sd.simular(_caminhos([100, 110, 120]), parametros)
    q = (CAPITAL - 5) / (100 * (1 + custos.emolumentos_no_leilao))
    compra = custo_de_negociar(q * 100, "acoes", no_leilao=True, custos=custos)
    venda = custo_de_negociar(q * 120, "acoes", no_leilao=True, custos=custos)
    assert resultado.custos[0] == approx(compra)
    assert resultado.final[0] == approx(q * 120)
    assert resultado.liquidado[0] == approx(q * 120 - venda)
    assert resultado.execucoes[0] == 0
    assert resultado.multiplo()[0] == approx((q * 120 - venda) / CAPITAL)


def test_liquidar_paga_o_ir_e_o_etf_nao_tem_isencao():
    caminhos = _caminhos([100, 110, 120])
    acoes, etf = (
        sd.simular(
            caminhos,
            _parametros(regra="comprar_e_segurar", classe=classe, com_imposto=True),
            capital=10_000,
        )
        for classe in ("acoes", "etf")
    )
    assert acoes.liquidado[0] == approx(12_000)  # vendeu R$ 12 mil no mês: isento
    assert etf.liquidado[0] == approx(12_000 - 0.15 * 2_000)
    assert etf.final[0] == approx(12_000)  # sem vender, o IR fica adiado


def test_darf_sai_do_caixa_no_fim_do_mes_seguinte():
    """Venda em janeiro, DARF de 15% (ETF) pago no último dia de fevereiro."""
    precos = [100] + [UM_PASSO] * 69
    resultado = sd.simular(
        _caminhos(precos), _parametros(classe="etf", com_imposto=True)
    )
    vendido = CAPITAL / 100 * RS
    darf = 0.15 * vendido * (UM_PASSO - 100)
    queda = -np.diff(resultado.patrimonio[:, 0])
    assert resultado.imposto[0] == approx(darf)
    assert np.flatnonzero(queda > 1) == [57]  # do dia 58 (28/02) para trás
    assert queda[57] == approx(darf)


# --- as regras -------------------------------------------------------------------------------------------


def test_full_vende_r_vezes_s_no_fechamento_do_dia_seguinte():
    seguinte = UM_PASSO * 1.02
    ultimo = seguinte * 1.05  # menos de um passo acima da nova âncora: nada
    resultado = sd.simular(_caminhos([100, UM_PASSO, seguinte, ultimo]), _parametros())
    q = CAPITAL / 100
    assert resultado.execucoes[0] == 1
    assert resultado.final[0] == approx(q * (1 - RS) * ultimo + q * RS * seguinte)


def test_ath_so_vende_e_o_full_recompra_na_queda():
    precos = [100, UM_PASSO, UM_PASSO, *[UM_PASSO / 1.2] * 3]  # sobe um passo, cai dois
    full, ath = (
        sd.simular(_caminhos(precos), _parametros(regra=regra))
        for regra in ("full", "ath")
    )
    assert full.execucoes[0] == 2
    assert ath.execucoes[0] == 1


def test_gatilho_do_sd_conta_passos_inteiros():
    livro = sd._Livro(1, CAPITAL, _parametros())
    livro.ancora[:] = 100.0
    precos = np.array([100 * (1 + R) ** 2.5])
    assert sd.gatilho(precos, livro, np.zeros(1), _parametros())[0] == 2
    assert sd.gatilho(100 / precos * 100, livro, np.zeros(1), _parametros())[0] == -2
    ath = _parametros(regra="ath")
    assert sd.gatilho(100 / precos * 100, livro, np.zeros(1), ath)[0] == 0


def test_banda_adaptativa_e_o_piso():
    cripto = sd.Parametros(regra="constant_mix")
    assert sd.banda_adaptativa(np.array([0.70]), cripto)[0] == approx(0.70 / 30**0.5)
    assert sd.piso_da_banda(cripto) == approx(10 * 2 * PADRAO.taxa_cripto_por_lado)
    assert sd.banda_adaptativa(np.array([0.01]), cripto)[0] == approx(0.02)
    b3 = sd.Parametros(regra="constant_mix", classe="etf", execucoes_desejadas=12)
    assert sd.piso_da_banda(b3) == approx(20 * PADRAO.emolumentos_no_leilao)
    limitada = sd.com(b3, execucao="limitada")
    assert sd.piso_da_banda(limitada) == approx(20 * PADRAO.emolumentos_a_vista)
    cambio = sd.com(cripto, com_cambio=True)
    assert sd.taxa_por_lado(cambio) == approx(0.001 + 0.0038 + 0.005)


def test_volatilidade_so_usa_os_dias_anteriores():
    sorteio = np.random.default_rng(1)
    fechamentos = 100 * np.exp(np.cumsum(sorteio.normal(0, 0.02, (200, 1)), axis=0))
    sigma = sd.volatilidade_conhecida(fechamentos, 90, 365)
    alterado = fechamentos.copy()
    alterado[150:] *= 3
    assert np.isnan(sigma[90, 0]) and not np.isnan(sigma[91, 0])
    np.testing.assert_array_equal(
        sd.volatilidade_conhecida(alterado, 90, 365)[:151], sigma[:151]
    )


def test_constant_mix_volta_a_metade_quando_passa_da_banda():
    """Histórico parado (σ = 0, banda no piso de 2%): sobe 3%, rebalanceia no dia seguinte."""
    inicio = sd.JANELA_DA_VOL + 1
    precos = [100.0] * (inicio + 1) + [103.0] * 3
    resultado = sd.simular(
        _caminhos(precos, inicio=inicio), _parametros(regra="constant_mix")
    )
    assert resultado.execucoes[0] == 1
    assert resultado.final[0] == approx(2 * 0.5 * (CAPITAL / 2 + 1_000 * 103))


def test_ordem_do_constant_mix_mira_a_fracao():
    livro = sd._Livro(1, 50_000.0, _parametros(regra="constant_mix"))
    livro.quantidade[:] = 1_500.0
    preco = np.array([100.0])
    pedido = sd.ordem(np.ones(1), preco, livro, _parametros(regra="constant_mix"))
    assert pedido[0] == approx((0.5 * 200_000 - 150_000) / 100)


# --- execução, day trade, teto e caixa -------------------------------------------------------------------


def test_no_fechamento_nao_ha_day_trade():
    caminhos = sd.caminhos_gbm(BTC, 0.14, caminhos=40, anos=1)
    for regra in ("full", "constant_mix"):
        resultado = sd.simular(caminhos, sd.Parametros(regra=regra))
        assert resultado.dias_de_day_trade.sum() == 0
        assert resultado.execucoes.sum() > 0


def _dia_de_day_trade(**mudancas):
    """No dia 1 o preço sobe um passo (vende) e volta a 100 (recompra), em ações."""
    precos = [100, 100, UM_PASSO, 100, 100, 100]
    return sd.simular(
        _caminhos(precos, passos_por_dia=2),
        _parametros(classe="acoes", execucao="limitada", com_imposto=True, **mudancas),
    )


def test_limitada_apura_o_day_trade_a_vinte_por_cento():
    resultado = _dia_de_day_trade()
    q = CAPITAL / 100
    day_trade = min(q * RS, q * (1 - RS) * RS)
    assert resultado.dias_de_day_trade[0] == 1
    assert resultado.execucoes[0] == 2
    # o resto da venda (swing) ficou abaixo de R$ 20 mil no mês: isento
    assert resultado.imposto[0] == approx(0.20 * day_trade * (UM_PASSO - 100))


def test_bloqueio_de_day_trade_impede_a_recompra_no_mesmo_dia():
    resultado = _dia_de_day_trade(bloquear_day_trade=True)
    assert resultado.dias_de_day_trade[0] == 0
    assert resultado.execucoes[0] == 2  # a recompra fica para o dia seguinte
    assert resultado.imposto[0] == 0


def test_teto_nao_vende_acima_da_isencao_do_mes():
    tres_passos = 100 * (1 + R) ** 3 * 1.001  # venda de ~13% de R$ 260 mil
    caminhos = _caminhos([100, tres_passos, tres_passos, tres_passos])
    travado = sd.simular(caminhos, _parametros(classe="acoes", teto_de_vendas=True))
    livre = sd.simular(caminhos, _parametros(classe="acoes"))
    etf = sd.simular(caminhos, _parametros(classe="etf", teto_de_vendas=True))
    assert travado.execucoes[0] == 0 and travado.vendas_travadas[0] == 2
    assert livre.execucoes[0] == 1
    assert etf.execucoes[0] == 1 and etf.vendas_travadas[0] == 0  # ETF não tem isenção


def test_teto_deixa_a_venda_pequena():
    caminhos = _caminhos([100, UM_PASSO, UM_PASSO])  # venda de ~R$ 9,9 mil
    resultado = sd.simular(caminhos, _parametros(classe="acoes", teto_de_vendas=True))
    assert resultado.execucoes[0] == 1 and resultado.vendas_travadas[0] == 0


def test_sem_caixa_nao_recompra_e_com_caixa_negativo_recompra():
    caminhos = _caminhos([100, 70, 70, 70])
    sem = sd.simular(caminhos, _parametros())
    com = sd.simular(caminhos, _parametros(caixa_negativo=True))
    assert sem.execucoes[0] == 0
    assert sem.caixa_minimo[0] >= -1e-9
    assert com.execucoes[0] == 1
    assert com.caixa_minimo[0] < 0


def test_caixa_rende_o_cdi_do_dia():
    """Constant-mix com preço parado: metade fica no caixa e rende 0,1% ao dia."""
    resultado = sd.simular(
        _caminhos([100] * 6, inicio=3, caixa=0.001),
        _parametros(regra="constant_mix", janela_da_vol=2),
    )
    no_inicio = CAPITAL * 1.001  # o caixa rende no dia antes da compra do fechamento
    assert resultado.final[0] == approx(no_inicio / 2 + no_inicio / 2 * 1.001**2)


# --- sem olhar o futuro e reexecução ---------------------------------------------------------------------


@pytest.mark.parametrize("regra", sd.REGRAS)
def test_cortar_o_futuro_nao_muda_o_passado(regra):
    longo = sd.caminhos_gbm(BTC, 0.14, caminhos=30, anos=1)
    corte = longo.inicio + 200
    curto = sd.Caminhos(
        precos=longo.precos[:corte],
        passos_por_dia=1,
        caixa=longo.caixa[:corte],
        fim_do_mes=longo.fim_do_mes[:corte],
        inicio=longo.inicio,
    )
    parametros = sd.Parametros(regra=regra)
    a, b = sd.simular(longo, parametros), sd.simular(curto, parametros)
    antes = corte - longo.inicio - 1  # o último dia do curto liquida
    np.testing.assert_allclose(b.patrimonio[:antes], a.patrimonio[:antes])


def test_mesma_semente_mesmo_hash():
    def rodar(semente):
        caminhos = sd.caminhos_gbm(BTC, 0.14, caminhos=20, anos=1, semente=semente)
        return sd.hash_do_resultado(sd.simular(caminhos, sd.Parametros()))

    assert rodar(1) == rodar(1)
    assert rodar(1) != rodar(2)


def test_caminhos_do_gbm():
    caminhos = sd.caminhos_gbm(BTC, 0.14, caminhos=5, anos=1, passos_por_dia=4)
    dias = sd.JANELA_DA_VOL + 1 + 365 + 1
    assert caminhos.precos.shape == (dias * 4, 5)
    assert caminhos.fechamentos.shape == (dias, 5)
    assert caminhos.inicio == sd.JANELA_DA_VOL + 1
    assert np.all(caminhos.precos[0] == sd.PRECO_INICIAL)
    assert caminhos.caixa[0, 0] == approx(1.14 ** (1 / 365) - 1)
    assert caminhos.fim_do_mes[30, 0] and not caminhos.fim_do_mes[29, 0]


def test_janelas_do_historico_comecam_em_cada_mes():
    datas = pd.date_range("2020-01-01", "2023-12-31", freq="D")
    fechamento = pd.Series(np.arange(1, len(datas) + 1, dtype=float), datas)
    caixa = pd.Series(0.0001, datas)
    caminhos, comecos = sd.janelas_do_historico(
        fechamento, caixa, dias=365, aquecimento=365
    )
    assert comecos[0] == pd.Timestamp("2021-01-01")
    assert comecos[-1] == pd.Timestamp("2023-01-01")
    assert all(dia.day == 1 for dia in comecos)
    i = datas.get_loc(comecos[0])
    antes = sd.JANELA_DA_VOL + 1
    np.testing.assert_array_equal(
        caminhos.precos[:, 0], fechamento.to_numpy()[i - antes : i + 365]
    )
    assert caminhos.inicio == antes and caminhos.precos.shape[1] == len(comecos)
    with pytest.raises(ValueError, match="mesmas datas"):
        sd.janelas_do_historico(fechamento, caixa.iloc[1:], dias=365, aquecimento=365)
    with pytest.raises(ValueError, match="curta"):
        sd.janelas_do_historico(fechamento, caixa, dias=5_000, aquecimento=365)


def test_resumo_compara_com_a_regua_no_mesmo_caminho():
    caminhos = sd.caminhos_gbm(BTC, 0.14, caminhos=50, anos=1)
    regua = sd.simular(caminhos, sd.Parametros(regra="comprar_e_segurar"))
    full = sd.simular(caminhos, sd.Parametros())
    resumo = sd.resumir(full, regua)
    assert resumo["caminhos"] == 50
    assert resumo["p5"] <= resumo["mediana"] <= resumo["p95"]
    assert resumo["vence_a_regua"] == approx(
        np.mean(full.multiplo() > regua.multiplo())
    )
    assert sd.resumir(regua, regua)["vence_a_regua"] == 0
    assert 0 <= resumo["maior_queda"] < 1


# --- o que não pode ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mudanca",
    [
        {"regra": "martingale"},
        {"classe": "futuros"},
        {"execucao": "mercado"},
        {"fracao": 1.0},
        {"passo": 0.0},
        {"execucoes_desejadas": 0},
    ],
)
def test_parametros_invalidos(mudanca):
    with pytest.raises(ValueError):
        sd.Parametros(**mudanca)


def test_caminhos_invalidos():
    with pytest.raises(ValueError, match="positivo"):
        _caminhos([100, -1, 100])
    with pytest.raises(ValueError, match="não batem"):
        sd.Caminhos(
            precos=np.ones((5, 1)),
            passos_por_dia=2,
            caixa=np.zeros((3, 1)),
            fim_do_mes=np.zeros((3, 1), bool),
            inicio=0,
        )


def test_simulacao_invalida():
    with pytest.raises(ValueError, match="um preço por dia"):
        sd.simular(_caminhos([100] * 6, passos_por_dia=2), sd.Parametros())
    with pytest.raises(ValueError, match="volatilidade"):
        sd.simular(_caminhos([100] * 6), sd.Parametros(regra="constant_mix"))
