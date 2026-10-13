"""Réguas R0, R1 e R2 e os dois candidatos do modelo C-1 (pré-registro v2, seções 5 e 6), em dados
sintéticos."""

import numpy as np
import pandas as pd
import pytest

from base.cripto.c1.candidatos import (
    GRADE_DA_REGULARIZACAO,
    ArvoresComReforco,
    LogisticaComValidacao,
    preparar_entradas,
)
from base.cripto.c1.entradas import COLUNAS
from base.cripto.c1.medidas import brier
from base.cripto.c1.reguas import Frequencia, Har, Persistencia


def _quadro(
    n: int = 1500, semente: int = 11, sinal: float = 0.0
) -> tuple[pd.DataFrame, pd.Series]:
    """Entradas sintéticas com faixas fixas em 1 e 2; a volatilidade futura (alvo) segue a dos
    últimos 30 dias e, se `sinal` > 0, também a entrada `wikipedia`."""
    rng = np.random.default_rng(semente)
    quadro = pd.DataFrame(rng.normal(size=(n, len(COLUNAS))), columns=COLUNAS)
    passada = np.exp(rng.normal(np.log(1.5), 0.4, n))
    for coluna in ("vol_1", "vol_7", "vol_30", "vol_90"):
        quadro[coluna] = passada * np.exp(rng.normal(0, 0.1, n))
    quadro["limite_inferior"], quadro["limite_superior"] = 1.0, 2.0
    log_alvo = (
        0.8 * np.log(passada) + sinal * quadro["wikipedia"] + rng.normal(0, 0.15, n)
    )
    quadro["alvo"] = np.exp(log_alvo)
    classes = pd.Series(np.digitize(quadro["alvo"], [1.0, 2.0]), index=quadro.index)
    return quadro, classes


def test_brier_de_previsao_perfeita_e_zero_e_de_chute_uniforme_e_dois_tercos():
    y = np.array([0, 1, 2])
    assert brier(np.eye(3), y) == pytest.approx(0.0)
    assert brier(np.full((3, 3), 1 / 3), y) == pytest.approx(2 / 3)


def test_r0_frequencia_das_faixas_no_treino():
    quadro, classes = _quadro()

    probabilidades = (
        Frequencia().ajustar(quadro, classes).probabilidades(quadro.head(2))
    )

    esperado = classes.tail(1095).value_counts(normalize=True).sort_index().to_numpy()
    assert probabilidades[0] == pytest.approx(esperado)


def test_r1_persistencia_repete_a_faixa_dos_ultimos_30_dias():
    quadro = pd.DataFrame(
        {
            "vol_30": [0.5, 1.5, 2.5],
            "limite_inferior": [1.0] * 3,
            "limite_superior": [2.0] * 3,
        }
    )

    assert Persistencia().probabilidades(quadro).tolist() == [
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1],
    ]


def test_r2_har_usa_so_as_volatilidades_do_preco():
    quadro, classes = _quadro()
    har = Har().ajustar(quadro, classes)
    mexido = quadro.assign(wikipedia=99.0, selic=-5.0)

    assert har.probabilidades(quadro) == pytest.approx(har.probabilidades(mexido))


def test_r2_har_bate_a_frequencia_quando_o_passado_explica_o_futuro():
    quadro, classes = _quadro()
    treino, teste = slice(0, 1000), slice(1000, None)

    har = Har().ajustar(quadro.iloc[treino], classes.iloc[treino])
    frequencia = Frequencia().ajustar(quadro.iloc[treino], classes.iloc[treino])

    assert brier(har.probabilidades(quadro.iloc[teste]), classes.iloc[teste]) < brier(
        frequencia.probabilidades(quadro.iloc[teste]), classes.iloc[teste]
    )


def test_preparar_entradas_poe_as_volatilidades_na_escala_das_faixas():
    quadro = pd.DataFrame([[0.0] * len(COLUNAS)], columns=COLUNAS)
    quadro["vol_30"] = 2.0
    quadro["limite_inferior"], quadro["limite_superior"] = 1.0, 4.0  # centro = 2

    preparado = preparar_entradas(quadro)

    assert preparado["vol_30"].iloc[0] == pytest.approx(0.0)
    assert list(preparado.columns) == COLUNAS


def test_candidatos_com_os_parametros_do_pre_registro():
    arvores = ArvoresComReforco().modelo
    assert (arvores.max_depth, arvores.n_estimators, arvores.learning_rate) == (
        3,
        200,
        0.05,
    )
    assert GRADE_DA_REGULARIZACAO == (0.01, 0.1, 1.0, 10.0, 100.0)


@pytest.mark.parametrize("candidato", [LogisticaComValidacao, ArvoresComReforco])
def test_candidato_nao_enxerga_o_alvo(candidato):
    quadro, classes = _quadro(n=600)
    modelo = candidato().ajustar(quadro, classes)

    com_lixo_no_alvo = quadro.assign(alvo=-1.0)

    assert modelo.probabilidades(quadro) == pytest.approx(
        modelo.probabilidades(com_lixo_no_alvo)
    )


@pytest.mark.parametrize("candidato", [LogisticaComValidacao, ArvoresComReforco])
def test_candidato_aprende_a_entrada_que_tem_sinal(candidato):
    quadro, classes = _quadro(sinal=0.5)
    treino, teste = slice(0, 1000), slice(1000, None)

    modelo = candidato().ajustar(quadro.iloc[treino], classes.iloc[treino])
    har = Har().ajustar(quadro.iloc[treino], classes.iloc[treino])

    assert brier(
        modelo.probabilidades(quadro.iloc[teste]), classes.iloc[teste]
    ) < brier(har.probabilidades(quadro.iloc[teste]), classes.iloc[teste])


def test_buracos_nas_entradas_viram_a_mediana_do_treino():
    quadro, classes = _quadro(n=600)
    quadro.loc[::7, "tom"] = np.nan

    probabilidades = (
        LogisticaComValidacao().ajustar(quadro, classes).probabilidades(quadro)
    )

    assert np.isfinite(probabilidades).all()
