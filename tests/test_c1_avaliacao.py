"""Avaliação e teste contra a sorte do modelo C-1 (pré-registro v2, seções 7 e 8), em dados
sintéticos. Os testes de ponta a ponta mostram que o critério reprova ruído e aprova sinal de verdade."""

from datetime import date, timedelta
from typing import ClassVar

import numpy as np
import pandas as pd
import pytest

from base.cripto.c1.avaliacao import calibracao, estabilidade_por_ano, walk_forward
from base.cripto.c1.candidatos import LogisticaComValidacao
from base.cripto.c1.entradas import COLUNAS
from base.cripto.c1.reguas import Har
from base.cripto.c1.sorte import (
    diebold_mariano,
    embaralhar_em_blocos,
    holm,
    veredito,
)

INICIO = date(2016, 1, 1)


def _quadro(
    n: int = 2200, semente: int = 5, sinal: float = 0.0
) -> tuple[pd.DataFrame, pd.Series]:
    """Dias seguidos com entradas sintéticas; o alvo segue a volatilidade passada e, com `sinal`,
    também a entrada `wikipedia` (persistente, como uma série de atenção de verdade)."""
    rng = np.random.default_rng(semente)
    dias = [INICIO + timedelta(days=i) for i in range(n)]
    quadro = pd.DataFrame(
        rng.normal(size=(n, len(COLUNAS))), columns=COLUNAS, index=dias
    )
    atencao = pd.Series(rng.normal(size=n)).ewm(span=20).mean().to_numpy() * 3
    quadro["wikipedia"] = atencao
    passada = np.exp(rng.normal(np.log(1.5), 0.4, n))
    for coluna in ("vol_1", "vol_7", "vol_30", "vol_90"):
        quadro[coluna] = passada * np.exp(rng.normal(0, 0.1, n))
    quadro["limite_inferior"], quadro["limite_superior"] = 1.0, 2.0
    quadro["alvo"] = np.exp(
        0.8 * np.log(passada) + sinal * atencao + rng.normal(0, 0.15, n)
    )
    classes = pd.Series(np.digitize(quadro["alvo"], [1.0, 2.0]), index=dias)
    return quadro, classes


class _Espiao:
    """Modelo falso que guarda o último dia de cada treino."""

    treinos: ClassVar[list[date]] = []

    def ajustar(self, quadro, classes):
        _Espiao.treinos.append(quadro.index.max())
        return self

    def probabilidades(self, quadro):
        return np.full((len(quadro), 3), 1 / 3)


def test_intervalo_de_30_dias_entre_o_treino_e_o_teste():
    quadro, classes = _quadro(n=900)
    _Espiao.treinos = []

    resultado = walk_forward(
        quadro, classes, {"espiao": _Espiao}, date(2017, 1, 1), date(2018, 3, 31)
    )

    inicios = sorted({d.replace(day=1) for d in resultado.classes.index})
    for inicio_do_teste, fim_do_treino in zip(inicios, _Espiao.treinos, strict=True):
        # o alvo do último dia do treino (D+1 a D+30) já tinha terminado antes do teste começar
        assert fim_do_treino + timedelta(days=31) <= inicio_do_teste


def test_retreino_todo_mes():
    quadro, classes = _quadro(n=900)
    _Espiao.treinos = []

    walk_forward(
        quadro, classes, {"espiao": _Espiao}, date(2017, 1, 1), date(2017, 6, 30)
    )

    assert len(_Espiao.treinos) == 6


def test_diebold_mariano_com_newey_west_conferido_a_mao():
    # diferenças 1, -1, 1, -1, ... com média -0,1 (n = 10), 1 defasagem
    d = np.array([1, -1, 1, -1, 1, -1, 1, -1, 0, -1], dtype=float)
    estatistica, p = diebold_mariano(d, np.zeros(10), defasagens=1)

    media = d.mean()
    centrado = d - media
    gama0 = (centrado @ centrado) / 10
    gama1 = (centrado[1:] @ centrado[:-1]) / 10
    variancia = (gama0 + 2 * 0.5 * gama1) / 10
    assert estatistica == pytest.approx(media / np.sqrt(variancia))
    assert 0 < p < 1


def test_holm():
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])


def test_embaralhamento_em_blocos_mantem_os_blocos():
    quadro = pd.DataFrame({"x": np.arange(360), "fica": np.arange(360)})

    embaralhado = embaralhar_em_blocos(
        quadro, ["x"], tamanho_do_bloco=90, rng=np.random.default_rng(0)
    )

    blocos = [tuple(embaralhado["x"].iloc[i : i + 90]) for i in range(0, 360, 90)]
    originais = {tuple(range(i, i + 90)) for i in range(0, 360, 90)}
    assert set(blocos) == originais
    assert (embaralhado["fica"] == quadro["fica"]).all()


def test_calibracao_de_previsao_calibrada_e_perto_de_zero():
    rng = np.random.default_rng(1)
    probabilidades = rng.dirichlet([1, 1, 1], size=20_000)
    classes = np.array([rng.choice(3, p=p) for p in probabilidades])

    assert calibracao(probabilidades, classes) < 0.02


def test_calibracao_de_previsao_confiante_demais_e_alta():
    classes = np.zeros(1000, dtype=int)
    classes[::2] = 1  # acerta metade
    probabilidades = np.tile([0.99, 0.005, 0.005], (1000, 1))

    assert calibracao(probabilidades, classes) == pytest.approx(0.49, abs=0.01)


def test_estabilidade_por_ano():
    dias = pd.Index(
        [date(2024, 1, 1), date(2024, 6, 1), date(2025, 1, 1), date(2026, 1, 1)]
    )
    ganho = pd.Series([0.1, 0.1, -0.2, 0.05], index=dias)

    assert estabilidade_por_ano(ganho) == {
        2024: pytest.approx(0.1),
        2025: pytest.approx(-0.2),
        2026: pytest.approx(0.05),
    }


def _veredito(sinal: float):
    quadro, classes = _quadro(sinal=sinal)
    fabricas = {"candidato": LogisticaComValidacao, "har": Har}
    resultado = walk_forward(
        quadro,
        classes,
        fabricas,
        date(2018, 1, 1),
        date(2021, 12, 31),
        meses_entre_treinos=6,
    )
    return veredito(
        resultado,
        candidato="candidato",
        regua="har",
        p_das_outras_tentativas=[],
        quadro=quadro,
        classes=classes,
        fabrica_do_candidato=LogisticaComValidacao,
        rodadas=20,
        rng=np.random.default_rng(2),
    )


def test_ruido_nao_passa_no_teste_contra_a_sorte():
    assert not _veredito(sinal=0.0).passou


def test_sinal_verdadeiro_passa():
    resultado = _veredito(sinal=0.25)

    assert resultado.ganho > 0
    assert resultado.passou, resultado
