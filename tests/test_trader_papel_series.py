"""Papel da v0.2: a foto de cada série sai do simulador registrado, sem olhar o futuro e sem posição
antes do início do papel."""

from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from trader.estrategias import carteira_rp as rp
from trader.estrategias import tendencia_b3 as tb
from trader.estrategias import tendencia_cripto as tc
from trader.papel import series as sr

# --- dados sintéticos ----------------------------------------------------------------------------

PREGOES = pd.bdate_range("2024-01-01", periods=420)
DIAS = pd.date_range("2024-01-01", periods=560, freq="D")


def _tabelas_da_p0_3(semente: int = 0) -> sr.Tabelas:
    gerador = np.random.default_rng(semente)
    vols = (0.004, 0.012, 0.009, 0.010)
    retornos = gerador.normal(0.0003, vols, size=(len(PREGOES), len(vols)))
    precos = pd.DataFrame(
        100 * np.cumprod(1 + retornos, axis=0),
        index=PREGOES,
        columns=list(rp.ATIVOS_DE_RISCO),
    )
    volumes = pd.Series(1e9, index=list(rp.ATIVOS_DE_RISCO))
    return sr.Tabelas(precos, pd.Series(0.0004, index=PREGOES), volumes)


def _tabelas_de_cripto(semente: int = 3) -> sr.Tabelas:
    gerador = np.random.default_rng(semente)
    fase = (np.arange(len(DIAS)) // 90) % 2
    media = np.where(fase == 0, 0.004, -0.003)[:, None]
    retornos = gerador.normal(0.0, 0.03, (len(DIAS), 2)) + media
    precos = pd.DataFrame(
        100 * np.cumprod(1 + retornos, axis=0), index=DIAS, columns=list(tc.ATIVOS)
    )
    volumes = pd.DataFrame(1e9, index=DIAS, columns=list(tc.ATIVOS))
    return sr.Tabelas(precos, pd.Series(0.0004, index=DIAS), volumes)


def _entradas_do_di1(semente: int = 7) -> sr.EntradasDoDI1:
    gerador = np.random.default_rng(semente)
    cdi = pd.Series(0.0004, index=PREGOES)
    fechamento = pd.Series(
        100 * np.cumprod(1 + gerador.normal(0.0003, 0.015, len(PREGOES))), index=PREGOES
    )
    abertura = fechamento.shift(1).fillna(fechamento.iloc[0])
    bova11 = tb.a_vista(
        "BOVA11", abertura, fechamento, pd.Series(5e8, index=PREGOES), cdi
    )
    passos = np.where((np.arange(len(PREGOES)) // 80) % 2 == 0, -0.0003, 0.0003)
    curva = pd.DataFrame(
        {
            "data_base": PREGOES,
            "curva": "nominal",
            "prazo_anos": 2.0,
            "taxa": 0.11 + np.cumsum(passos),
        }
    )
    return sr.EntradasDoDI1(tb.di1_sintetico(curva, cdi, bova11), cdi)


def _cortado(tabelas: sr.Tabelas, fechamento) -> sr.Tabelas:
    corte = pd.Timestamp(fechamento)
    volumes = tabelas.volumes
    if isinstance(volumes, pd.DataFrame):
        volumes = volumes.loc[:corte]
    return sr.Tabelas(tabelas.precos.loc[:corte], tabelas.cdi.loc[:corte], volumes)


def _fins_de_mes(datas: pd.DatetimeIndex) -> list:
    meses = pd.Series(datas.to_period("M"), index=datas)
    return [d.date() for d in meses.groupby(meses).tail(1).index]


# --- a lista fixa --------------------------------------------------------------------------------


def test_a_lista_e_a_da_tabela_da_secao_5():
    referencia = {
        s.nome: (s.registro, s.sharpe_de_referencia, s.mercado) for s in sr.SERIES
    }
    assert referencia == {
        "p0_3": (5, 0.41, "b3"),
        "p0_1": (11, 0.68, "cripto"),
        "di1": (12, 0.44, "b3"),
        "p0_1b": (18, -1.16, "cripto"),
    }
    assert all(s.queda_do_desenvolvimento < 0 for s in sr.SERIES)
    assert sr.serie("di1").registro == 12
    with pytest.raises(KeyError):
        sr.serie("p0_9")


def test_as_series_usam_os_parametros_da_ficha():
    assert rp.Parametros() == sr.PARAMETROS_DA_P0_3
    assert (
        sr.PARAMETROS_DA_P0_3.esquema == "risk_parity"
        and sr.PARAMETROS_DA_P0_3.janela == 252
    )


# --- P0-3 ----------------------------------------------------------------------------------------

PRIMEIRO_DA_P0_3 = PREGOES[300].date()


def test_p0_3_esta_em_caixa_no_primeiro_fechamento_e_comeca_no_aquecimento():
    foto = sr.fotografar_p0_3(_tabelas_da_p0_3(), PRIMEIRO_DA_P0_3, PRIMEIRO_DA_P0_3)
    assert set(foto["carteira"]["exposicao"].values()) == {0.0}
    assert foto["dados"]["desde"] == PREGOES[300 - 252].date().isoformat()
    assert foto["fechamento"] == PRIMEIRO_DA_P0_3.isoformat()
    assert foto["regra"]["registro"] == 5


def test_p0_3_decide_so_no_ultimo_pregao_do_mes_e_o_alvo_e_o_que_a_simulacao_executa():
    tabelas = _tabelas_da_p0_3()
    fim_de_mes = next(
        d
        for d in _fins_de_mes(PREGOES)
        if PREGOES[PREGOES.get_loc(pd.Timestamp(d)) - 5].date() > PRIMEIRO_DA_P0_3
    )
    meio_do_mes = PREGOES[PREGOES.get_loc(pd.Timestamp(fim_de_mes)) - 5].date()
    assert sr.fotografar_p0_3(tabelas, meio_do_mes, PRIMEIRO_DA_P0_3)["sinal"] == {
        "decisao": False,
        "alvo": None,
    }
    sinal = sr.fotografar_p0_3(tabelas, fim_de_mes, PRIMEIRO_DA_P0_3)["sinal"]
    assert sinal["decisao"] is True
    assert sum(sinal["alvo"].values()) == pytest.approx(1.0)
    # a simulação longa (com o pregão seguinte de verdade) decide o mesmo alvo
    desde = PREGOES[300 - 252]
    longa = rp.simular(
        tabelas.precos.loc[desde:],
        tabelas.cdi.loc[desde:],
        tabelas.volumes,
        rp.Parametros(),
    )
    assert sinal["alvo"] == pytest.approx(
        longa.alvos.loc[pd.Timestamp(fim_de_mes)].to_dict()
    )


def test_p0_3_a_carteira_do_dia_e_a_da_simulacao_continua():
    tabelas = _tabelas_da_p0_3()
    desde = PREGOES[300 - 252]
    # o caixa não rende até o primeiro fechamento: nada do aquecimento chega ao papel
    caixa = tabelas.cdi.loc[desde:].copy()
    caixa.loc[: pd.Timestamp(PRIMEIRO_DA_P0_3)] = 0.0
    longa = rp.simular(
        tabelas.precos.loc[desde:], caixa, tabelas.volumes, rp.Parametros()
    )
    assert longa.patrimonio.loc[pd.Timestamp(PRIMEIRO_DA_P0_3)] == sr.CAPITAL_DO_PAPEL
    for posicao in (330, 360, 400):
        dia = PREGOES[posicao]
        foto = sr.fotografar_p0_3(tabelas, dia.date(), PRIMEIRO_DA_P0_3)
        assert foto["carteira"]["patrimonio"] == pytest.approx(
            sr.CAPITAL_DO_PAPEL
            * longa.patrimonio.loc[dia]
            / longa.patrimonio.loc[pd.Timestamp(PRIMEIRO_DA_P0_3)]
        )
    assert longa.pesos.loc[PREGOES[400]].sum() > 0  # a carteira já investiu


@pytest.mark.parametrize("posicao", [300, 335, 389, 410])
def test_p0_3_cortar_o_futuro_nao_muda_o_passado(posicao):
    tabelas = _tabelas_da_p0_3()
    dia = PREGOES[posicao].date()
    inteira = sr.fotografar_p0_3(tabelas, dia, PRIMEIRO_DA_P0_3)
    cortada = sr.fotografar_p0_3(_cortado(tabelas, dia), dia, PRIMEIRO_DA_P0_3)
    assert inteira == cortada


def test_p0_3_sem_aquecimento_suficiente_falha():
    with pytest.raises(ValueError, match="aquecimento"):
        sr.fotografar_p0_3(_tabelas_da_p0_3(), PREGOES[260].date(), PREGOES[200].date())


def test_p0_3_sem_o_fechamento_nos_dados_falha():
    tabelas = _tabelas_da_p0_3()
    dia = PREGOES[350]
    sem_o_dia = sr.Tabelas(
        tabelas.precos.drop(dia), tabelas.cdi.drop(dia), tabelas.volumes
    )
    with pytest.raises(ValueError, match="fechamento"):
        sr.fotografar_p0_3(sem_o_dia, dia.date(), PRIMEIRO_DA_P0_3)


def test_estimados_vao_para_a_foto():
    tabelas = _tabelas_da_p0_3()
    com_estimado = sr.Tabelas(
        tabelas.precos, tabelas.cdi, tabelas.volumes, ("cdi", "NTNB")
    )
    foto = sr.fotografar_p0_3(com_estimado, PRIMEIRO_DA_P0_3, PRIMEIRO_DA_P0_3)
    assert foto["dados"]["estimados"] == ["NTNB", "cdi"]


# --- P0-1 ----------------------------------------------------------------------------------------

PRIMEIRO_DE_CRIPTO = DIAS[400].date()


FOTOS_DE_CRIPTO = pytest.mark.parametrize(
    "fotografar", [sr.fotografar_p0_1, sr.fotografar_p0_1b], ids=["p0_1", "p0_1b"]
)


@FOTOS_DE_CRIPTO
def test_cripto_esta_em_caixa_no_primeiro_fechamento_e_aquece_365_dias(fotografar):
    foto = fotografar(_tabelas_de_cripto(), PRIMEIRO_DE_CRIPTO, PRIMEIRO_DE_CRIPTO)
    assert set(foto["carteira"]["exposicao"].values()) == {0.0}
    assert foto["dados"]["desde"] == DIAS[35].date().isoformat()
    assert set(foto["sinal"]["alvo"]) == {"BTC", "ETH"}


def test_cripto_o_alvo_do_dia_e_o_que_a_simulacao_executa_no_dia_seguinte():
    tabelas = _tabelas_de_cripto()
    desde = DIAS[35]
    precos = tabelas.precos.loc[desde:]
    longa = tc.simular(
        precos,
        tabelas.cdi.loc[desde:],
        tabelas.volumes.loc[desde:],
        tc.PARAMETROS_DA_FICHA,
    )
    executados = 0
    for posicao in (401, 430, 470, 500):
        dia = DIAS[posicao]
        foto = sr.fotografar_p0_1(tabelas, dia.date(), PRIMEIRO_DE_CRIPTO)
        seguinte = longa.alvos.loc[DIAS[posicao + 1]].to_dict()
        assert foto["sinal"]["alvo"] == pytest.approx(seguinte)
        executados += sum(seguinte.values()) > 0
    assert executados > 0  # o teste olha dias com posição de verdade


@FOTOS_DE_CRIPTO
@pytest.mark.parametrize("posicao", [400, 450, 520])
def test_cripto_cortar_o_futuro_nao_muda_o_passado(fotografar, posicao):
    tabelas = _tabelas_de_cripto()
    dia = DIAS[posicao].date()
    inteira = fotografar(tabelas, dia, PRIMEIRO_DE_CRIPTO)
    cortada = fotografar(_cortado(tabelas, dia), dia, PRIMEIRO_DE_CRIPTO)
    assert inteira == cortada


def test_p0_1b_e_a_p0_1_diferem_pela_banda_e_pelo_cambio():
    tabelas = _tabelas_de_cripto()
    dia = DIAS[520].date()
    p0_1 = sr.fotografar_p0_1(tabelas, dia, PRIMEIRO_DE_CRIPTO)
    p0_1b = sr.fotografar_p0_1b(tabelas, dia, PRIMEIRO_DE_CRIPTO)
    assert p0_1["sinal"] == p0_1b["sinal"]  # o alvo é a regra da P0-1, sem mudança
    assert p0_1["regra"]["parametros"] != p0_1b["regra"]["parametros"]
    assert p0_1["carteira"]["patrimonio"] != p0_1b["carteira"]["patrimonio"]


def test_cripto_precisa_dos_dados_desde_o_aquecimento():
    tabelas = _tabelas_de_cripto()
    curta = sr.Tabelas(
        tabelas.precos.iloc[100:], tabelas.cdi.iloc[100:], tabelas.volumes.iloc[100:]
    )
    with pytest.raises(ValueError, match="começar"):
        sr.fotografar_p0_1(curta, PRIMEIRO_DE_CRIPTO, PRIMEIRO_DE_CRIPTO)


# --- DI1 -----------------------------------------------------------------------------------------

PRIMEIRO_DO_DI1 = PREGOES[370].date()


def test_di1_esta_em_caixa_no_primeiro_fechamento():
    entradas = _entradas_do_di1()
    foto = sr.fotografar_di1(entradas, PRIMEIRO_DO_DI1, PRIMEIRO_DO_DI1)
    assert foto["carteira"]["exposicao"] == {"DI1": 0.0}
    primeiro_excesso = entradas.ativo.excesso.first_valid_index()
    posicao = PREGOES.get_loc(pd.Timestamp(PRIMEIRO_DO_DI1)) - tb.AQUECIMENTO_EM_PREGOES
    assert pd.Timestamp(foto["dados"]["desde"]) == PREGOES[posicao] >= primeiro_excesso


@pytest.mark.parametrize("posicao", [370, 395, 419])
def test_di1_cortar_o_futuro_nao_muda_o_passado(posicao):
    entradas = _entradas_do_di1()
    dia = PREGOES[posicao].date()
    inteira = sr.fotografar_di1(entradas, dia, PRIMEIRO_DO_DI1)
    cortada = sr.fotografar_di1(
        sr.EntradasDoDI1(
            entradas.ativo.ate(pd.Timestamp(dia)), entradas.cdi.loc[: pd.Timestamp(dia)]
        ),
        dia,
        PRIMEIRO_DO_DI1,
    )
    assert inteira == cortada


def test_di1_o_alvo_e_o_da_regra_no_fechamento():
    entradas = _entradas_do_di1()
    dia = PREGOES[410]
    foto = sr.fotografar_di1(entradas, dia.date(), PRIMEIRO_DO_DI1)
    desde = PREGOES[370 - tb.AQUECIMENTO_EM_PREGOES]
    ativo = sr._ativo_desde(entradas.ativo, desde).ate(dia)
    assert foto["sinal"]["alvo"]["DI1"] == pytest.approx(
        float(tb.fracao_alvo(ativo, tb.PARAMETROS_DA_FICHA).loc[dia])
    )


# --- nada antes do início -------------------------------------------------------------------------


def test_posicao_antes_do_inicio_e_recusada():
    exposicao = pd.DataFrame({"BTC": [0.0, 0.3, 0.2]}, index=DIAS[:3])
    with pytest.raises(sr.AntesDoInicioError, match=str(DIAS[1].date())):
        sr._sem_posicao_ate(exposicao, DIAS[2].date())
    sr._sem_posicao_ate(exposicao, DIAS[0].date())
    sr._sem_posicao_ate(pd.Series([0.0, 0.0], index=DIAS[:2]), DIAS[1].date())


# --- nada de antes do início entra no papel ------------------------------------------------------


def _casos_do_inicio():
    return [
        pytest.param(sr.fotografar_p0_3, _tabelas_da_p0_3, PRIMEIRO_DA_P0_3, id="p0_3"),
        pytest.param(
            sr.fotografar_p0_1, _tabelas_de_cripto, PRIMEIRO_DE_CRIPTO, id="p0_1"
        ),
        pytest.param(
            sr.fotografar_p0_1b, _tabelas_de_cripto, PRIMEIRO_DE_CRIPTO, id="p0_1b"
        ),
        pytest.param(sr.fotografar_di1, _entradas_do_di1, PRIMEIRO_DO_DI1, id="di1"),
    ]


@pytest.mark.parametrize(("fotografar", "entradas", "primeiro"), _casos_do_inicio())
def test_no_primeiro_fechamento_o_papel_vale_o_capital_e_esta_em_caixa(
    fotografar, entradas, primeiro
):
    foto = fotografar(entradas(), primeiro, primeiro)
    assert foto["carteira"]["patrimonio"] == sr.CAPITAL_DO_PAPEL
    assert set(foto["carteira"]["exposicao"].values()) == {0.0}


def _com_outro_cdi_antes(entradas, primeiro: date):
    """As mesmas entradas, com o triplo do CDI em todo pregão até o primeiro fechamento."""
    antes = entradas.cdi.index <= pd.Timestamp(primeiro)
    return replace(entradas, cdi=entradas.cdi.where(~antes, entradas.cdi * 3))


@pytest.mark.parametrize(("fotografar", "entradas", "primeiro"), _casos_do_inicio())
def test_o_caixa_de_antes_do_inicio_nao_muda_o_que_e_gravado(
    fotografar, entradas, primeiro
):
    """O aquecimento cai no holdout: o que a simulação rende nele não pode chegar à foto."""
    tabelas = entradas()
    mexida = _com_outro_cdi_antes(tabelas, primeiro)
    datas = pd.DatetimeIndex(tabelas.cdi.index)
    for dia in datas[datas.get_loc(pd.Timestamp(primeiro)) :][[0, 10, 40]]:
        original = fotografar(tabelas, dia.date(), primeiro)
        mexido = fotografar(mexida, dia.date(), primeiro)
        assert mexido["carteira"] == original["carteira"]
        assert mexido["sinal"] == original["sinal"]
