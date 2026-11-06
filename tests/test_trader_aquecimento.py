"""Aquecimento separado da janela avaliada, e as conferências de cobertura e de memória."""

import numpy as np
import pandas as pd
import pytest

from trader import aquecimento as aq
from trader.atributos import HORIZONTES, atributos_do_ativo
from trader.holdout import INICIO_DA_AVALIACAO


def _indice(inicio="2000-01-03", periodos=600):
    return pd.bdate_range(inicio, periods=periodos)


def _retornos(periodos=2500, semente=0):
    rng = np.random.default_rng(semente)
    return pd.Series(
        rng.normal(0.0003, 0.01, periodos), index=_indice(periodos=periodos)
    )


def test_janela_avaliada_comeca_depois_do_aquecimento():
    indice = _indice()
    janela = aq.janela_avaliada(indice, aquecimento=252)
    assert janela[0] == indice[252]
    assert len(janela) == len(indice) - 252


def test_janela_avaliada_por_data():
    indice = _indice()
    janela = aq.janela_avaliada(indice, inicio="2001-01-01")
    assert janela[0] == pd.Timestamp("2001-01-01")
    assert (janela >= pd.Timestamp("2001-01-01")).all()


def test_aquecimento_ou_data_nunca_os_dois():
    indice = _indice()
    with pytest.raises(ValueError, match="nunca os dois"):
        aq.janela_avaliada(indice, aquecimento=252, inicio="2001-01-01")
    with pytest.raises(ValueError, match="nunca os dois"):
        aq.janela_avaliada(indice)


def test_aquecimento_negativo_recusa():
    with pytest.raises(ValueError, match="negativo"):
        aq.janela_avaliada(_indice(), aquecimento=-1)
    with pytest.raises(ValueError, match="negativa"):
        aq.aquecimento_necessario([21, -5])


def test_serie_curta_demais_recusa():
    with pytest.raises(ValueError, match="não cobre"):
        aq.janela_avaliada(_indice(periodos=100), aquecimento=252)
    with pytest.raises(ValueError, match="Nenhum pregão"):
        aq.janela_avaliada(_indice(periodos=100), inicio="2030-01-01")


def test_aquecimento_necessario_e_a_maior_janela():
    assert aq.aquecimento_necessario([1, 21, 252, 63]) == 252
    assert aq.aquecimento_necessario([]) == 0
    assert (
        aq.aquecimento_necessario([*HORIZONTES, 252])
        == aq.AQUECIMENTO_DOS_ATRIBUTOS_DA_M2
    )


def test_janela_finita_nao_depende_do_comeco_e_expansiva_depende():
    r = _retornos()

    def calcular(retorno):
        return pd.DataFrame(
            {
                "media_de_21": retorno.rolling(21).mean(),
                "exponencial": retorno.ewm(span=35, min_periods=20).std(),
                "desde_o_primeiro_dia": retorno.expanding().mean(),
            }
        )

    assert aq.dependem_do_comeco(calcular, r, corte=300, aquecimento=252) == [
        "desde_o_primeiro_dia"
    ]


def test_mais_historia_antes_nao_muda_a_janela_avaliada():
    """Nos atributos da M2, só a tendência (normalização expansiva da B1) depende do começo.

    Este teste fixa o achado: se um atributo novo também depender, ou se a tendência deixar de
    depender, o teste quebra e a lista de `aquecimento` precisa ser revista.
    """
    r = _retornos()

    def calcular(retorno):
        return atributos_do_ativo(retorno, dias_por_ano=252)

    for corte in (300, 1000):
        mudaram = aq.dependem_do_comeco(
            calcular, r, corte=corte, aquecimento=aq.AQUECIMENTO_DOS_ATRIBUTOS_DA_M2
        )
        assert mudaram == ["tendencia"]


def test_corte_precisa_tirar_algum_pregao():
    with pytest.raises(ValueError, match="corte"):
        aq.dependem_do_comeco(
            lambda r: r.to_frame("x"), _retornos(), corte=0, aquecimento=10
        )


def test_cobertura_do_aquecimento():
    """Um ativo com história antes do início cobre o aquecimento; um que começa depois, não."""
    indices = {
        "ANTIGO": pd.bdate_range("1995-01-02", "2005-12-30"),
        "NOVO": pd.bdate_range("2014-09-17", "2020-12-31"),
    }
    cobertura = aq.cobertura_do_aquecimento(
        indices, INICIO_DA_AVALIACAO, aq.AQUECIMENTO_DOS_ATRIBUTOS_DA_M2
    ).set_index("simbolo")
    assert list(cobertura.reset_index().columns) == aq.COLUNAS_DA_COBERTURA
    assert bool(cobertura.loc["ANTIGO", "cobre"])
    assert cobertura.loc["ANTIGO", "aquecido_desde"] < INICIO_DA_AVALIACAO
    assert not bool(cobertura.loc["NOVO", "cobre"])
    assert cobertura.loc["NOVO", "pregoes_antes_do_inicio"] == 0
    assert cobertura.loc["NOVO", "aquecido_desde"] == indices["NOVO"][252]
