"""Testes de src/ficha.py: a ficha "Foi sorte?" (ADR 0037, D1 e D2)."""

import numpy as np
import pandas as pd
import pytest

from src import ficha
from src.ficha import Checagem, Situacao

PALAVRAS_PROIBIDAS = (
    "compre",
    "comprar agora",
    "garantid",
    "vai subir",
    "lucro certo",
    "recomendamos",
    "recomendo",
)


def _checagem(situacao, pergunta="Pergunta?"):
    return Checagem(pergunta, situacao, "Explicação.")


def _ficha(*situacoes):
    return ficha.Ficha(
        tuple(_checagem(s, f"Pergunta {i}?") for i, s in enumerate(situacoes)),
        tentativas=1,
    )


# --- Veredito -----------------------------------------------------------------------------


def test_veredito_passou_so_com_tudo_passando():
    v = _ficha(*[Situacao.PASSOU] * 5).veredito
    assert v.resultado is ficha.Resultado.PASSOU
    assert v.titulo == "Passou no teste contra a sorte"


def test_uma_falha_da_nao_passou_e_diz_qual():
    v = _ficha(
        Situacao.PASSOU,
        Situacao.NAO_PASSOU,
        Situacao.PASSOU,
        Situacao.SEM_MEDIDA,
        Situacao.PASSOU,
    ).veredito
    assert v.resultado is ficha.Resultado.NAO_PASSOU
    assert v.titulo == "Não passou no teste contra a sorte"
    assert "Pergunta 1?" in v.texto
    assert "Pergunta 3?" not in v.texto


def test_sem_medida_e_sem_falha_da_inconclusivo():
    v = _ficha(
        Situacao.PASSOU, Situacao.SEM_MEDIDA, Situacao.PASSOU, Situacao.PASSOU
    ).veredito
    assert v.resultado is ficha.Resultado.INCONCLUSIVO
    assert "Pergunta 1?" in v.texto


def test_nao_se_aplica_nao_pesa():
    v = _ficha(
        Situacao.NAO_SE_APLICA,
        Situacao.PASSOU,
        Situacao.PASSOU,
        Situacao.NAO_SE_APLICA,
        Situacao.PASSOU,
    ).veredito
    assert v.resultado is ficha.Resultado.PASSOU


def test_sem_nenhuma_checagem_que_passou_e_inconclusivo():
    v = _ficha(Situacao.NAO_SE_APLICA, Situacao.NAO_SE_APLICA).veredito
    assert v.resultado is ficha.Resultado.INCONCLUSIVO


@pytest.mark.parametrize(
    "situacoes",
    [
        [Situacao.PASSOU] * 5,
        [Situacao.NAO_PASSOU] * 5,
        [Situacao.PASSOU, Situacao.SEM_MEDIDA],
    ],
)
def test_todo_veredito_tem_o_aviso(situacoes):
    assert ficha.AVISO in _ficha(*situacoes).veredito.texto


@pytest.mark.parametrize(
    "situacoes",
    [
        [Situacao.PASSOU] * 5,
        [Situacao.NAO_PASSOU] * 5,
        [Situacao.PASSOU, Situacao.SEM_MEDIDA],
    ],
)
def test_veredito_nao_usa_palavras_proibidas(situacoes):
    v = _ficha(*situacoes).veredito
    texto = f"{v.titulo} {v.texto}".lower()
    assert not [p for p in PALAVRAS_PROIBIDAS if p in texto]


# --- Checagem 1: fora do período ----------------------------------------------------------


def test_fora_do_periodo_passa_com_sharpe_positivo_e_eficiencia_alta():
    c = ficha.checar_fora_do_periodo(0.8, 1.0, "walk-forward")
    assert c.situacao is Situacao.PASSOU
    assert "0,80" in c.explicacao


def test_eficiencia_baixa_nao_passa():
    assert (
        ficha.checar_fora_do_periodo(0.3, 1.0, "walk-forward").situacao
        is Situacao.NAO_PASSOU
    )


def test_sharpe_negativo_fora_do_periodo_nao_passa():
    assert (
        ficha.checar_fora_do_periodo(-0.2, 1.0, "treino e teste").situacao
        is Situacao.NAO_PASSOU
    )


def test_sem_ganho_nem_no_periodo_de_escolha_nao_passa():
    assert (
        ficha.checar_fora_do_periodo(0.5, -0.1, "walk-forward").situacao
        is Situacao.NAO_PASSOU
    )


def test_sem_operar_fora_do_periodo_nao_passa():
    assert (
        ficha.checar_fora_do_periodo(float("nan"), 1.0, "walk-forward").situacao
        is Situacao.NAO_PASSOU
    )


# --- Checagem 4: parâmetros vizinhos ------------------------------------------------------


def _mapa(valores, colunas=(10, 20, 30), linhas=(50, 100, 150)):
    return pd.DataFrame(valores, index=list(linhas), columns=list(colunas), dtype=float)


def test_vizinhos_de_um_pico_isolado_nao_passam():
    mapa = _mapa([[-0.2, -0.2, -0.2], [-0.2, 1.5, -0.2], [-0.2, -0.2, -0.2]])
    c = ficha.checar_vizinhos(mapa, (20, 100), 1.5)
    assert c.situacao is Situacao.NAO_PASSOU


def test_regiao_larga_passa():
    mapa = _mapa([[0.9, 1.0, 0.8], [1.0, 1.1, 0.9], [0.8, 0.9, 1.0]])
    assert ficha.checar_vizinhos(mapa, (20, 100), 1.1).situacao is Situacao.PASSOU


def test_vizinhos_bem_abaixo_da_metade_nao_passam():
    mapa = _mapa([[0.3, 0.3, 0.3], [0.3, 1.0, 0.3], [0.3, 0.3, 0.3]])
    assert ficha.checar_vizinhos(mapa, (20, 100), 1.0).situacao is Situacao.NAO_PASSOU


def test_vizinhos_sao_os_oito_em_volta():
    mapa = _mapa([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
    assert sorted(ficha.vizinhos(mapa, (20, 100))) == [1, 2, 3, 4, 6, 7, 8, 9]
    assert sorted(ficha.vizinhos(mapa, (10, 50))) == [2, 4, 5]


def test_configuracao_fora_da_grade_usa_a_mais_proxima():
    mapa = _mapa([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
    assert sorted(ficha.vizinhos(mapa, (22, 140))) == [4, 5, 6, 7, 9]


def test_uma_linha_so_usa_esquerda_e_direita():
    mapa = pd.DataFrame([[0.5, 0.9, 0.7]], index=[""], columns=[10, 20, 30])
    assert sorted(ficha.vizinhos(mapa, (20, ""))) == [0.5, 0.7]


def test_combinacoes_invalidas_sao_ignoradas():
    mapa = _mapa([[np.nan, 2, 3], [np.nan, 5, 6], [np.nan, 8, 9]])
    assert sorted(ficha.vizinhos(mapa, (20, 100))) == [2, 3, 6, 8, 9]


def test_sem_vizinho_valido_nao_deu_para_medir():
    mapa = pd.DataFrame([[np.nan, 1.0, np.nan]], index=[""], columns=[10, 20, 30])
    assert ficha.checar_vizinhos(mapa, (20, ""), 1.0).situacao is Situacao.SEM_MEDIDA
