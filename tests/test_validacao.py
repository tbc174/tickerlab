"""Testes de src/validacao.py."""

import numpy as np
import pandas as pd
import pytest

from src import indicadores as ind
from src import validacao as val
from src.estrategias import ESTRATEGIAS


def _dados(n=900, semente=7):
    rng = np.random.default_rng(semente)
    f = 100 * np.cumprod(1 + rng.normal(0.0004, 0.012, n))
    return pd.DataFrame(
        {"Open": f, "High": f * 1.005, "Low": f * 0.995, "Close": f, "Volume": 1_000},
        index=pd.bdate_range("2020-01-02", periods=n),
    )


def _retornos(n=400):
    """Dois candidatos: o 0 ganha no começo e perde no fim; o 1 é fraco e estável."""
    indice = pd.bdate_range("2021-01-04", periods=n)
    rng = np.random.default_rng(1)
    ruido = rng.normal(0, 0.005, n)
    sinal = np.where(np.arange(n) < n // 2, 0.003, -0.003)
    return pd.DataFrame({0: ruido + sinal, 1: ruido + 0.0003}, index=indice)


CANDIDATOS = [{"a": 1}, {"a": 2}]


# --- grade de candidatos ------------------------------------------------------------------


def test_valores_do_parametro_ficam_nos_limites_e_incluem_o_padrao():
    for estrategia in ESTRATEGIAS.values():
        for p in estrategia.parametros:
            valores = val.valores_do_parametro(p)
            if p.opcoes:
                assert valores == list(p.opcoes)
                continue
            assert p.padrao in valores
            assert min(valores) >= p.minimo and max(valores) <= p.maximo
            assert valores == sorted(set(valores))


def test_montar_candidatos_faz_todas_as_combinacoes():
    padrao = ESTRATEGIAS["Cruzamento de médias"].parametros_padrao()
    um = val.montar_candidatos("Cruzamento de médias", padrao, ["curta"])
    dois = val.montar_candidatos("Cruzamento de médias", padrao, ["curta", "longa"])
    n_curta = len(
        val.valores_do_parametro(ESTRATEGIAS["Cruzamento de médias"].parametros[0])
    )
    n_longa = len(
        val.valores_do_parametro(ESTRATEGIAS["Cruzamento de médias"].parametros[1])
    )
    assert len(um) == n_curta
    assert len(dois) == n_curta * n_longa
    assert all(c["tipo"] == padrao["tipo"] for c in dois)  # o que não é livre fica fixo


def test_parametro_desconhecido_e_recusado():
    with pytest.raises(ValueError, match="desconhecidos"):
        val.montar_candidatos("Cruzamento de médias", {}, ["inexistente"])


def test_combinacoes_invalidas_sao_puladas():
    dados = _dados()
    padrao = ESTRATEGIAS["Cruzamento de médias"].parametros_padrao()
    candidatos = val.montar_candidatos(
        "Cruzamento de médias", padrao, ["curta", "longa"]
    )
    retornos, validos = val.calcular_retornos_dos_candidatos(
        dados, "Cruzamento de médias", candidatos, 0.0005
    )
    assert retornos.shape[1] == len(validos) <= len(candidatos)
    assert all(c["curta"] < c["longa"] for c in validos)


def test_sem_nenhuma_combinacao_valida_da_erro():
    with pytest.raises(ValueError, match="Nenhuma combinação"):
        val.calcular_retornos_dos_candidatos(
            _dados(), "Cruzamento de médias", [{"curta": 100, "longa": 10}], 0.0
        )


# --- escolha e treino/teste ---------------------------------------------------------------


def test_escolher_o_melhor_pega_o_maior_sharpe():
    retornos = _retornos().iloc[:150]  # só a parte boa do candidato 0
    coluna, sharpe = val.escolher_o_melhor(retornos)
    assert coluna == 0
    assert sharpe > 0


def test_escolher_o_melhor_sem_sharpe_calculavel_devolve_none():
    constante = pd.DataFrame({0: np.zeros(50)})
    assert val.escolher_o_melhor(constante) is None


def test_data_de_corte_respeita_a_fracao():
    indice = pd.bdate_range("2021-01-04", periods=200)
    assert val.data_de_corte(indice, 0.7) == indice[140]


def test_data_de_corte_recusa_fracao_absurda_e_poucos_dados():
    indice = pd.bdate_range("2021-01-04", periods=200)
    with pytest.raises(ValueError):
        val.data_de_corte(indice, 0.95)
    with pytest.raises(ValueError, match="Poucos dados"):
        val.data_de_corte(indice[:40], 0.5)


def test_treino_e_teste_mostram_a_queda_do_que_foi_ajustado():
    retornos = _retornos()
    corte = retornos.index[len(retornos) // 2 + 20]
    resultado = val.avaliar_treino_e_teste(retornos, CANDIDATOS, corte)
    assert resultado.melhor_do_treino == {"a": 1}
    assert resultado.sharpe_no_treino > 0 > resultado.sharpe_no_teste


def test_a_escolha_do_treino_nao_depende_do_teste():
    retornos = _retornos()
    corte = retornos.index[250]
    antes = val.avaliar_treino_e_teste(retornos, CANDIDATOS, corte)
    alterado = retornos.copy()
    alterado.loc[alterado.index >= corte, 0] = 0.05  # o teste vira um sonho
    depois = val.avaliar_treino_e_teste(alterado, CANDIDATOS, corte)
    assert depois.melhor_do_treino == antes.melhor_do_treino
    assert depois.sharpe_no_treino == antes.sharpe_no_treino


def test_treino_e_teste_nao_se_misturam():
    retornos = _retornos()
    corte = retornos.index[250]
    resultado = val.avaliar_treino_e_teste(retornos, CANDIDATOS, corte)
    assert resultado.retorno_no_treino.index.max() < corte
    assert resultado.retorno_no_teste.index.min() == corte


def test_treino_curto_demais_da_erro():
    retornos = _retornos()
    with pytest.raises(ValueError, match="mais dias"):
        val.avaliar_treino_e_teste(retornos, CANDIDATOS, retornos.index[5])


# --- walk-forward -------------------------------------------------------------------------


def test_walk_forward_janelas_nao_se_sobrepoem_e_cobrem_o_teste():
    retornos = _retornos(400)
    r = val.executar_walk_forward(retornos, CANDIDATOS, 100, 50)
    assert len(r.janelas) == 6  # (400 - 100) // 50
    fins = r.janelas["Fim do teste"]
    comecos = r.janelas["Começo do teste"]
    assert (comecos.iloc[1:].to_numpy() > fins.iloc[:-1].to_numpy()).all()
    assert len(r.retorno_fora_da_amostra) == 6 * 50
    assert r.retorno_fora_da_amostra.index.is_unique
    assert r.retorno_fora_da_amostra.index.is_monotonic_increasing


def test_walk_forward_escolhe_so_com_o_treino_de_cada_janela():
    retornos = _retornos(400)
    antes = val.executar_walk_forward(retornos, CANDIDATOS, 100, 50)
    alterado = retornos.copy()
    ultimo_teste = alterado.index[-50:]
    alterado.loc[ultimo_teste, 1] = 0.08  # só o teste da última janela muda
    depois = val.executar_walk_forward(alterado, CANDIDATOS, 100, 50)
    assert list(depois.janelas["Parâmetros escolhidos"]) == list(
        antes.janelas["Parâmetros escolhidos"]
    )
    assert list(depois.janelas["Sharpe no treino"]) == list(
        antes.janelas["Sharpe no treino"]
    )


def test_walk_forward_percebe_a_virada_do_candidato():
    r = val.executar_walk_forward(_retornos(400), CANDIDATOS, 100, 50)
    escolhidos = [p["a"] for p in r.janelas["Parâmetros escolhidos"]]
    assert escolhidos[0] == 1  # no começo o candidato 0 é bom
    assert escolhidos[-1] == 2  # no fim ele deixou de ser
    assert not np.isnan(r.eficiencia) or r.sharpe_medio_no_treino <= 0


def test_walk_forward_sem_janela_completa_da_erro():
    with pytest.raises(ValueError, match="nenhuma janela"):
        val.executar_walk_forward(_retornos(100), CANDIDATOS, 80, 50)


def test_walk_forward_recusa_janelas_minusculas():
    with pytest.raises(ValueError, match="pelo menos"):
        val.executar_walk_forward(_retornos(), CANDIDATOS, 5, 5)


def test_eficiencia_e_nan_quando_o_treino_nao_foi_positivo():
    r = val.ResultadoWalkForward(pd.DataFrame(), pd.Series(dtype=float), 0.5, -0.2)
    assert np.isnan(r.eficiencia)


# --- mapa de parâmetros -------------------------------------------------------------------


def test_mapa_de_sharpe_tem_o_formato_da_grade():
    dados = _dados()
    padrao = ESTRATEGIAS["Cruzamento de médias"].parametros_padrao()
    candidatos = val.montar_candidatos(
        "Cruzamento de médias", padrao, ["curta", "longa"]
    )
    retornos, validos = val.calcular_retornos_dos_candidatos(
        dados, "Cruzamento de médias", candidatos, 0.0005
    )
    mapa = val.montar_mapa_de_sharpe(retornos, validos, "curta", "longa")
    assert set(mapa.columns) == {c["curta"] for c in validos}
    assert set(mapa.index) == {c["longa"] for c in validos}
    assert mapa.notna().sum().sum() == len(validos)


def test_mapa_com_um_parametro_tem_uma_linha():
    dados = _dados()
    padrao = ESTRATEGIAS["Filtro de tendência"].parametros_padrao()
    candidatos = val.montar_candidatos("Filtro de tendência", padrao, ["janela"])
    retornos, validos = val.calcular_retornos_dos_candidatos(
        dados, "Filtro de tendência", candidatos, 0.0005
    )
    mapa = val.montar_mapa_de_sharpe(retornos, validos, "janela")
    assert mapa.shape[0] == 1


# --- de ponta a ponta ---------------------------------------------------------------------


def test_de_ponta_a_ponta_com_uma_estrategia_real():
    dados = _dados(1000)
    padrao = ESTRATEGIAS["Filtro de tendência"].parametros_padrao()
    candidatos = val.montar_candidatos("Filtro de tendência", padrao, ["janela"])
    retornos, validos = val.calcular_retornos_dos_candidatos(
        dados, "Filtro de tendência", candidatos, 0.0005
    )
    corte = val.data_de_corte(retornos.index, 0.7)
    tt = val.avaliar_treino_e_teste(retornos, validos, corte)
    assert tt.melhor_do_treino in validos
    wf = val.executar_walk_forward(retornos, validos, 300, 100)
    assert len(wf.janelas) >= 5


# --- resumos que saíram da tela do backtest (13/10/2026) ----------------------------------------
def test_resumo_da_grade_igual_ao_que_a_tela_calculava():
    mapa = pd.DataFrame([[0.5, -0.2, np.nan], [1.1, 0.0, 0.3]])
    resumo = val.resumir_grade(mapa)
    valores = pd.Series(mapa.to_numpy(dtype=float).ravel()).dropna()
    assert resumo.mediana == pytest.approx(valores.median())
    assert resumo.melhor == pytest.approx(valores.max())
    assert resumo.fracao_positiva == pytest.approx((valores > 0).mean())


def test_grade_vazia_nao_tem_resumo():
    assert val.resumir_grade(pd.DataFrame([[np.nan, np.nan]])) is None


def test_melhor_candidato_e_o_de_maior_sharpe():
    retornos = _retornos()
    esperado = retornos.apply(lambda r: ind.calcular_indice_sharpe(r, 0.1)).idxmax()
    assert val.melhor_candidato(retornos, 0.1) == esperado
