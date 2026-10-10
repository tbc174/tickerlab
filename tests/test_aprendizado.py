"""Testes de src/aprendizado.py."""

import numpy as np
import pandas as pd
import pytest

from src import aprendizado as ml


def _dados(n=1500, semente=1, deriva=0.0003, vol=0.012):
    rng = np.random.default_rng(semente)
    fechamento = 100 * np.cumprod(1 + rng.normal(deriva, vol, n))
    return pd.DataFrame(
        {
            "Open": fechamento,
            "High": fechamento * (1 + np.abs(rng.normal(0, 0.005, n))),
            "Low": fechamento * (1 - np.abs(rng.normal(0, 0.005, n))),
            "Close": fechamento,
            "Volume": rng.integers(1000, 5000, n).astype(float),
        },
        index=pd.bdate_range("2018-01-02", periods=n),
    )


def _dados_com_volatilidade_persistente(n=2500, semente=2):
    rng = np.random.default_rng(semente)
    log_vol = np.zeros(n)
    for t in range(1, n):
        log_vol[t] = 0.98 * log_vol[t - 1] + rng.normal(0, 0.12)
    retorno = rng.normal(0, 1, n) * 0.01 * np.exp(log_vol)
    fechamento = 100 * np.cumprod(1 + retorno)
    return pd.DataFrame(
        {"Close": fechamento}, index=pd.bdate_range("2014-01-01", periods=n)
    )


# --- variáveis e rótulos ------------------------------------------------------------------


def test_variaveis_nao_olham_o_futuro():
    dados = _dados()
    completo = ml.montar_variaveis(dados)
    cortado = ml.montar_variaveis(dados.iloc[:-100])
    assert np.allclose(
        completo.iloc[:-100].to_numpy(), cortado.to_numpy(), equal_nan=True
    )
    assert list(completo.columns) == list(ml.NOMES_DAS_VARIAVEIS)


def test_sem_volume_a_variavel_fica_neutra():
    dados = _dados().drop(columns=["Volume", "High", "Low"])
    variaveis = ml.montar_variaveis(dados)
    assert (variaveis["Volume relativo"] == 0).all()


def test_rotulo_do_proximo_dia():
    dados = _dados(300)
    conjunto = ml.rotular_proximo_dia(dados)
    retorno = dados["Close"].pct_change()
    dia = conjunto.y.index[10]
    posicao = dados.index.get_loc(dia)
    assert conjunto.y.iloc[10] == float(retorno.iloc[posicao + 1] > 0)
    assert conjunto.fim[10] == conjunto.posicao[10] + 1
    assert conjunto.y.index[-1] == dados.index[-2]  # o último dia não tem rótulo


def _precos(valores):
    return pd.Series(valores, index=pd.bdate_range("2026-01-05", periods=len(valores)))


def test_barreira_tripla_alvo_stop_e_prazo():
    # dia 0: sobe 5% no dia 2 (alvo de 3%); dia 1: cai 5% no dia 2 (stop de 3%)
    preco = _precos([100, 100, 105, 99, 99, 99, 99, 99.5, 99.5])
    rotulo, fim = ml.calcular_barreira_tripla(preco, 0.03, 0.03, prazo=3)
    assert rotulo[0] == 1 and fim[0] == 2
    assert rotulo[1] == 1 and fim[1] == 2  # 100 -> 105: bateu o alvo primeiro
    assert rotulo[2] == 0 and fim[2] == 3  # 105 -> 99 (-5,7%): stop
    assert rotulo[3] == 0 and fim[3] == 6  # nada em 3 dias: o prazo acaba
    # janela incompleta no fim dos dados: sem rótulo
    assert np.isnan(rotulo[6]) and np.isnan(rotulo[7])


def test_barreira_tripla_o_que_vem_primeiro_vale():
    preco = _precos([100, 96, 110, 100, 100])  # cai 4% e depois sobe 10%
    rotulo, _ = ml.calcular_barreira_tripla(preco, 0.05, 0.03, prazo=3)
    assert rotulo[0] == 0  # o stop de 3% veio antes do alvo de 5%


def test_barreira_valida_entradas():
    preco = _precos([100.0] * 10)
    with pytest.raises(ValueError, match="entre 0 e 1"):
        ml.calcular_barreira_tripla(preco, 0, 0.03, 3)
    with pytest.raises(ValueError, match="pelo menos 1"):
        ml.calcular_barreira_tripla(preco, 0.03, 0.03, 0)


def test_rotulos_da_barreira_ficam_resolvidos_depois_do_dia():
    conjunto = ml.rotular_barreira_tripla(_dados(600), 0.02, 0.02, 10)
    assert (conjunto.fim > conjunto.posicao).all()
    assert (conjunto.fim - conjunto.posicao <= 10).all()


def test_poucos_dados_para_treinar():
    with pytest.raises(ValueError, match="Poucos dias"):
        ml.rotular_proximo_dia(_dados(100))


# --- modelo -------------------------------------------------------------------------------


def test_regressao_logistica_aprende_um_sinal_claro():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(2000, 3))
    y = (X[:, 0] + 0.3 * rng.normal(size=2000) > 0).astype(float)
    modelo = ml.RegressaoLogistica().ajustar(X[:1500], y[:1500])
    p = modelo.prever_probabilidade(X[1500:])
    assert ml.calcular_auc(y[1500:], p) > 0.9
    assert modelo.pesos[1] > 5 * abs(modelo.pesos[2])


def test_regressao_logistica_em_ruido_fica_perto_do_acaso():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(3000, 4))
    y = rng.integers(0, 2, 3000).astype(float)
    modelo = ml.RegressaoLogistica().ajustar(X[:2000], y[:2000])
    auc = ml.calcular_auc(y[2000:], modelo.prever_probabilidade(X[2000:]))
    assert abs(auc - 0.5) < 0.05


def test_regressao_logistica_valida_entradas():
    with pytest.raises(ValueError, match="maior que zero"):
        ml.RegressaoLogistica(l2=0)
    with pytest.raises(ValueError, match="Ajuste"):
        ml.RegressaoLogistica().prever_probabilidade(np.zeros((2, 2)))
    with pytest.raises(ValueError, match="pelo menos 2"):
        ml.RegressaoLogistica().ajustar(np.zeros((1, 2)), np.zeros(1))


def test_auc_com_valores_conhecidos():
    y = np.array([0, 0, 1, 1])
    assert ml.calcular_auc(y, np.array([0.1, 0.2, 0.8, 0.9])) == 1.0
    assert ml.calcular_auc(y, np.array([0.9, 0.8, 0.2, 0.1])) == 0.0
    assert ml.calcular_auc(y, np.array([0.5, 0.5, 0.5, 0.5])) == 0.5
    assert np.isnan(ml.calcular_auc(np.ones(4), np.arange(4.0)))


# --- treino com janela que expande --------------------------------------------------------


def test_previsoes_so_comecam_depois_do_treino_minimo():
    conjunto = ml.rotular_proximo_dia(_dados())
    previsoes = ml.prever_fora_da_amostra(conjunto, minimo_de_treino=300, passo=50)
    assert previsoes["p"].iloc[:300].isna().all()
    assert previsoes["p"].iloc[300:].notna().all()
    assert previsoes["p"].between(0, 1).all() or previsoes["p"].isna().any()


def test_previsoes_nao_olham_o_futuro():
    dados = _dados()
    completo = ml.prever_fora_da_amostra(
        ml.rotular_proximo_dia(dados), minimo_de_treino=300, passo=50
    )
    cortado = ml.prever_fora_da_amostra(
        ml.rotular_proximo_dia(dados.iloc[:-120]), minimo_de_treino=300, passo=50
    )
    comum = cortado.index
    assert np.allclose(
        completo.loc[comum[:-1]].to_numpy(),
        cortado.loc[comum[:-1]].to_numpy(),
        equal_nan=True,
    )


def test_treino_expurga_rotulos_ainda_nao_resolvidos():
    # com prazo longo, os exemplos recentes não podem entrar no treino
    dados = _dados()
    conjunto = ml.rotular_barreira_tripla(dados, 0.02, 0.02, 20)
    a = ml.prever_fora_da_amostra(conjunto, minimo_de_treino=300, passo=50)
    # embaralhar os rótulos do trecho ainda não resolvido não pode mudar a previsão
    n_bloco = 300
    inicio_do_bloco = conjunto.posicao[n_bloco]
    y_alterado = conjunto.y.copy()
    ainda_abertos = (conjunto.fim >= inicio_do_bloco) & (
        conjunto.posicao < inicio_do_bloco
    )
    y_alterado[ainda_abertos] = 1.0 - y_alterado[ainda_abertos]
    b = ml.prever_fora_da_amostra(
        ml.ConjuntoDeDados(conjunto.X, y_alterado, conjunto.posicao, conjunto.fim),
        minimo_de_treino=300,
        passo=50,
    )
    assert np.allclose(a["p"].iloc[300:350].to_numpy(), b["p"].iloc[300:350].to_numpy())


def test_mascara_preve_so_nos_exemplos_marcados():
    conjunto = ml.rotular_proximo_dia(_dados())
    mascara = np.zeros(len(conjunto.y), dtype=bool)
    mascara[::2] = True
    previsoes = ml.prever_fora_da_amostra(
        conjunto, minimo_de_treino=300, passo=50, mascara=mascara
    )
    assert previsoes["p"].iloc[1::2].isna().all()
    assert previsoes["p"].iloc[300::2].notna().all()


def test_previsoes_validam_entradas():
    conjunto = ml.rotular_proximo_dia(_dados(400))
    with pytest.raises(ValueError, match="curto demais"):
        ml.prever_fora_da_amostra(conjunto, minimo_de_treino=1000)
    with pytest.raises(ValueError, match="mínimo"):
        ml.prever_fora_da_amostra(conjunto, minimo_de_treino=10)


def test_avaliacao_contra_a_previsao_ingenua():
    y = pd.Series(np.tile([0.0, 1.0], 100))
    perfeita = pd.DataFrame({"p": y * 0.9 + 0.05, "p_ingenua": 0.5 + 0.0 * y})
    r = ml.avaliar_previsoes(y, perfeita)
    assert r["Acurácia do modelo"] == 1.0 and r["AUC"] == 1.0
    assert r["Brier do modelo"] < r["Brier ingênuo"]
    assert r["Diferença em erros-padrão"] > 5
    with pytest.raises(ValueError, match="poucas"):
        ml.avaliar_previsoes(y, perfeita.assign(p=np.nan))


def test_prever_o_sinal_do_dia_em_ruido_nao_vence_o_ingenuo_com_folga():
    conjunto = ml.rotular_proximo_dia(_dados(2500, semente=7, deriva=0.0))
    previsoes = ml.prever_fora_da_amostra(conjunto)
    r = ml.avaliar_previsoes(conjunto.y, previsoes)
    assert abs(r["AUC"] - 0.5) < 0.06
    assert r["Diferença em erros-padrão"] < 3


def test_posicao_a_partir_das_probabilidades():
    indice = pd.bdate_range("2026-01-05", periods=4)
    p = pd.Series([0.6, 0.4, np.nan], index=indice[:3])
    posicao = ml.posicao_a_partir_das_probabilidades(p, indice, 0.5)
    assert list(posicao) == [1.0, 0.0, 0.0, 0.0]
    with pytest.raises(ValueError, match="limiar"):
        ml.posicao_a_partir_das_probabilidades(p, indice, 1.0)


# --- validação cruzada com expurgo --------------------------------------------------------


def test_expurgo_tira_do_treino_o_que_encosta_no_teste():
    conjunto = ml.rotular_barreira_tripla(_dados(), 0.02, 0.02, 10)
    for treino, teste in ml.dividir_com_expurgo(conjunto, k=5, embargo=5):
        inicio, fim = conjunto.posicao[teste[0]], conjunto.posicao[teste[-1]]
        p, f = conjunto.posicao[treino], conjunto.fim[treino]
        assert not ((p <= fim) & (f >= inicio)).any()  # nenhum intervalo encosta
        assert not ((p > fim) & (p <= fim + 5)).any()  # embargo
        assert len(np.intersect1d(treino, teste)) == 0


def test_sem_expurgo_o_treino_tem_exemplos_que_vazam():
    conjunto = ml.rotular_barreira_tripla(_dados(), 0.02, 0.02, 10)
    vazou = False
    for treino, teste in ml.dividir_com_expurgo(conjunto, 5, 5, expurgar=False):
        inicio = conjunto.posicao[teste[0]]
        vazou |= bool(
            (
                (conjunto.posicao[treino] < inicio) & (conjunto.fim[treino] >= inicio)
            ).any()
        )
    assert vazou


def test_validacao_cruzada_devolve_metricas_e_valida_entradas():
    conjunto = ml.rotular_proximo_dia(_dados())
    r = ml.validar_com_expurgo(conjunto)
    assert 0.3 < r["Acurácia do modelo"] < 0.7 and 0.4 < r["AUC"] < 0.6
    with pytest.raises(ValueError, match="blocos"):
        list(ml.dividir_com_expurgo(conjunto, k=1))
    with pytest.raises(ValueError, match="embargo"):
        list(ml.dividir_com_expurgo(conjunto, embargo=-1))


# --- volatilidade -------------------------------------------------------------------------


def test_modelo_de_volatilidade_vence_o_ingenuo_quando_a_volatilidade_persiste():
    dados = _dados_com_volatilidade_persistente()
    r = ml.prever_volatilidade(dados)
    assert r.metricas["Correlação do modelo"] > 0.5
    assert r.metricas["Erro do modelo (log)"] <= r.metricas["Erro ingênuo (log)"] * 1.05
    assert len(r.prevista) == len(r.realizada) == len(r.ingenua)
    assert (r.prevista > 0).all()


def test_previsao_de_volatilidade_nao_olha_o_futuro():
    dados = _dados_com_volatilidade_persistente()
    completo = ml.prever_volatilidade(dados).prevista
    cortado = ml.prever_volatilidade(dados.iloc[:-200]).prevista
    comum = cortado.index[:-25]
    assert np.allclose(completo.loc[comum], cortado.loc[comum])


def test_volatilidade_valida_entradas():
    with pytest.raises(ValueError, match="horizonte"):
        ml.prever_volatilidade(_dados(), horizonte=1)
    with pytest.raises(ValueError, match="curto demais"):
        ml.prever_volatilidade(_dados(300))


def test_posicao_pelo_alvo_de_volatilidade():
    indice = pd.bdate_range("2026-01-05", periods=3)
    vol = pd.Series([0.10, 0.40], index=indice[:2])
    posicao = ml.posicao_pelo_alvo_de_volatilidade(vol, indice, 0.20)
    assert list(posicao) == [1.0, 0.5, 0.0]  # sem alavancagem; sem dado, caixa
    with pytest.raises(ValueError, match="maior que zero"):
        ml.posicao_pelo_alvo_de_volatilidade(vol, indice, 0)


def test_volatilidades_estao_todas_na_mesma_escala_anual():
    r = ml.prever_volatilidade(_dados_com_volatilidade_persistente())
    razao = (r.prevista / r.ingenua).median()
    assert 0.7 < razao < 1.4
    assert 0.05 < r.realizada.median() < 1.0
