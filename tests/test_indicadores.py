"""Testes de src/indicadores.py. Os números são pequenos para dar para conferir de cabeça."""

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_series_equal

from src.indicadores import (
    DIAS_POR_ANO,
    NOMES_DOS_MESES,
    calcular_drawdown,
    calcular_indice_sharpe,
    calcular_media_movel,
    calcular_media_por_mes,
    calcular_percentual_dias_positivos,
    calcular_retorno_acumulado,
    calcular_retorno_anualizado,
    calcular_retorno_diario,
    calcular_retorno_mensal,
    calcular_var_historico,
    calcular_volatilidade_anual,
    calcular_volatilidade_movel,
    encontrar_melhor_dia,
    encontrar_melhor_e_pior_mes,
    encontrar_pior_dia,
    encontrar_pior_drawdown,
    montar_tabela_retornos,
)


def test_retorno_diario():
    # 100 -> 110 sobe 10%; 110 -> 99 cai 10%. O primeiro dia não tem dia anterior.
    fechamento = pd.Series([100.0, 110.0, 99.0])
    esperado = pd.Series([np.nan, 0.10, -0.10])
    assert_series_equal(calcular_retorno_diario(fechamento), esperado)


def test_retorno_acumulado():
    # Subir 10% e cair 10% NÃO volta ao zero: 1,10 x 0,90 = 0,99, ou seja, -1%.
    retorno = pd.Series([np.nan, 0.10, -0.10])
    esperado = pd.Series([np.nan, 0.10, -0.01])
    assert_series_equal(calcular_retorno_acumulado(retorno), esperado)


def test_retorno_acumulado_bate_com_preco_final_sobre_inicial():
    fechamento = pd.Series([50.0, 55.0, 44.0, 60.0])
    acumulado = calcular_retorno_acumulado(calcular_retorno_diario(fechamento))
    assert acumulado.iloc[-1] == pytest.approx(60.0 / 50.0 - 1)


def test_media_movel():
    # Janela 3: média de [1,2,3] = 2, de [2,3,4] = 3, de [3,4,5] = 4.
    # Os dois primeiros dias não têm 3 valores, então ficam vazios.
    fechamento = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    esperado = pd.Series([np.nan, np.nan, 2.0, 3.0, 4.0])
    assert_series_equal(calcular_media_movel(fechamento, 3), esperado)


def test_volatilidade_anual():
    # Desvio padrão (amostral) de [+1%, -1%, +1%, -1%] = raiz(0,0004 / 3).
    retorno = pd.Series([0.01, -0.01, 0.01, -0.01])
    esperado = np.sqrt(0.0004 / 3) * np.sqrt(DIAS_POR_ANO)
    assert calcular_volatilidade_anual(retorno) == pytest.approx(esperado)


def test_volatilidade_ignora_o_primeiro_dia_vazio():
    com_vazio = pd.Series([np.nan, 0.01, -0.01, 0.01, -0.01])
    sem_vazio = pd.Series([0.01, -0.01, 0.01, -0.01])
    assert calcular_volatilidade_anual(com_vazio) == pytest.approx(
        calcular_volatilidade_anual(sem_vazio)
    )


def test_volatilidade_de_preco_parado_e_zero():
    retorno = pd.Series([0.0, 0.0, 0.0, 0.0])
    assert calcular_volatilidade_anual(retorno) == 0.0


def test_drawdown():
    # Picos até cada dia: 100, 120, 120, 120, 120.
    # 90 está 25% abaixo de 120; 60 está 50% abaixo; voltar a 120 zera a queda.
    fechamento = pd.Series([100.0, 120.0, 90.0, 120.0, 60.0])
    esperado = pd.Series([0.0, 0.0, -0.25, 0.0, -0.50])
    assert_series_equal(calcular_drawdown(fechamento), esperado)


def test_drawdown_nunca_e_positivo():
    fechamento = pd.Series([10.0, 12.0, 11.0, 15.0, 9.0, 20.0])
    assert (calcular_drawdown(fechamento) <= 0).all()


def test_drawdown_de_preco_sempre_subindo_e_zero():
    fechamento = pd.Series([10.0, 11.0, 12.0, 13.0])
    assert calcular_drawdown(fechamento).min() == 0.0


def test_retorno_anualizado_de_um_ano_inteiro():
    # 252 dias de +0,1% compõem (1,001)^252 - 1 em um ano.
    retorno = pd.Series([0.001] * 252)
    assert calcular_retorno_anualizado(retorno) == pytest.approx(1.001**252 - 1)


def test_retorno_anualizado_de_meio_ano_projeta_para_um_ano():
    # Meio ano (126 dias) de +0,2%: manter esse ritmo por 252 dias dá (1,002)^252 - 1.
    retorno = pd.Series([0.002] * 126)
    assert calcular_retorno_anualizado(retorno) == pytest.approx(1.002**252 - 1)


def test_retorno_anualizado_ignora_o_primeiro_dia_vazio():
    com_vazio = pd.Series([np.nan] + [0.001] * 252)
    sem_vazio = pd.Series([0.001] * 252)
    assert calcular_retorno_anualizado(com_vazio) == pytest.approx(
        calcular_retorno_anualizado(sem_vazio)
    )


def test_sharpe_com_taxa_zero():
    retorno = pd.Series([0.02, -0.01] * 126)
    anualizado = (1 + retorno).prod() ** (DIAS_POR_ANO / len(retorno)) - 1
    volatilidade = retorno.std() * np.sqrt(DIAS_POR_ANO)
    assert calcular_indice_sharpe(retorno) == pytest.approx(anualizado / volatilidade)


def test_sharpe_diminui_quando_a_taxa_livre_de_risco_sobe():
    retorno = pd.Series([0.02, -0.01] * 126)
    assert calcular_indice_sharpe(retorno, 0.10) < calcular_indice_sharpe(retorno, 0.0)


def test_sharpe_sem_volatilidade_e_nan():
    retorno = pd.Series([0.001] * 50)  # sobe igual todo dia: desvio padrão zero
    assert np.isnan(calcular_indice_sharpe(retorno))


def test_melhor_e_pior_dia():
    datas = pd.date_range("2026-01-01", periods=4)
    retorno = pd.Series([np.nan, 0.05, -0.03, 0.02], index=datas)
    assert encontrar_melhor_dia(retorno) == (pd.Timestamp("2026-01-02"), 0.05)
    assert encontrar_pior_dia(retorno) == (pd.Timestamp("2026-01-03"), -0.03)


# --- Extras da issue #7 -------------------------------------------------------


def test_percentual_dias_positivos():
    # Dias válidos: 4. Subiram: 2 (+1% e +3%). O dia parado (0%) não conta como alta.
    retorno = pd.Series([np.nan, 0.01, -0.02, 0.03, 0.0])
    assert calcular_percentual_dias_positivos(retorno) == pytest.approx(0.5)


def test_var_historico():
    # 101 retornos de -50% a +50%: o pior 1 dia em cada 20 (5%) fica em -45%.
    retorno = pd.Series(np.arange(-50, 51) / 100)
    assert calcular_var_historico(retorno) == pytest.approx(-0.45)
    assert calcular_var_historico(retorno, nivel=0.99) == pytest.approx(-0.49)


# --- Casos de borda: série vazia ou com um único dia --------------------------
# O app não pode quebrar se a pessoa pedir um período curto demais.


@pytest.mark.parametrize(
    "funcao",
    [
        calcular_retorno_anualizado,
        calcular_indice_sharpe,
        calcular_volatilidade_anual,
        calcular_percentual_dias_positivos,
        calcular_var_historico,
    ],
)
@pytest.mark.parametrize("retorno", [pd.Series([], dtype=float), pd.Series([np.nan])])
def test_sem_retornos_validos_devolve_nan(funcao, retorno):
    assert np.isnan(funcao(retorno))


@pytest.mark.parametrize("funcao", [encontrar_melhor_dia, encontrar_pior_dia])
def test_melhor_e_pior_dia_sem_dados_levantam_erro(funcao):
    with pytest.raises(ValueError, match="vazia"):
        funcao(pd.Series([np.nan]))


# --- Issue #8: volatilidade móvel e pior drawdown -------------------------------


def test_volatilidade_movel():
    # Janela 3 sobre [nan, +1%, -1%, +1%, -1%]: o primeiro valor só existe no 4º dia,
    # quando há 3 retornos válidos (+1%, -1%, +1%).
    retorno = pd.Series([np.nan, 0.01, -0.01, 0.01, -0.01])
    resultado = calcular_volatilidade_movel(retorno, janela=3)
    esperado = np.std([0.01, -0.01, 0.01], ddof=1) * np.sqrt(DIAS_POR_ANO)
    assert len(resultado) == len(retorno)
    assert resultado.iloc[:3].isna().all()
    assert resultado.iloc[3] == pytest.approx(esperado)
    assert resultado.iloc[4] == pytest.approx(
        esperado
    )  # (-1%, +1%, -1%) tem o mesmo desvio


def test_volatilidade_movel_de_preco_parado_e_zero():
    retorno = pd.Series([0.0] * 10)
    assert (calcular_volatilidade_movel(retorno, janela=5).dropna() == 0).all()


@pytest.mark.parametrize("janela", [1, 0, -5])
def test_volatilidade_movel_com_janela_invalida(janela):
    with pytest.raises(ValueError, match="janela"):
        calcular_volatilidade_movel(pd.Series([0.01, 0.02, 0.03]), janela=janela)


def _datas(n):
    return pd.date_range("2026-01-01", periods=n)


def test_pior_drawdown_sem_recuperacao():
    # Topo 120 (dia 4), fundo 60 (dia 5): queda de 50%. Nunca voltou a 120.
    fechamento = pd.Series([100.0, 120.0, 90.0, 120.0, 60.0, 100.0], index=_datas(6))
    pior = encontrar_pior_drawdown(fechamento)
    assert pior.queda == pytest.approx(-0.50)
    assert pior.data_topo == pd.Timestamp("2026-01-04")
    assert pior.data_fundo == pd.Timestamp("2026-01-05")
    assert pior.data_recuperacao is None


def test_pior_drawdown_com_recuperacao():
    # Topo 120 (dia 2), fundo 90 (dia 3), volta ao topo no dia 4 (130 passa de 120).
    fechamento = pd.Series([100.0, 120.0, 90.0, 130.0], index=_datas(4))
    pior = encontrar_pior_drawdown(fechamento)
    assert pior.queda == pytest.approx(-0.25)
    assert pior.data_topo == pd.Timestamp("2026-01-02")
    assert pior.data_fundo == pd.Timestamp("2026-01-03")
    assert pior.data_recuperacao == pd.Timestamp("2026-01-04")


def test_pior_drawdown_de_preco_sempre_subindo():
    fechamento = pd.Series([10.0, 11.0, 12.0], index=_datas(3))
    pior = encontrar_pior_drawdown(fechamento)
    assert pior == (0.0, None, None, None)


def test_pior_drawdown_sem_dados():
    pior = encontrar_pior_drawdown(pd.Series([], dtype=float))
    assert np.isnan(pior.queda)
    assert pior.data_fundo is None


# --- Issue #9: retorno por mês e por ano ------------------------------------------


def _retornos_de_dois_meses():
    # Fechamentos 100, 110, 121, 108,9 em quatro dias: retornos +10%, +10%, -10%.
    datas = pd.to_datetime(["2026-01-29", "2026-01-30", "2026-02-02", "2026-02-03"])
    return calcular_retorno_diario(pd.Series([100.0, 110.0, 121.0, 108.9], index=datas))


def test_retorno_mensal_compoe_os_retornos_do_mes():
    mensal = calcular_retorno_mensal(_retornos_de_dois_meses())
    assert list(mensal.index.astype(str)) == ["2026-01", "2026-02"]
    assert mensal.iloc[0] == pytest.approx(
        0.10
    )  # janeiro: só o +10% (o 1º dia não tem retorno)
    assert mensal.iloc[1] == pytest.approx(
        1.10 * 0.90 - 1
    )  # fevereiro: +10% e depois -10% = -1%


def test_retorno_mensal_nao_inventa_meses_sem_dados():
    datas = pd.to_datetime(["2026-01-30", "2026-02-02", "2026-04-01"])  # nada em março
    retorno = pd.Series([0.01, 0.02, 0.03], index=datas)
    meses = list(calcular_retorno_mensal(retorno).index.astype(str))
    assert meses == ["2026-01", "2026-02", "2026-04"]


def test_retorno_mensal_sem_dados():
    assert calcular_retorno_mensal(pd.Series([np.nan])).empty
    assert calcular_retorno_mensal(pd.Series([], dtype=float)).empty


def _mensal_de_exemplo():
    meses = pd.PeriodIndex(["2025-12", "2026-01", "2026-02"], freq="M")
    return pd.Series([0.05, 0.10, -0.01], index=meses)


def test_tabela_tem_um_ano_por_linha_e_os_doze_meses():
    tabela = montar_tabela_retornos(_mensal_de_exemplo())
    assert list(tabela.index) == [2025, 2026]
    assert list(tabela.columns) == [*NOMES_DOS_MESES, "Ano"]
    assert tabela.loc[2025, "Dez"] == pytest.approx(0.05)
    assert tabela.loc[2026, "Jan"] == pytest.approx(0.10)
    assert tabela.loc[2026, "Fev"] == pytest.approx(-0.01)


def test_tabela_deixa_vazios_os_meses_sem_dados():
    tabela = montar_tabela_retornos(_mensal_de_exemplo())
    assert np.isnan(tabela.loc[2025, "Jan"])
    assert np.isnan(tabela.loc[2026, "Dez"])


def test_total_do_ano_compoe_os_meses():
    tabela = montar_tabela_retornos(_mensal_de_exemplo())
    assert tabela.loc[2025, "Ano"] == pytest.approx(0.05)
    assert tabela.loc[2026, "Ano"] == pytest.approx(1.10 * 0.99 - 1)


def test_tabela_sem_dados_tem_so_as_colunas():
    tabela = montar_tabela_retornos(calcular_retorno_mensal(pd.Series([], dtype=float)))
    assert tabela.empty
    assert list(tabela.columns) == [*NOMES_DOS_MESES, "Ano"]


def test_media_por_mes_do_calendario():
    # Dois janeiros: +10% e +20% -> média 15%. Fevereiro só tem um: -2%.
    meses = pd.PeriodIndex(["2025-01", "2025-02", "2026-01"], freq="M")
    tabela = montar_tabela_retornos(pd.Series([0.10, -0.02, 0.20], index=meses))
    media = calcular_media_por_mes(tabela)
    assert media["Jan"] == pytest.approx(0.15)
    assert media["Fev"] == pytest.approx(-0.02)
    assert np.isnan(media["Mar"])


def test_melhor_e_pior_mes():
    (mes_melhor, melhor), (mes_pior, pior) = encontrar_melhor_e_pior_mes(
        _mensal_de_exemplo()
    )
    assert (str(mes_melhor), melhor) == ("2026-01", pytest.approx(0.10))
    assert (str(mes_pior), pior) == ("2026-02", pytest.approx(-0.01))


def test_melhor_e_pior_mes_sem_dados():
    with pytest.raises(ValueError, match="vazia"):
        encontrar_melhor_e_pior_mes(pd.Series([], dtype=float))


# --- Média exponencial, MACD e ATR --------------------------------------------------------


def test_media_movel_exponencial_pesa_mais_os_dias_recentes():
    # janela (span) 3 -> peso 0,5: 1; 1,5; 2,25. Os 2 primeiros ficam vazios (sem histórico).
    from src.indicadores import calcular_media_movel_exponencial

    resultado = calcular_media_movel_exponencial(pd.Series([1.0, 2.0, 3.0]), 3)
    assert resultado.iloc[:2].isna().all()
    assert resultado.iloc[2] == pytest.approx(2.25)


def test_macd_e_a_diferenca_entre_as_medias_exponenciais():
    from src.indicadores import calcular_macd, calcular_media_movel_exponencial

    fechamento = pd.Series(np.linspace(10, 20, 60) + np.sin(np.arange(60)))
    macd = calcular_macd(fechamento, rapida=5, lenta=10, sinal=3)
    esperado = calcular_media_movel_exponencial(
        fechamento, 5
    ) - calcular_media_movel_exponencial(fechamento, 10)
    assert macd["macd"].dropna().to_numpy() == pytest.approx(
        esperado.dropna().to_numpy()
    )
    assert (macd["histograma"] - (macd["macd"] - macd["sinal"])).abs().max() < 1e-12


def test_macd_de_preco_so_subindo_fica_positivo():
    from src.indicadores import calcular_macd

    macd = calcular_macd(pd.Series(np.linspace(10, 30, 80)))
    assert macd["macd"].dropna().iloc[-1] > 0


def test_atr_com_numeros_pequenos():
    from src.indicadores import calcular_atr

    dados = pd.DataFrame(
        {
            "High": [10.0, 11.0, 12.0],
            "Low": [9.0, 10.0, 10.0],
            "Close": [9.5, 10.5, 11.0],
        }
    )
    # amplitude verdadeira: 1; 1,5; 2. Suavização de Wilder com janela 3 (peso 1/3):
    # 1; 1,1667; 1,4444. Só o terceiro dia tem histórico suficiente.
    atr = calcular_atr(dados, janela=3)
    assert atr.iloc[:2].isna().all()
    assert atr.iloc[2] == pytest.approx(
        1.0 / 3 * 2 + 2.0 / 3 * (1.0 / 3 * 1.5 + 2.0 / 3 * 1.0)
    )


# --- RSI, Bandas de Bollinger e z-score -----------------------------------------------------


def test_rsi_com_numeros_pequenos():
    from src.indicadores import calcular_rsi

    # janela 2 (peso 1/2): variações +2 e -1 -> ganho médio 1, perda média 0,5 -> RS = 2
    rsi = calcular_rsi(pd.Series([10.0, 12.0, 11.0]), janela=2)
    assert rsi.iloc[:2].isna().all()
    assert rsi.iloc[2] == pytest.approx(100 - 100 / 3)


def test_rsi_so_de_altas_e_100_e_so_de_quedas_e_0():
    from src.indicadores import calcular_rsi

    assert calcular_rsi(pd.Series(np.arange(1.0, 30.0)), 14).iloc[-1] == 100
    assert calcular_rsi(pd.Series(np.arange(30.0, 1.0, -1)), 14).iloc[-1] == 0


def test_rsi_de_preco_parado_e_neutro():
    from src.indicadores import calcular_rsi

    assert calcular_rsi(pd.Series([5.0] * 30), 14).iloc[-1] == 50


def test_rsi_fica_entre_0_e_100():
    from src.indicadores import calcular_rsi

    rng = np.random.default_rng(3)
    serie = pd.Series(50 * np.cumprod(1 + rng.normal(0, 0.03, 300)))
    rsi = calcular_rsi(serie).dropna()
    assert rsi.between(0, 100).all()


def test_bandas_de_bollinger_com_numeros_pequenos():
    from src.indicadores import calcular_bandas_de_bollinger

    # [1, 2, 3]: média 2; desvio-padrão (população) = raiz(2/3) = 0,8165
    bandas = calcular_bandas_de_bollinger(
        pd.Series([1.0, 2.0, 3.0]), janela=3, desvios=2.0
    )
    desvio = np.sqrt(2 / 3)
    assert bandas["media"].iloc[2] == pytest.approx(2.0)
    assert bandas["superior"].iloc[2] == pytest.approx(2 + 2 * desvio)
    assert bandas["inferior"].iloc[2] == pytest.approx(2 - 2 * desvio)
    assert bandas["percentual_b"].iloc[2] == pytest.approx(
        (3 - (2 - 2 * desvio)) / (4 * desvio)
    )
    assert bandas["largura"].iloc[2] == pytest.approx(4 * desvio / 2)
    assert bandas["media"].iloc[:2].isna().all()


def test_bandas_de_preco_parado_nao_dividem_por_zero():
    from src.indicadores import calcular_bandas_de_bollinger

    bandas = calcular_bandas_de_bollinger(pd.Series([7.0] * 10), janela=3)
    assert bandas["percentual_b"].dropna().empty
    assert (bandas["largura"].dropna() == 0).all()


def test_zscore_com_numeros_pequenos():
    from src.indicadores import calcular_zscore

    z = calcular_zscore(pd.Series([1.0, 2.0, 3.0]), janela=3)
    assert z.iloc[2] == pytest.approx((3 - 2) / np.sqrt(2 / 3))


def test_zscore_de_preco_parado_nao_existe():
    from src.indicadores import calcular_zscore

    assert calcular_zscore(pd.Series([4.0] * 10), janela=3).dropna().empty


# --- saiu da tela do backtest (preparação para outra interface, 13/10/2026) ---------------------
def test_curva_de_capital_e_a_composicao_dos_retornos():
    from src import indicadores as ind

    retorno = pd.Series([0.01, -0.02, 0.03, np.nan, 0.0])
    assert_series_equal(ind.curva_de_capital(retorno), (1 + retorno).cumprod())
