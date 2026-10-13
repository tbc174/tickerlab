"""Alvo e faixas do modelo C-1, "Clima de risco do Bitcoin" (pré-registro v2, seção 2). Só dados
sintéticos: nenhum teste olha a volatilidade real do Bitcoin (ADR 0027)."""

import numpy as np
import pandas as pd
import pytest

from base.cripto.c1.alvo import (
    AGITADO,
    CALMO,
    NORMAL,
    alvo_30_dias,
    classe_do_alvo,
    faixas,
    retornos_log,
    volatilidade_realizada,
)

DIAS = pd.date_range("2015-01-01", periods=1500, freq="D").date


def _retornos(semente: int = 1) -> pd.Series:
    rng = np.random.default_rng(semente)
    # volatilidade que muda de regime a cada 200 dias, para as faixas terem o que separar
    escala = np.repeat(rng.uniform(0.01, 0.06, size=8), 200)[: len(DIAS)]
    return pd.Series(rng.normal(0, escala), index=DIAS)


def test_retornos_log_do_fechamento():
    fechamento = pd.Series([100.0, 110.0, 99.0], index=DIAS[:3])

    retornos = retornos_log(fechamento)

    assert np.isnan(retornos.iloc[0])
    assert retornos.iloc[1] == pytest.approx(np.log(1.1))
    assert retornos.iloc[2] == pytest.approx(np.log(0.9))


def test_dia_faltando_vira_buraco_e_nao_junta_dois_dias():
    fechamento = pd.Series([100.0, 120.0], index=[DIAS[0], DIAS[2]])

    retornos = retornos_log(fechamento)

    assert list(retornos.index) == list(DIAS[:3])
    assert retornos.isna().all()  # sem o dia do meio, nenhum retorno de 1 dia existe


def test_alvo_e_o_desvio_dos_retornos_de_d_mais_1_a_d_mais_30():
    retornos = _retornos()
    d = DIAS[400]

    alvo = alvo_30_dias(retornos)

    assert alvo.loc[d] == pytest.approx(retornos.loc[DIAS[401] : DIAS[430]].std())


def test_alvo_nao_existe_sem_os_30_dias_seguintes():
    alvo = alvo_30_dias(_retornos())

    assert alvo.iloc[-30:].isna().all()
    assert not np.isnan(alvo.iloc[-31])


def test_volatilidade_realizada_usa_a_janela_que_termina_no_dia():
    retornos = _retornos()

    vol = volatilidade_realizada(retornos, 7)

    assert vol.loc[DIAS[100]] == pytest.approx(retornos.loc[DIAS[94] : DIAS[100]].std())


def test_faixas_pelos_tercos_dos_1095_dias_anteriores():
    retornos = _retornos()
    d = DIAS[1300]

    limites = faixas(retornos).loc[d]

    historico = volatilidade_realizada(retornos, 30).loc[DIAS[1300 - 1095] : DIAS[1299]]
    assert limites["inferior"] == pytest.approx(historico.quantile(1 / 3))
    assert limites["superior"] == pytest.approx(historico.quantile(2 / 3))


def test_faixas_nao_olham_o_futuro():
    retornos = _retornos()
    corte = DIAS[1250]

    completas = faixas(retornos).loc[:corte]
    cortadas = faixas(retornos.loc[:corte]).loc[:corte]

    pd.testing.assert_frame_equal(completas, cortadas)


def test_classe_do_alvo():
    limites = pd.DataFrame(
        {"inferior": [1.0, 1.0, 1.0, 1.0], "superior": [2.0] * 4}, index=DIAS[:4]
    )
    alvo = pd.Series([0.5, 1.5, 2.5, np.nan], index=DIAS[:4])

    classes = classe_do_alvo(alvo, limites)

    assert classes.iloc[:3].tolist() == [CALMO, NORMAL, AGITADO]
    assert np.isnan(classes.iloc[3])
