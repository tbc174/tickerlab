"""Registro de tentativas e trava do período lacrado do modelo C-1 (pré-registro v2, seções 4 e 9)."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from base.cripto.c1.lacre import (
    FIM_DO_DESENVOLVIMENTO,
    INICIO_DO_DESENVOLVIMENTO,
    INICIO_DO_LACRADO,
    CandidatoNaoAprovadoError,
    LacradoJaAbertoError,
    LacradoVazandoError,
    Lacre,
    PreRegistroAlteradoError,
    cortar_desenvolvimento,
    exigir_sem_lacrado,
)
from base.cripto.c1.registro import (
    ORCAMENTO,
    OrcamentoEstouradoError,
    Registro,
)

ESPEC = {
    "candidato": "logistica_ordinal",
    "entradas": "lista fechada v2",
    "grade": [0.01, 0.1],
}


@pytest.fixture
def registro(tmp_path):
    registro = Registro(tmp_path / "registro.db", commit="abc123")
    registro.registrar_ajuste("v2", "início da CFTC corrigido (10/04/2018)", 5)
    return registro


def test_comeca_com_5_da_v2(registro):
    assert registro.usadas() == 5


def test_ajuste_registrado_duas_vezes_conta_uma(registro):
    registro.registrar_ajuste("v2", "de novo", 5)

    assert registro.usadas() == 5


def test_cada_execucao_conta_mesmo_repetida(registro):
    # pré-registro v2, seção 9: "cada execução de treino e avaliação conta"
    primeira = registro.nova_tentativa(ESPEC, "desenvolvimento")
    repetida = registro.nova_tentativa(dict(reversed(ESPEC.items())), "desenvolvimento")

    assert repetida != primeira
    assert registro.usadas() == 7
    # a mesma especificação (em qualquer ordem) tem o mesmo hash, para rastrear
    assert registro.hash_da(primeira) == registro.hash_da(repetida)


def test_recusa_a_21a_tentativa(registro):
    for i in range(ORCAMENTO - 5):
        registro.nova_tentativa({**ESPEC, "i": i}, "desenvolvimento")

    with pytest.raises(OrcamentoEstouradoError):
        registro.nova_tentativa({**ESPEC, "i": "uma a mais"}, "desenvolvimento")


def test_p_das_outras_tentativas_para_o_holm(registro):
    a = registro.nova_tentativa({**ESPEC, "i": 1}, "desenvolvimento")
    b = registro.nova_tentativa({**ESPEC, "i": 2}, "desenvolvimento")
    registro.anotar_resultado(a, p_valor=0.2, ganho=0.01, aprovada=False)
    registro.anotar_resultado(b, p_valor=0.01, ganho=0.05, aprovada=True)

    assert registro.p_das_outras(b) == [0.2]


def test_fase_invalida_e_recusada(registro):
    with pytest.raises(ValueError, match="fase"):
        registro.nova_tentativa(ESPEC, "producao")


def _classes(inicio: date, fim: date) -> pd.Series:
    dias = [inicio + timedelta(days=i) for i in range((fim - inicio).days + 1)]
    return pd.Series(np.zeros(len(dias)), index=dias)


def test_desenvolvimento_vai_de_agosto_de_2018_a_30_dias_antes_do_lacrado():
    classes = _classes(date(2018, 1, 1), date(2024, 6, 30))
    quadro = pd.DataFrame({"x": 1.0}, index=classes.index)

    quadro_cortado, classes_cortadas = cortar_desenvolvimento(quadro, classes)

    assert classes_cortadas.index.min() == INICIO_DO_DESENVOLVIMENTO == date(2018, 8, 1)
    # o alvo do último dia (D+1 a D+30) termina antes do lacrado começar
    assert classes_cortadas.index.max() == FIM_DO_DESENVOLVIMENTO == date(2023, 9, 12)
    assert classes_cortadas.index.max() + timedelta(days=31) == INICIO_DO_LACRADO
    assert list(quadro_cortado.index) == list(classes_cortadas.index)


def test_lacre_recusa_alvo_que_usa_preco_do_lacrado():
    with pytest.raises(LacradoVazandoError):
        exigir_sem_lacrado(_classes(date(2023, 1, 1), date(2023, 9, 13)))

    exigir_sem_lacrado(_classes(date(2023, 1, 1), date(2023, 9, 12)))  # não levanta


@pytest.fixture
def pre_registro(tmp_path):
    caminho = tmp_path / "pre-registro.md"
    caminho.write_text("critério v2", encoding="utf-8")
    return caminho


def test_lacrado_exige_candidato_aprovado(registro, pre_registro, tmp_path):
    tentativa = registro.nova_tentativa(ESPEC, "desenvolvimento")
    registro.anotar_resultado(tentativa, p_valor=0.3, ganho=-0.01, aprovada=False)
    lacre = Lacre(tmp_path, pre_registro)

    with pytest.raises(CandidatoNaoAprovadoError):
        lacre.abrir(registro, tentativa)


def test_lacrado_so_abre_uma_vez(registro, pre_registro, tmp_path):
    tentativa = registro.nova_tentativa(ESPEC, "desenvolvimento")
    registro.anotar_resultado(tentativa, p_valor=0.01, ganho=0.05, aprovada=True)
    lacre = Lacre(tmp_path, pre_registro)

    lacre.abrir(registro, tentativa)

    with pytest.raises(LacradoJaAbertoError):
        Lacre(tmp_path, pre_registro).abrir(registro, tentativa)


def test_pre_registro_alterado_trava(registro, pre_registro, tmp_path):
    lacre = Lacre(tmp_path, pre_registro)  # guarda o hash do texto na primeira vez
    pre_registro.write_text("critério v2, mexido depois", encoding="utf-8")
    tentativa = registro.nova_tentativa(ESPEC, "desenvolvimento")
    registro.anotar_resultado(tentativa, p_valor=0.01, ganho=0.05, aprovada=True)

    with pytest.raises(PreRegistroAlteradoError):
        lacre.abrir(registro, tentativa)
