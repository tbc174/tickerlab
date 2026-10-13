"""Testes de src/ficha.py: a ficha "Foi sorte?" (ADR 0037, D1 e D2)."""

from itertools import pairwise

import numpy as np
import pandas as pd
import pytest

from src import ficha
from src.backtest import CUSTO_PADRAO_POR_OPERACAO, executar_backtest
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


# --- Checagem 2: custos e imposto ---------------------------------------------------------


def test_custo_abaixo_do_padrao_sobe_para_o_padrao():
    assert ficha.custo_da_checagem(0.0) == CUSTO_PADRAO_POR_OPERACAO
    assert ficha.custo_da_checagem(0.002) == 0.002


def test_liquido_abaixo_do_cdi_nao_passa():
    c = ficha.checar_custos_e_imposto(0.08, 0.10)
    assert c.situacao is Situacao.NAO_PASSOU
    assert "+8,0%" in c.explicacao and "+10,0%" in c.explicacao


def test_liquido_acima_do_cdi_passa():
    assert ficha.checar_custos_e_imposto(0.15, 0.10).situacao is Situacao.PASSOU


def test_sem_cdi_compara_com_zero_e_avisa():
    c = ficha.checar_custos_e_imposto(0.03, None)
    assert c.situacao is Situacao.PASSOU
    assert "sem o CDI" in c.explicacao
    assert ficha.checar_custos_e_imposto(-0.01, None).situacao is Situacao.NAO_PASSOU


def test_imposto_reduz_o_retorno_liquido():
    fechamento = pd.Series(
        np.linspace(100, 200, 300), index=pd.bdate_range("2022-01-03", periods=300)
    )
    posicao = pd.Series(1.0, index=fechamento.index)
    posicao.iloc[150:] = 0.0  # vende no meio, com lucro: paga imposto
    sem_imposto = (
        executar_backtest(fechamento, posicao, 0.0).curva_de_capital.iloc[-1] - 1
    )
    liquido = ficha.retorno_liquido(fechamento, posicao, 0.0, 100_000.0)
    assert liquido < sem_imposto


# --- Checagem 5: quedas -------------------------------------------------------------------


def test_queda_acima_da_tolerancia_nao_passa():
    c = ficha.checar_quedas(-0.35, 0.30, "no Monte Carlo")
    assert c.situacao is Situacao.NAO_PASSOU
    assert "35%" in c.explicacao and "30%" in c.explicacao


def test_queda_dentro_da_tolerancia_passa():
    assert (
        ficha.checar_quedas(-0.20, 0.30, "no Monte Carlo").situacao is Situacao.PASSOU
    )


def test_poucas_operacoes_usa_a_queda_real():
    curva = pd.Series([1.0, 1.2, 0.9, 1.1])
    queda, fonte = ficha.queda_no_pior_caso_comum(pd.Series([0.2, -0.1]), curva)
    assert queda == pytest.approx(0.9 / 1.2 - 1)
    assert "real" in fonte


def test_com_operacoes_suficientes_usa_o_monte_carlo():
    operacoes = pd.Series([0.1, -0.15, 0.1, -0.15, 0.1, -0.15, 0.1])
    curva = (1 + operacoes).cumprod()
    queda, fonte = ficha.queda_no_pior_caso_comum(operacoes, curva)
    assert "Monte Carlo" in fonte
    assert (
        queda < (curva / curva.cummax() - 1).min()
    )  # o pior caso comum é pior que o real


# --- Checagem 3: acaso com as tentativas --------------------------------------------------


def _retorno_bom(n=750, semente=3):
    rng = np.random.default_rng(semente)
    return pd.Series(
        rng.normal(0.0008, 0.01, n), index=pd.bdate_range("2021-01-04", periods=n)
    )


def test_mais_tentativas_nunca_melhora_a_checagem_3():
    retorno = _retorno_bom()
    for variancia in (1e-5, 1e-4, 1e-3):
        chances = [
            ficha.chance_de_nao_ser_sorte(retorno, variancia, n)
            for n in (1, 2, 5, 10, 37, 100, 1_000, 10_000)
        ]
        assert all(a >= b for a, b in pairwise(chances))


def test_tentativas_somam_a_grade_e_as_da_pessoa():
    assert ficha.total_de_tentativas(49, 1) == 49
    assert (
        ficha.total_de_tentativas(49, 37) == 85
    )  # a configuração atual já está na grade
    assert ficha.total_de_tentativas(0, 1) == 1


def test_acaso_passa_com_p_baixo_e_chance_alta():
    c = ficha.checar_acaso(0.01, 0.97, 85)
    assert c.situacao is Situacao.PASSOU
    assert "85" in c.explicacao


def test_p_valor_alto_nao_passa_mesmo_com_chance_alta():
    assert ficha.checar_acaso(0.20, 0.99, 10).situacao is Situacao.NAO_PASSOU


def test_chance_baixa_nao_passa_mesmo_com_p_baixo():
    assert ficha.checar_acaso(0.01, 0.80, 10).situacao is Situacao.NAO_PASSOU


def test_sem_grade_usa_a_variancia_do_acaso():
    dados = pd.DataFrame({"Close": 100 * (1 + _retorno_bom()).cumprod()})
    posicao = pd.Series(1.0, index=dados.index)
    posicao.iloc[::40] = 0.0  # opera de vez em quando, para o deslocamento mudar algo
    c = ficha.medir_acaso(dados["Close"], posicao, 0.0005, 0.0, None, 5)
    assert c.situacao in (Situacao.PASSOU, Situacao.NAO_PASSOU)
    assert "5 tentativas" in c.explicacao


def test_poucos_dados_no_acaso_nao_deu_para_medir():
    fechamento = pd.Series(
        np.linspace(100, 110, 40), index=pd.bdate_range("2024-01-02", periods=40)
    )
    posicao = pd.Series(1.0, index=fechamento.index)
    c = ficha.medir_acaso(fechamento, posicao, 0.0005, 0.0, None, 1)
    assert c.situacao is Situacao.SEM_MEDIDA
