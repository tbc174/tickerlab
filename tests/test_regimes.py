"""Testes de src/regimes.py."""

import numpy as np
import pandas as pd
import pytest

from src import regimes as rg
from src.backtest import executar_backtest


def _precos(n=800, semente=3, deriva=0.0004, vol=0.012):
    rng = np.random.default_rng(semente)
    return pd.Series(
        100 * np.cumprod(1 + rng.normal(deriva, vol, n)),
        index=pd.bdate_range("2021-01-04", periods=n),
    )


def _precos_calmo_depois_agitado():
    rng = np.random.default_rng(1)
    retornos = np.concatenate(
        [rng.normal(0.0005, 0.004, 300), rng.normal(0.0, 0.03, 300)]
    )
    return pd.Series(
        100 * np.cumprod(1 + retornos), index=pd.bdate_range("2021-01-04", periods=600)
    )


# --- regimes ------------------------------------------------------------------------------


def test_volatilidade_separa_o_trecho_calmo_do_agitado():
    regime = rg.classificar_regimes_de_volatilidade(_precos_calmo_depois_agitado())
    assert regime.iloc[:60].eq(rg.SEM_HISTORICO).all()
    assert (regime.iloc[350 : 300 + 300] == "Agitado").mean() > 0.9
    # no trecho calmo a mediana separa na sorte (cerca de metade); o agitado quase não tem "Calmo"
    assert (regime.iloc[100:290] == "Agitado").mean() < 0.7


def test_regimes_nao_olham_o_futuro():
    precos = _precos()
    completo = rg.classificar_regimes_de_volatilidade(precos)
    cortado = rg.classificar_regimes_de_volatilidade(precos.iloc[:-100])
    assert completo.iloc[:-100].equals(cortado)
    completo = rg.classificar_regimes_de_tendencia(precos)
    cortado = rg.classificar_regimes_de_tendencia(precos.iloc[:-100])
    assert completo.iloc[:-100].equals(cortado)


def test_tendencia_alta_e_baixa():
    indice = pd.bdate_range("2021-01-04", periods=400)
    sobe = pd.Series(np.linspace(100, 200, 400), index=indice)
    assert rg.classificar_regimes_de_tendencia(sobe).iloc[-1] == "Alta"
    assert (
        rg.classificar_regimes_de_tendencia(sobe.iloc[::-1].set_axis(indice)).iloc[-1]
        == "Baixa"
    )
    assert rg.classificar_regimes_de_tendencia(sobe).iloc[0] == rg.SEM_HISTORICO


def test_classificadores_validam_entradas():
    precos = _precos(100)
    with pytest.raises(ValueError, match="janela"):
        rg.classificar_regimes_de_volatilidade(precos, janela=1)
    with pytest.raises(ValueError, match="percentil"):
        rg.classificar_regimes_de_volatilidade(precos, percentil=1.0)
    with pytest.raises(ValueError, match="janela"):
        rg.classificar_regimes_de_tendencia(precos, janela=1)


def test_resumo_por_regime_mostra_a_volatilidade_maior_no_agitado():
    precos = _precos_calmo_depois_agitado()
    regime = rg.classificar_regimes_de_volatilidade(precos)
    resumo = rg.resumir_por_regime(precos.pct_change().fillna(0.0), regime)
    assert set(resumo.index) == {"Calmo", "Agitado"}
    assert (
        resumo.loc["Agitado", "Volatilidade anual"]
        > 2 * resumo.loc["Calmo", "Volatilidade anual"]
    )
    assert resumo["% do tempo"].sum() < 1.0  # falta o trecho sem histórico


def test_resumo_usa_o_regime_da_vespera():
    indice = pd.bdate_range("2026-01-05", periods=6)
    retorno = pd.Series([0.0, 0.01, 0.02, -0.01, 0.03, 0.04], index=indice)
    regime = pd.Series(["A", "A", "B", "B", "A", "A"], index=indice)
    resumo = rg.resumir_por_regime(retorno, regime)
    # dias com véspera "A": 1, 2 e 5; com véspera "B": 3 e 4
    assert resumo.loc["A", "Retorno médio por dia"] == pytest.approx(
        np.mean([0.01, 0.02, 0.04])
    )
    assert resumo.loc["B", "Dias"] == 2


def test_resumo_valida_entradas():
    precos = _precos(100)
    with pytest.raises(ValueError, match="mesmas datas"):
        rg.resumir_por_regime(precos.pct_change(), pd.Series(dtype=object))
    sem = pd.Series(rg.SEM_HISTORICO, index=precos.index)
    with pytest.raises(ValueError, match="Poucos dias"):
        rg.resumir_por_regime(precos.pct_change(), sem)


def test_filtro_por_regime_zera_fora_do_regime():
    indice = pd.bdate_range("2026-01-05", periods=4)
    posicao = pd.Series(1.0, index=indice)
    regime = pd.Series(["Calmo", "Agitado", "Calmo", rg.SEM_HISTORICO], index=indice)
    filtrada = rg.filtrar_por_regime(posicao, regime, ("Calmo",))
    assert list(filtrada) == [1.0, 0.0, 1.0, 0.0]
    with pytest.raises(ValueError, match="pelo menos um"):
        rg.filtrar_por_regime(posicao, regime, ())
    with pytest.raises(ValueError, match="mesmas datas"):
        rg.filtrar_por_regime(posicao.iloc[1:], regime, ("Calmo",))


def test_ficar_fora_do_agitado_reduz_a_volatilidade_da_estrategia():
    precos = _precos_calmo_depois_agitado()
    posicao = pd.Series(1.0, index=precos.index)
    regime = rg.classificar_regimes_de_volatilidade(precos)
    filtrada = rg.filtrar_por_regime(posicao, regime, ("Calmo",))
    base = executar_backtest(precos, posicao, 0.0)
    com_filtro = executar_backtest(precos, filtrada, 0.0)
    assert com_filtro.retorno.std() < base.retorno.std()


# --- variância gerida ---------------------------------------------------------------------


def test_variancia_gerida_nunca_alavanca_e_corta_no_agitado():
    precos = _precos_calmo_depois_agitado()
    posicao = pd.Series(1.0, index=precos.index)
    gerida = rg.gerir_pela_variancia(precos, posicao)
    assert gerida.between(0, 1).all()
    assert gerida.iloc[400:].mean() < gerida.iloc[100:290].mean()
    assert gerida.iloc[:60].eq(0).all()  # sem histórico, fica em caixa


def test_variancia_gerida_nao_olha_o_futuro():
    precos = _precos()
    posicao = pd.Series(1.0, index=precos.index)
    completo = rg.gerir_pela_variancia(precos, posicao)
    cortado = rg.gerir_pela_variancia(precos.iloc[:-100], posicao.iloc[:-100])
    assert np.allclose(completo.iloc[:-100], cortado)


# --- disjuntor ----------------------------------------------------------------------------


def _queda_e_recuperacao():
    # sobe 20 dias, cai 30% em 10 dias, depois segue lateral
    valores = np.concatenate(
        [np.linspace(100, 120, 20), np.linspace(120, 84, 10), np.full(40, 84.0)]
    )
    return pd.Series(valores, index=pd.bdate_range("2026-01-05", periods=len(valores)))


def test_disjuntor_dispara_na_queda_e_trava_pelo_prazo():
    precos = _queda_e_recuperacao()
    posicao = pd.Series(1.0, index=precos.index)
    r = rg.aplicar_disjuntor_de_drawdown(precos, posicao, 0.10, 15, 0.0)
    assert len(r.acionamentos) >= 1
    disparo = precos.index.get_loc(r.acionamentos[0])
    assert (r.posicao.iloc[disparo : disparo + 15] == 0).all()
    assert r.posicao.iloc[:disparo].eq(1.0).all()
    assert r.dias_parado >= 15


def test_sem_queda_o_disjuntor_nao_muda_nada():
    precos = pd.Series(
        np.linspace(100, 200, 200), index=pd.bdate_range("2026-01-05", periods=200)
    )
    posicao = pd.Series(1.0, index=precos.index)
    r = rg.aplicar_disjuntor_de_drawdown(precos, posicao, 0.10, 10, 0.001)
    assert r.posicao.equals(posicao) and len(r.acionamentos) == 0
    assert r.dias_parado == 0


def test_disjuntor_evita_parte_da_queda_mas_nao_toda():
    precos = _queda_e_recuperacao()
    posicao = pd.Series(1.0, index=precos.index)
    r = rg.aplicar_disjuntor_de_drawdown(precos, posicao, 0.10, 15, 0.0)
    com = executar_backtest(precos, r.posicao, 0.0)
    sem = executar_backtest(precos, posicao, 0.0)
    assert com.curva_de_capital.iloc[-1] > sem.curva_de_capital.iloc[-1]
    assert com.curva_de_capital.iloc[-1] < 1.2  # ainda perdeu 10% do topo até o disparo


def test_disjuntor_nao_dispara_de_novo_pela_mesma_queda_antiga():
    precos = _queda_e_recuperacao()
    posicao = pd.Series(1.0, index=precos.index)
    r = rg.aplicar_disjuntor_de_drawdown(precos, posicao, 0.10, 5, 0.0)
    # depois da pausa, o preço está parado: o topo é refeito e não há novo disparo
    assert len(r.acionamentos) == 1


def test_disjuntor_nao_olha_o_futuro():
    precos = _precos(500)
    rng = np.random.default_rng(5)
    posicao = pd.Series(rng.integers(0, 2, 500).astype(float), index=precos.index)
    completo = rg.aplicar_disjuntor_de_drawdown(precos, posicao, 0.08, 10)
    cortado = rg.aplicar_disjuntor_de_drawdown(
        precos.iloc[:-80], posicao.iloc[:-80], 0.08, 10
    )
    assert np.allclose(completo.posicao.iloc[:-80], cortado.posicao)


def test_disjuntor_valida_entradas():
    precos = _precos(100)
    posicao = pd.Series(1.0, index=precos.index)
    with pytest.raises(ValueError, match="entre 0 e 1"):
        rg.aplicar_disjuntor_de_drawdown(precos, posicao, 0, 5)
    with pytest.raises(ValueError, match="pelo menos 1 dia"):
        rg.aplicar_disjuntor_de_drawdown(precos, posicao, 0.1, 0)
    with pytest.raises(ValueError, match="negativo"):
        rg.aplicar_disjuntor_de_drawdown(precos, posicao, 0.1, 5, -1)
    with pytest.raises(ValueError, match="mesmas datas"):
        rg.aplicar_disjuntor_de_drawdown(precos, posicao.iloc[1:], 0.1, 5)


def test_varredura_inclui_o_caso_sem_disjuntor():
    precos = _precos(600)
    posicao = pd.Series(1.0, index=precos.index)
    tabela = rg.varrer_disjuntor(precos, posicao, [0.05, 0.15], [10, 30])
    assert len(tabela) == 5
    assert tabela.index[0] == "Sem disjuntor"
    assert tabela.loc["Sem disjuntor", "Acionamentos"] == 0
    assert (tabela["Acionamentos"].iloc[1:] >= 0).all()
