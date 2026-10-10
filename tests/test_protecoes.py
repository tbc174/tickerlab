"""Testes de src/protecoes.py, com preços pequenos para conferir de cabeça."""

import numpy as np
import pandas as pd
import pytest

from src.estrategias import ESTRATEGIAS, gerar_posicao
from src.protecoes import Protecoes, aplicar_protecoes


def _dados(fechamentos, folga=0.0):
    f = np.array(fechamentos, dtype=float)
    return pd.DataFrame(
        {"Open": f, "High": f + folga, "Low": f - folga, "Close": f, "Volume": 1_000},
        index=pd.date_range("2026-01-05", periods=len(f), freq="B"),
    )


def _desejada(valores, dados):
    return pd.Series(valores, index=dados.index, dtype=float)


# --- sem proteção nada muda ---------------------------------------------------------------


def test_sem_nenhuma_protecao_a_posicao_nao_muda():
    dados = _dados([100, 101, 99, 98])
    desejada = _desejada([1, 1, 0, 1], dados)
    assert aplicar_protecoes(dados, desejada, Protecoes()).equals(desejada)


def test_o_original_nao_e_alterado():
    dados = _dados([100, 100, 90])
    desejada = _desejada([1, 1, 1], dados)
    aplicar_protecoes(dados, desejada, Protecoes(stop_loss=0.05))
    assert list(desejada) == [1, 1, 1]


# --- stop-loss ----------------------------------------------------------------------------


def test_stop_loss_sai_quando_perde_o_limite_desde_a_entrada():
    # entrada em 100; o limite é 90 (-10%); fecha em 89 no 4º dia
    dados = _dados([100, 100, 95, 89, 95, 100, 100])
    protegida = aplicar_protecoes(
        dados, _desejada([1] * 7, dados), Protecoes(stop_loss=0.10)
    )
    assert list(protegida) == [
        1,
        1,
        1,
        0,
        0,
        0,
        0,
    ]  # continua fora: a estratégia não "reiniciou"


def test_depois_do_stop_so_volta_com_um_sinal_novo_da_estrategia():
    dados = _dados([100, 100, 95, 89, 95, 100, 100])
    # a estratégia manda sair no 5º dia e entrar de novo no 6º
    desejada = _desejada([1, 1, 1, 1, 0, 1, 1], dados)
    protegida = aplicar_protecoes(dados, desejada, Protecoes(stop_loss=0.10))
    assert list(protegida) == [1, 1, 1, 0, 0, 1, 1]


def test_o_stop_nao_vale_no_dia_da_entrada():
    dados = _dados([100, 50, 50])  # o preço já "caiu" antes de a posição existir
    desejada = _desejada([0, 1, 1], dados)
    protegida = aplicar_protecoes(dados, desejada, Protecoes(stop_loss=0.10))
    assert list(protegida) == [
        0,
        1,
        1,
    ]  # entra em 50, que passa a ser o preço de entrada


# --- take-profit e stop móvel -----------------------------------------------------------


def test_take_profit_realiza_o_ganho():
    dados = _dados([100, 105, 111, 112])
    protegida = aplicar_protecoes(
        dados, _desejada([1, 1, 1, 1], dados), Protecoes(take_profit=0.10)
    )
    assert list(protegida) == [1, 1, 0, 0]


def test_stop_movel_acompanha_a_maxima():
    # máxima 120; o limite é 108 (-10% da máxima); 110 ainda passa, 107 não
    dados = _dados([100, 120, 110, 107, 108])
    protegida = aplicar_protecoes(
        dados, _desejada([1] * 5, dados), Protecoes(stop_movel=0.10)
    )
    assert list(protegida) == [1, 1, 1, 0, 0]


def test_stop_movel_e_stop_loss_lado_a_lado_pegam_primeiro_o_que_bater():
    dados = _dados([100, 120, 109, 107])
    # stop-loss de 10% desde 100 = 90 (não bate); móvel de 10% desde 120 = 108 (109 passa, 107 bate)
    protegida = aplicar_protecoes(
        dados, _desejada([1] * 4, dados), Protecoes(stop_loss=0.10, stop_movel=0.10)
    )
    assert list(protegida) == [1, 1, 1, 0]


# --- stop por ATR e tamanho por risco ------------------------------------------------------


def _preco_para_atr():
    # High = Low = Close: a amplitude verdadeira é o tamanho do salto do dia
    return _dados([100, 101, 102, 103, 104, 100, 99])


def test_stop_por_atr_usa_o_atr_do_dia_da_entrada():
    dados = _preco_para_atr()
    desejada = _desejada([0, 0, 1, 1, 1, 1, 1], dados)
    # ATR(3) no dia da entrada (3º dia) = 0,5556; stop = 102 - 2 x 0,5556 = 100,89
    protegida = aplicar_protecoes(
        dados, desejada, Protecoes(stop_atr=2.0, janela_atr=3)
    )
    assert list(protegida) == [0, 0, 1, 1, 1, 0, 0]  # 100 < 100,89 no 6º dia


def test_tamanho_por_risco_arrisca_uma_fracao_fixa_do_capital():
    dados = _preco_para_atr()
    desejada = _desejada([0, 0, 1, 1, 1, 0, 0], dados)
    protegida = aplicar_protecoes(
        dados, desejada, Protecoes(stop_atr=2.0, janela_atr=3, risco_por_operacao=0.01)
    )
    # amplitudes verdadeiras 0, 1, 1: ATR = 0, 1/3, 1/3 + (2/3) x 1/3 = 5/9 (Wilder, janela 3)
    atr_da_entrada = 1 / 3 + (2 / 3) * (1 / 3)
    distancia_relativa = 2.0 * atr_da_entrada / 102
    esperado = 0.01 / distancia_relativa  # arrisca 1% do capital: ~92% da carteira
    assert protegida.iloc[2] == pytest.approx(esperado)
    assert protegida.iloc[3] == pytest.approx(
        esperado
    )  # o tamanho se mantém durante a operação


def test_tamanho_por_risco_nunca_passa_de_100_por_cento():
    dados = _preco_para_atr()
    protegida = aplicar_protecoes(
        dados,
        _desejada([0, 0, 1, 1, 1, 1, 1], dados),
        Protecoes(stop_atr=2.0, janela_atr=3, risco_por_operacao=1.0),
    )
    assert protegida.max() <= 1.0


def test_sem_atr_ainda_nao_entra():
    dados = _preco_para_atr()
    protegida = aplicar_protecoes(
        dados, _desejada([1] * 7, dados), Protecoes(stop_atr=2.0, janela_atr=3)
    )
    assert list(protegida.iloc[:2]) == [0, 0]  # o ATR(3) só existe a partir do 3º dia
    assert protegida.iloc[2] == 1


# --- alvo de volatilidade -----------------------------------------------------------------------


def test_alvo_de_volatilidade_reduz_a_posicao_quando_o_mercado_esta_agitado():
    retornos = np.tile([0.02, -0.02], 30)  # bem agitado: ~32% ao ano
    dados = _dados(100 * np.cumprod(1 + retornos))
    protegida = aplicar_protecoes(
        dados,
        _desejada([1] * 60, dados),
        Protecoes(alvo_de_volatilidade=0.16, janela_volatilidade=20),
    )
    janela = pd.Series(retornos[-20:])
    esperado = 0.16 / (janela.std() * np.sqrt(252))
    assert protegida.iloc[-1] == pytest.approx(esperado, rel=0.05)
    assert protegida.iloc[-1] < 1


def test_alvo_de_volatilidade_nao_alavanca_mercado_calmo():
    retornos = np.tile([0.001, -0.001], 30)  # muito calmo: ~1,6% ao ano
    dados = _dados(100 * np.cumprod(1 + retornos))
    protegida = aplicar_protecoes(
        dados,
        _desejada([1] * 60, dados),
        Protecoes(alvo_de_volatilidade=0.15, janela_volatilidade=20),
    )
    assert protegida.iloc[-1] == 1.0  # trava em 100%: sem dinheiro emprestado


def test_alvo_de_volatilidade_sem_historico_fica_em_caixa():
    dados = _dados(np.linspace(100, 110, 30))
    protegida = aplicar_protecoes(
        dados,
        _desejada([1] * 30, dados),
        Protecoes(alvo_de_volatilidade=0.15, janela_volatilidade=20),
    )
    assert (protegida.iloc[:20] == 0).all()


# --- validação ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "protecoes",
    [
        Protecoes(stop_loss=0.0),
        Protecoes(stop_loss=1.0),
        Protecoes(stop_movel=-0.1),
        Protecoes(take_profit=0.0),
        Protecoes(stop_atr=-1.0),
        Protecoes(alvo_de_volatilidade=0.0),
        Protecoes(stop_atr=2.0, risco_por_operacao=0.0),
        Protecoes(stop_atr=2.0, janela_atr=1),
    ],
)
def test_valores_invalidos_sao_barrados(protecoes):
    dados = _dados([100, 101, 102])
    with pytest.raises(ValueError):
        aplicar_protecoes(dados, _desejada([1, 1, 1], dados), protecoes)


def test_risco_por_operacao_exige_stop_atr():
    dados = _dados([100, 101, 102])
    with pytest.raises(ValueError, match="stop por ATR"):
        aplicar_protecoes(
            dados, _desejada([1, 1, 1], dados), Protecoes(risco_por_operacao=0.01)
        )


# --- as proteções também não olham o futuro --------------------------------------------------------


def _dados_sinteticos(dias=400, semente=5):
    rng = np.random.default_rng(semente)
    fechamento = 20 * np.cumprod(1 + rng.normal(0.0004, 0.015, dias))
    return pd.DataFrame(
        {
            "Open": fechamento * 0.999,
            "High": fechamento * 1.01,
            "Low": fechamento * 0.99,
            "Close": fechamento,
            "Volume": 1_000,
        },
        index=pd.date_range("2024-01-01", periods=dias, freq="B"),
    )


TUDO_LIGADO = Protecoes(
    stop_loss=0.08,
    take_profit=0.15,
    stop_movel=0.10,
    stop_atr=2.0,
    risco_por_operacao=0.02,
    alvo_de_volatilidade=0.15,
    dias_de_espera=5,
)


@pytest.mark.parametrize("nome", list(ESTRATEGIAS))
def test_protecoes_nao_olham_o_futuro_em_nenhuma_estrategia(nome):
    # cortar os dias finais não pode mudar a posição protegida dos dias iniciais
    dados = _dados_sinteticos(400)
    completa = aplicar_protecoes(dados, gerar_posicao(nome, dados), TUDO_LIGADO)
    cortada_dados = dados.iloc[:300]
    cortada = aplicar_protecoes(
        cortada_dados, gerar_posicao(nome, cortada_dados), TUDO_LIGADO
    )
    assert completa.iloc[:300].to_numpy() == pytest.approx(cortada.to_numpy())


@pytest.mark.parametrize("nome", list(ESTRATEGIAS))
def test_posicao_protegida_fica_entre_zero_e_um(nome):
    dados = _dados_sinteticos()
    posicao = aplicar_protecoes(dados, gerar_posicao(nome, dados), TUDO_LIGADO)
    assert not posicao.isna().any()
    assert posicao.between(0, 1).all()


# --- espera depois do stop (estratégias que nunca mandam sair) ------------------------------------


def test_sem_espera_comprar_e_segurar_nao_volta_depois_do_stop():
    dados = _dados([100, 100, 95, 89, 95, 100, 100])
    protegida = aplicar_protecoes(
        dados, _desejada([1] * 7, dados), Protecoes(stop_loss=0.10)
    )
    assert list(protegida) == [1, 1, 1, 0, 0, 0, 0]


def test_com_espera_volta_depois_dos_dias_combinados():
    dados = _dados([100, 100, 95, 89, 95, 100, 100])
    protegida = aplicar_protecoes(
        dados, _desejada([1] * 7, dados), Protecoes(stop_loss=0.10, dias_de_espera=2)
    )
    # o stop é no 4º dia; espera 2 dias (5º e 6º); no 7º volta, com novo preço de entrada
    assert list(protegida) == [1, 1, 1, 0, 0, 0, 1]


def test_a_espera_nao_atrapalha_o_sinal_novo_da_estrategia():
    dados = _dados([100, 100, 95, 89, 95, 100, 100])
    desejada = _desejada([1, 1, 1, 1, 0, 1, 1], dados)  # sai no 5º dia, volta no 6º
    protegida = aplicar_protecoes(
        dados, desejada, Protecoes(stop_loss=0.10, dias_de_espera=20)
    )
    assert list(protegida) == [1, 1, 1, 0, 0, 1, 1]


def test_o_novo_preco_de_entrada_vale_depois_da_espera():
    # volta em 200; um stop de 10% passa a valer sobre 200 (limite 180), e não sobre 100
    dados = _dados([100, 100, 89, 150, 200, 190, 179])
    protegida = aplicar_protecoes(
        dados, _desejada([1] * 7, dados), Protecoes(stop_loss=0.10, dias_de_espera=1)
    )
    # stop no 3º dia (89); espera o 4º; no 5º (200) entra de novo; 190 passa; 179 < 180 sai
    assert list(protegida) == [1, 1, 0, 0, 1, 1, 0]


def test_espera_invalida():
    dados = _dados([100, 101])
    with pytest.raises(ValueError, match="espera"):
        aplicar_protecoes(
            dados, _desejada([1, 1], dados), Protecoes(stop_loss=0.1, dias_de_espera=0)
        )
