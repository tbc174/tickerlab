"""Camada A3: a nota só é comparada com preços posteriores ao registro, 12 meses depois."""

import numpy as np
import pandas as pd
import pytest

from trader import custos_br
from trader.agentes import comparacao

DATAS = pd.bdate_range("2026-10-01", "2028-03-31")
CDI = pd.Series(0.0004, index=DATAS)
SEM_CUSTOS = custos_br.CustosBR(emolumentos_a_vista=0.0)


def _fechamento():
    passos = np.arange(len(DATAS))
    return pd.DataFrame(
        {
            "AAA3": 100 * 1.001**passos,
            "BBB3": 100 * 0.999**passos,
            "CCC3": np.full(len(DATAS), 100.0),
        },
        index=DATAS,
    )


def _linha(data="2026-11-03", escolhidas=None):
    return {
        "data": data,
        "avaliacoes": [
            {"ticker": "AAA3", "nota_final": 9.0},
            {"ticker": "BBB3", "nota_final": 2.0},
            {"ticker": "CCC3", "nota_final": 5.0},
        ],
        "escolhidas": {"AAA3": 0.2} if escolhidas is None else escolhidas,
    }


ENTRADA = pd.Timestamp("2026-11-04")  # fechamento do pregão seguinte ao registro
SAIDA = pd.Timestamp("2027-11-04")


def test_janela_comeca_no_pregao_seguinte_e_dura_12_meses():
    assert comparacao.janela(DATAS, "2026-11-03") == (ENTRADA, SAIDA)
    assert comparacao.janela(DATAS[DATAS <= "2027-11-03"], "2026-11-03") is None


def test_compara_escolhidas_cesta_e_cdi():
    fechamento = _fechamento()
    resultado = comparacao.comparar(_linha(), fechamento, CDI)
    assert resultado is not None
    passos = DATAS.get_loc(SAIDA) - DATAS.get_loc(ENTRADA)
    retorno_a = 1.001**passos - 1
    retorno_b = 0.999**passos - 1
    cdi = 1.0004**passos - 1
    assert resultado["cdi"] == pytest.approx(cdi)
    assert resultado["escolhidas"] == pytest.approx(0.2 * retorno_a + 0.8 * cdi)
    assert resultado["cesta"] == pytest.approx((retorno_a + retorno_b + 0.0) / 3)
    assert resultado["correlacao"] == pytest.approx(1.0)  # nota alta, retorno alto
    assert resultado["ibovespa"] is None
    assert (resultado["entrada"], resultado["saida"]) == ("2026-11-04", "2027-11-04")


def test_sem_escolhidas_a_rodada_rende_cdi():
    resultado = comparacao.comparar(_linha(escolhidas={}), _fechamento(), CDI)
    assert resultado is not None
    assert resultado["escolhidas"] == pytest.approx(resultado["cdi"])


def test_ibovespa_entra_na_mesma_janela():
    ibovespa = pd.Series(np.linspace(100, 200, len(DATAS)), index=DATAS)
    resultado = comparacao.comparar(_linha(), _fechamento(), CDI, ibovespa=ibovespa)
    assert resultado is not None
    assert resultado["ibovespa"] == pytest.approx(
        ibovespa[SAIDA] / ibovespa[ENTRADA] - 1
    )


def test_rodada_sem_12_meses_nao_e_comparada():
    fechamento = _fechamento().loc[:"2027-10-29"]
    assert comparacao.comparar(_linha(), fechamento, CDI) is None


def test_comparacao_nao_usa_preco_do_dia_do_registro_nem_de_antes():
    antes = comparacao.comparar(_linha(), _fechamento(), CDI)
    mexido = _fechamento()
    mexido.loc[:"2026-11-03"] *= (
        3.0  # o passado até o registro, inclusive o próprio dia
    )
    assert comparacao.comparar(_linha(), mexido, CDI) == antes


def test_cortar_o_futuro_depois_da_saida_nao_muda_a_comparacao():
    antes = comparacao.comparar(_linha(), _fechamento(), CDI)
    cortado = _fechamento().loc[:SAIDA]
    assert comparacao.comparar(_linha(), cortado, CDI) == antes


# --- a carteira em papel, rodada após rodada -----------------------------------------------------


def test_carteira_em_papel_sem_custo_chega_no_mesmo_valor_da_comparacao():
    freio = comparacao.carteira_em_papel(
        [_linha()], _fechamento(), CDI, custos=SEM_CUSTOS
    )
    assert freio.retorno.index[0] == ENTRADA
    valor = (1 + freio.retorno.loc[:SAIDA]).prod() - 1
    resultado = comparacao.comparar(_linha(), _fechamento(), CDI)
    assert resultado is not None
    assert valor == pytest.approx(resultado["escolhidas"])


def test_custo_de_montar_sai_no_dia_da_entrada():
    custos = custos_br.CustosBR(emolumentos_a_vista=0.001)
    freio = comparacao.carteira_em_papel([_linha()], _fechamento(), CDI, custos=custos)
    assert freio.retorno[ENTRADA] == pytest.approx(-0.2 * 0.001)


def test_segunda_rodada_troca_a_carteira_na_entrada_dela():
    fechamento = _fechamento()
    linhas = [_linha(), _linha("2026-12-02", escolhidas={"BBB3": 0.2})]
    freio = comparacao.carteira_em_papel(linhas, fechamento, CDI, custos=SEM_CUSTOS)
    troca = pd.Timestamp("2026-12-03")
    fim = DATAS[-1]

    def acumulado(inicio, final):
        return 1.0004 ** (DATAS.get_loc(final) - DATAS.get_loc(inicio))

    ate_a_troca = 0.2 * fechamento.at[troca, "AAA3"] / fechamento.at[
        ENTRADA, "AAA3"
    ] + 0.8 * acumulado(ENTRADA, troca)
    depois = 0.2 * fechamento.at[fim, "BBB3"] / fechamento.at[
        troca, "BBB3"
    ] + 0.8 * acumulado(troca, fim)
    assert (1 + freio.retorno).prod() == pytest.approx(ate_a_troca * depois)


def test_freio_de_40_por_cento_manda_a_camada_para_cdi():
    fechamento = pd.DataFrame(100.0, index=DATAS, columns=[f"Q{n}3" for n in range(5)])
    fechamento.loc["2027-02-01":] = 30.0  # as cinco caem 70% no mesmo dia
    linha = {
        "data": "2026-11-03",
        "avaliacoes": [{"ticker": t, "nota_final": 8.0} for t in fechamento.columns],
        "escolhidas": dict.fromkeys(fechamento.columns, 0.2),
    }
    freio = comparacao.carteira_em_papel([linha], fechamento, CDI, custos=SEM_CUSTOS)
    assert freio.disparos == (pd.Timestamp("2027-02-01"),)
    assert freio.em_cdi["2027-02-02"]
    assert freio.retorno["2027-02-02"] == pytest.approx(0.0004)


def test_carteira_em_papel_nao_olha_o_futuro():
    linhas = [_linha(), _linha("2026-12-02", escolhidas={"BBB3": 0.2})]
    inteira = comparacao.carteira_em_papel(linhas, _fechamento(), CDI).retorno
    corte = pd.Timestamp("2027-03-15")
    cortada = comparacao.carteira_em_papel(
        linhas, _fechamento().loc[:corte], CDI
    ).retorno
    pd.testing.assert_series_equal(cortada, inteira.loc[:corte])


def test_rodada_que_ainda_nao_entrou_fica_de_fora():
    linhas = [_linha(), _linha("2028-03-31", escolhidas={"BBB3": 0.2})]
    so_a_primeira = comparacao.carteira_em_papel([_linha()], _fechamento(), CDI).retorno
    pd.testing.assert_series_equal(
        comparacao.carteira_em_papel(linhas, _fechamento(), CDI).retorno, so_a_primeira
    )
