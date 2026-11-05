"""Freios da carteira própria (pré-registro quant v0.1, seção 6).

O freio dispara no dia em que o fechamento cruza o limite, sai para o CDI só no pregão seguinte
(nunca usa o fechamento do próprio dia para sair) e, no backtest, volta no primeiro pregão 12 meses
depois do disparo. Os históricos são artificiais, no calendário real da B3.
"""

from datetime import date

import pandas as pd
import pytest

from trader import calendario, criterio_quant, freios

DATAS = pd.DatetimeIndex(calendario.pregoes(date(2015, 1, 2), date(2018, 12, 28)))
CDI = pd.Series(0.0004, index=DATAS)
DRIFT = 0.001
# Posições (pregões) das quedas plantadas: −30% não cruza os 40%; com mais −20% cruza (≈ −43%).
PRIMEIRA_QUEDA, SEGUNDA_QUEDA = 50, 60


def _historia(quedas: dict[int, float]) -> pd.Series:
    retorno = pd.Series(DRIFT, index=DATAS)
    for posicao, queda in quedas.items():
        retorno.iloc[posicao] = queda
    return retorno


@pytest.fixture
def com_disparo():
    retorno = _historia({PRIMEIRA_QUEDA: -0.30, SEGUNDA_QUEDA: -0.20})
    return retorno, freios.aplicar_freio(retorno, CDI, limite=0.40)


def test_dispara_no_dia_em_que_o_fechamento_cruza_o_limite(com_disparo):
    _, freio = com_disparo
    assert freio.disparos == (DATAS[SEGUNDA_QUEDA],)
    assert freio.saidas == (DATAS[SEGUNDA_QUEDA + 1],)


def test_a_perda_do_dia_do_disparo_e_da_camada(com_disparo):
    """Nunca usa o fechamento do próprio dia para sair: o dia do disparo rende o da camada."""
    _, freio = com_disparo
    dia, seguinte = DATAS[SEGUNDA_QUEDA], DATAS[SEGUNDA_QUEDA + 1]
    assert freio.retorno[dia] == -0.20
    assert not freio.em_cdi[dia]
    assert freio.retorno[seguinte] == CDI[seguinte]
    assert freio.em_cdi[seguinte]


def test_volta_no_primeiro_pregao_doze_meses_depois(com_disparo):
    retorno, freio = com_disparo
    aniversario = DATAS[SEGUNDA_QUEDA] + pd.DateOffset(months=12)
    volta = DATAS[aniversario <= DATAS][0]
    assert freio.voltas == (volta,)
    vespera = DATAS[DATAS.get_loc(volta) - 1]
    assert freio.em_cdi[vespera] and not freio.em_cdi[volta]
    assert freio.retorno[volta] == retorno[volta]
    assert freio.em_cdi[seguinte_ao(DATAS[SEGUNDA_QUEDA]) : vespera].all()


def seguinte_ao(dia: pd.Timestamp) -> pd.Timestamp:
    return DATAS[DATAS.get_loc(dia) + 1]


def test_sem_queda_ate_o_limite_nada_muda():
    retorno = _historia({PRIMEIRA_QUEDA: -0.30})
    freio = freios.aplicar_freio(retorno, CDI, limite=0.40)
    assert freio.retorno.equals(retorno)
    assert freio.disparos == () and freio.saidas == () and freio.voltas == ()
    assert not freio.em_cdi.any()


def test_o_pico_recomeca_na_volta(com_disparo):
    retorno, freio = com_disparo
    volta = freio.voltas[0]
    posicao = DATAS.get_loc(volta)
    retorno = retorno.copy()
    retorno.iloc[posicao + 5] = -0.35  # 35% abaixo do novo pico: não é 40%
    assert freios.aplicar_freio(retorno, CDI, limite=0.40).disparos == freio.disparos
    retorno.iloc[
        posicao + 10
    ] = -0.10  # 0,65 × 0,9 ≈ −41,5% do novo pico: dispara de novo
    de_novo = freios.aplicar_freio(retorno, CDI, limite=0.40)
    assert de_novo.disparos == (*freio.disparos, DATAS[posicao + 10])


def test_sem_doze_meses_de_dados_fica_em_cdi_ate_o_fim():
    retorno = _historia({PRIMEIRA_QUEDA: -0.30, SEGUNDA_QUEDA: -0.20}).iloc[:200]
    freio = freios.aplicar_freio(retorno, CDI, limite=0.40)
    assert freio.voltas == ()
    assert freio.em_cdi.iloc[SEGUNDA_QUEDA + 1 :].all()


def test_disparo_no_ultimo_dia_nao_tem_saida():
    retorno = _historia({PRIMEIRA_QUEDA: -0.30, SEGUNDA_QUEDA: -0.20}).iloc[
        : SEGUNDA_QUEDA + 1
    ]
    freio = freios.aplicar_freio(retorno, CDI, limite=0.40)
    assert freio.disparos == (DATAS[SEGUNDA_QUEDA],) and freio.saidas == ()


def test_cortar_o_futuro_nao_muda_o_passado(com_disparo):
    retorno, freio = com_disparo
    for corte in (SEGUNDA_QUEDA + 1, SEGUNDA_QUEDA + 40, 400):
        cortado = freios.aplicar_freio(retorno.iloc[:corte], CDI, limite=0.40)
        assert cortado.retorno.equals(freio.retorno.iloc[:corte])
        assert cortado.em_cdi.equals(freio.em_cdi.iloc[:corte])


def test_cdi_faltando_e_erro():
    retorno = _historia({})
    with pytest.raises(ValueError, match="CDI"):
        freios.aplicar_freio(retorno, CDI.iloc[:-5], limite=0.40)


def test_limites_vem_do_pre_registro():
    assert freios.FREIO_POR_CAMADA == criterio_quant.FREIO_POR_CAMADA == 0.40
    assert freios.FREIO_GLOBAL == criterio_quant.FREIO_GLOBAL == 0.35
    assert freios.MESES_DE_VOLTA == criterio_quant.MESES_DE_VOLTA_DO_FREIO == 12
    retorno = _historia({PRIMEIRA_QUEDA: -0.30, SEGUNDA_QUEDA: -0.10})  # ≈ −37%
    assert freios.aplicar_freio(retorno, CDI).disparos == ()  # padrão: por camada, 40%
    assert freios.aplicar_freio(retorno, CDI, limite=freios.FREIO_GLOBAL).disparos


# --- 2008 e 2020 -----------------------------------------------------------------------------------

PREGOES_DAS_CRISES = pd.DatetimeIndex(
    calendario.pregoes(date(2007, 1, 2), date(2021, 12, 30))
)
# Pico e primeiro fechamento 35% abaixo dele, com o formato do Ibovespa nas duas crises; os
# valores são plantados (não são as cotações), só as datas e o calendário são reais.
CRISES = {
    "2008": (pd.Timestamp("2008-05-20"), pd.Timestamp("2008-09-29")),
    "2020": (pd.Timestamp("2020-01-23"), pd.Timestamp("2020-03-12")),
}
PREGOES_DE_QUEDA_DEPOIS_DO_CRUZAMENTO = 10


def _historia_das_crises(limite: float) -> pd.Series:
    """Sobe devagar; do pico ao cruzamento cai em progressão geométrica que só fica abaixo de
    (1 − limite) × pico no dia do cruzamento; cai mais 10 pregões e volta a subir."""
    retorno = pd.Series(0.0002, index=PREGOES_DAS_CRISES)
    for pico, cruzamento in CRISES.values():
        de_pico_a_cruzamento = PREGOES_DAS_CRISES[
            (pico < PREGOES_DAS_CRISES) & (cruzamento >= PREGOES_DAS_CRISES)
        ]
        pregoes = len(de_pico_a_cruzamento)
        queda_por_dia = 1 - (1 - limite) ** (1 / (pregoes - 0.5))
        retorno[de_pico_a_cruzamento] = -queda_por_dia
        depois = PREGOES_DAS_CRISES[cruzamento < PREGOES_DAS_CRISES][
            :PREGOES_DE_QUEDA_DEPOIS_DO_CRUZAMENTO
        ]
        retorno[depois] = -0.01
    return retorno


def test_freio_global_dispara_nas_datas_de_2008_e_2020_e_a_carteira_vai_para_cdi():
    camadas = pd.DataFrame({"A1": _historia_das_crises(freios.FREIO_GLOBAL)})
    cdi = pd.Series(0.0004, index=PREGOES_DAS_CRISES)
    carteira = freios.freiar_carteira(camadas, {"A1": 1.0}, cdi)
    global_ = carteira.global_
    assert global_.disparos == (
        pd.Timestamp("2008-09-29"),
        pd.Timestamp("2020-03-12"),
    )
    assert global_.saidas == (pd.Timestamp("2008-09-30"), pd.Timestamp("2020-03-13"))
    assert global_.voltas == (pd.Timestamp("2009-09-29"), pd.Timestamp("2021-03-12"))
    assert carteira.retorno["2008-09-30":"2009-09-28"].eq(0.0004).all()
    assert carteira.retorno["2020-03-13":"2021-03-11"].eq(0.0004).all()
    # O freio da camada (40%) só cruza dias depois, quando a queda continua.
    assert all(
        camada > global_
        for camada, global_ in zip(
            carteira.camadas["A1"].disparos, global_.disparos, strict=True
        )
    )
    assert len(carteira.camadas["A1"].disparos) == 2


def test_carteira_freada_soma_as_camadas_com_os_pesos():
    datas = DATAS[:300]
    camadas = pd.DataFrame({"A1": 0.002, "A2": -0.001}, index=datas)
    cdi = CDI[:300]
    carteira = freios.freiar_carteira(camadas, {"A1": 0.75, "A2": 0.25}, cdi)
    assert carteira.sem_freio.iloc[10] == pytest.approx(0.75 * 0.002 + 0.25 * -0.001)
    assert carteira.retorno.equals(carteira.sem_freio)  # nada cruzou os limites
    with pytest.raises(ValueError, match="pesos"):
        freios.freiar_carteira(camadas, {"A1": 0.5, "A2": 0.3}, cdi)
    with pytest.raises(ValueError, match="pesos"):
        freios.freiar_carteira(camadas, {"A1": 1.0}, cdi)


def test_freio_por_camada_tira_so_a_camada_que_caiu():
    datas = DATAS[:400]
    cdi = CDI[:400]
    a1 = pd.Series(0.0005, index=datas)
    a1.iloc[100] = -0.45
    camadas = pd.DataFrame({"A1": a1, "A2": 0.0005}, index=datas)
    carteira = freios.freiar_carteira(camadas, {"A1": 0.5, "A2": 0.5}, cdi)
    assert carteira.camadas["A1"].disparos == (datas[100],)
    assert carteira.camadas["A2"].disparos == ()
    assert carteira.retorno.iloc[101] == pytest.approx(0.5 * 0.0004 + 0.5 * 0.0005)
    assert carteira.global_.disparos == ()  # a carteira caiu 22,5%, menos que 35%
