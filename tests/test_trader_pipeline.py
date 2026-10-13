"""Atributos sem olhar o futuro, rótulo, armazém de séries e o pipeline com um CPCV pequeno."""

import numpy as np
import pandas as pd
import pytest

from trader import armazem, atributos, pipeline
from trader.rodar_baselines import SerieDoAtivo
from trader.universo import UNIVERSO
from trader.validacao import CPCV


def _ativo(simbolo):
    return next(a for a in UNIVERSO if a.simbolo == simbolo)


def _retornos(datas, seed, sinal=0.0):
    rng = np.random.default_rng(seed)
    ruido = rng.normal(0, 0.01, len(datas))
    r = pd.Series(ruido, index=datas)
    if sinal:  # um pouco de persistência: o retorno de ontem ajuda a prever o de hoje
        r = r + sinal * r.shift(1).fillna(0)
    return r


def _macro(datas):
    rng = np.random.default_rng(99)
    passeio = lambda base: pd.Series(
        base * np.exp(np.cumsum(rng.normal(0, 0.01, len(datas)))), index=datas
    )
    return {
        "vix": passeio(20),
        "juro_10a": passeio(3),
        "dolar": passeio(90),
        "petroleo": passeio(60),
        "cobre": passeio(3),
    }


@pytest.fixture(scope="module")
def mundo():
    uteis = pd.bdate_range("2000-01-03", periods=1600)
    todos_os_dias = pd.date_range("2000-01-03", uteis[-1], freq="D")
    series = [
        SerieDoAtivo(_ativo("EURUSD"), _retornos(uteis, 1, 0.1)),
        SerieDoAtivo(_ativo("PETR4.SA"), _retornos(uteis, 2, 0.1)),
        SerieDoAtivo(_ativo("^GSPC"), _retornos(uteis, 3, 0.1)),
        SerieDoAtivo(_ativo("BTC-USD"), _retornos(todos_os_dias, 4, 0.1)),
    ]
    painel = atributos.montar_painel(
        series, None, _macro(uteis), pd.Timestamp("2001-01-02"), uteis[-1]
    )
    return series, painel


# --- atributos e rótulo --------------------------------------------------------------------


def test_rotulo_olha_os_proximos_5_pregoes():
    r = pd.Series([0.01, -0.02, 0.03, 0.0, 0.01, -0.05, 0.02, 0.01])
    y = atributos.rotulo(r, 5)
    soma = r.iloc[1:6].sum()  # -0,02 + 0,03 + 0 + 0,01 - 0,05 = -0,03
    assert y.iloc[0] == float(soma > 0) == 0.0
    assert y.iloc[2] == float(r.iloc[3:8].sum() > 0)
    assert y.iloc[-5:].isna().all() and y.iloc[:3].notna().all()


def test_atributos_do_ativo_nao_olham_o_futuro():
    datas = pd.bdate_range("2000-01-03", periods=900)
    r = _retornos(datas, 5)
    a = atributos.atributos_do_ativo(r, 252)
    alterado = r.copy()
    alterado.iloc[-100:] = 0.05
    b = atributos.atributos_do_ativo(alterado, 252)
    pd.testing.assert_frame_equal(a.iloc[:-100], b.iloc[:-100])


def test_macro_e_sempre_da_vespera():
    datas = pd.bdate_range("2000-01-03", periods=600)
    macro = _macro(datas)
    a = atributos.atributos_macro(macro, datas)
    alterado = {k: v.copy() for k, v in macro.items()}
    alterado["vix"].iloc[-1] = 500.0  # choque no último dia
    b = atributos.atributos_macro(alterado, datas)
    pd.testing.assert_frame_equal(a, b)  # o último dia só vê a véspera


def test_painel_tem_todas_as_colunas_e_sem_infinito(mundo):
    _, painel = mundo
    for coluna in (*atributos.ATRIBUTOS, "y", "simbolo", "Date", "retorno_futuro"):
        assert coluna in painel.columns
    assert not np.isinf(painel[list(atributos.ATRIBUTOS)].to_numpy(dtype=float)).any()
    assert painel["simbolo"].nunique() == 4
    assert (painel.loc[painel["simbolo"] == "PETR4.SA", "classe_acoes_b3"] == 1).all()


# --- armazém -------------------------------------------------------------------------------


def test_armazem_guarda_e_monta_candidatos(tmp_path):
    datas = pd.bdate_range("2010-01-04", periods=50)
    a, b = "a" * 64, "b" * 64
    armazem.salvar(
        a, pd.Series(0.01, index=datas), pd.Series(0.0, index=datas), tmp_path
    )
    armazem.salvar(
        b,
        pd.Series(0.02, index=datas[10:]),
        pd.Series(0.0, index=datas[10:]),
        tmp_path,
        apelido="baseline_B1",
    )
    cand = armazem.candidatos(datas, pasta=tmp_path)
    assert list(cand.columns) == [a, b]  # o apelido não conta duas vezes
    assert cand[b].iloc[:10].eq(0).all()
    assert armazem.carregar("baseline_B1", tmp_path)["x1"].iloc[0] == 0.02
    with pytest.raises(FileNotFoundError):
        armazem.carregar("nao_existe", tmp_path)


# --- pipeline ------------------------------------------------------------------------------


CPCV_PEQUENO = CPCV(n_grupos=4, k_teste=2, expurgo=5, embargo=5)


def test_pipeline_monta_os_caminhos_completos(mundo):
    series, painel = mundo
    config = pipeline.Configuracao("teste", "logistica")
    res = pipeline.rodar(config, painel, series, None, cpcv=CPCV_PEQUENO)
    uteis = pipeline.dias_uteis(painel)
    assert len(res.caminhos) == CPCV_PEQUENO.n_caminhos == 3
    for c in res.caminhos + res.caminhos_x2:
        assert c.index.equals(uteis)
    assert set(res.por_ativo[0]) == {"EURUSD", "PETR4.SA", "^GSPC", "BTC-USD"}
    btc = res.por_ativo[0]["BTC-USD"]
    assert (btc.index.weekday >= 5).any()  # cripto no fim de semana entra no caminho
    assert res.posicoes[0].abs().max().max() <= 2.0 + 1e-9
    assert res.custo_por_lado["PETR4.SA"] == pytest.approx(0.0005)


def test_pipeline_custos_x2_nunca_melhoram(mundo):
    series, painel = mundo
    res = pipeline.rodar(
        pipeline.Configuracao("teste", "logistica"),
        painel,
        series,
        None,
        cpcv=CPCV_PEQUENO,
    )
    for c1, c2 in zip(res.caminhos, res.caminhos_x2, strict=True):
        assert c2.sum() <= c1.sum() + 1e-12


def test_variante_futuro_infla_e_embaralhado_some(mundo):
    series, painel = mundo
    config = pipeline.Configuracao(
        "teste", "lightgbm", ajustes={"n_estimators": 50, "min_child_samples": 50}
    )
    normal = pipeline.rodar(
        config, painel, series, None, "normal", CPCV_PEQUENO
    ).caminhos[1]
    futuro = pipeline.rodar(
        config, painel, series, None, "futuro", CPCV_PEQUENO
    ).caminhos[1]
    sharpe = lambda r: r.mean() / r.std() * np.sqrt(252)
    assert sharpe(futuro) > sharpe(normal) + 0.5


def test_variante_proporcao_preve_so_a_frequencia_do_treino():
    rng = np.random.default_rng(5)
    x = rng.normal(size=(100, 3))
    y = (rng.random(100) < 0.6).astype(float)
    treino, teste = np.arange(80), np.arange(80, 100)
    completos = np.ones(100, dtype=bool)
    completos[95] = False  # sem atributos: fica neutro, como no normal
    p, escala = pipeline._treinar_e_prever(
        "logistica", {}, 0, x, y, treino, teste, completos, None, so_proporcao=True
    )
    proporcao = y[:80].mean()
    assert np.allclose(np.delete(p, 15), proporcao) and p[15] == 0.5
    sinal = (2 * np.delete(p, 15) - 1) / escala
    assert np.allclose(
        sinal, 0.5 * np.sign(2 * proporcao - 1)
    )  # mesma média absoluta do normal


def test_variante_proporcao_roda_no_pipeline(mundo):
    series, painel = mundo
    res = pipeline.rodar(
        pipeline.Configuracao("t", "logistica"),
        painel,
        series,
        None,
        "proporcao",
        CPCV_PEQUENO,
    )
    assert len(res.caminhos) == 3


def test_floresta_preve_igual_nas_duas_execucoes():
    rng = np.random.default_rng(4)
    x = rng.normal(size=(6000, 5))
    y = (x[:, 0] + rng.normal(size=6000) > 0).astype(float)
    treino, teste = np.arange(4000), np.arange(4000, 6000)
    completos = np.ones(6000, dtype=bool)
    ajustes = {"n_estimators": 60, "min_samples_leaf": 50}
    a = pipeline._treinar_e_prever(
        "floresta", ajustes, 0, x, y, treino, teste, completos, None
    )[0]
    b = pipeline._treinar_e_prever(
        "floresta", ajustes, 0, x, y, treino, teste, completos, None
    )[0]
    assert np.array_equal(a, b)  # exatamente igual, não só parecido


def test_meta_rotulo_diz_se_a_tendencia_acertou():
    tendencia = np.array([0.5, -0.3, 0.0, np.nan, 0.2])
    y = np.array([1.0, 1.0, 1.0, 0.0, np.nan])  # 1 = os próximos pregões subiram
    direcao, rotulo = pipeline.direcao_e_rotulo_meta(tendencia, y)
    assert direcao.tolist() == [1, -1, 0, 0, 1]
    assert (
        rotulo[0] == 1 and rotulo[1] == 0
    )  # comprado e subiu: acertou; vendido e subiu: errou
    assert np.isnan(rotulo[2:]).all()  # sem direção ou sem rótulo: fora do treino


def test_meta_so_age_quando_o_modelo_acredita_no_acerto():
    p = np.array([0.3, 0.5, 0.7, 0.9])
    assert pipeline._forca(p, meta=True).tolist() == pytest.approx([0, 0, 0.4, 0.8])
    assert pipeline._forca(p).tolist() == pytest.approx([0.4, 0, 0.4, 0.8])


def test_meta_e_familia_h3_e_muda_a_especificacao():
    from trader.registro import hash_da_especificacao

    meta = pipeline.Configuracao("m", "lightgbm", meta=True)
    comum = pipeline.Configuracao("m", "lightgbm")
    assert meta.familia == "H3" and comum.familia == "H2"
    assert "meta" in meta.especificacao() and "meta" not in comum.especificacao()
    assert hash_da_especificacao(meta.especificacao()) != hash_da_especificacao(
        comum.especificacao()
    )


def test_pipeline_meta_roda_e_segue_a_direcao_da_tendencia(mundo):
    series, painel = mundo
    res = pipeline.rodar(
        pipeline.Configuracao("m", "logistica", meta=True),
        painel,
        series,
        None,
        cpcv=CPCV_PEQUENO,
    )
    assert len(res.caminhos) == 3 and all(c.notna().all() for c in res.caminhos)


def test_sinal_meta_nunca_contraria_a_direcao():
    # (a posição final pode atrasar alguns dias por causa do buffer; o sinal não)
    p = np.array([0.9, 0.9, 0.4, 0.8, 0.6])
    direcao = np.array([1.0, -1.0, 1.0, 0.0, -1.0])
    sinal = pipeline.sinal_da_previsao(p, 0.5, direcao)
    assert sinal.tolist() == pytest.approx([1.0, -1.0, 0.0, 0.0, -0.4])
    assert pipeline.sinal_da_previsao(p, 0.8).tolist() == pytest.approx(
        [1.0, 1.0, -0.25, 0.75, 0.25]
    )


def test_variante_desconhecida_e_recusada(mundo):
    series, painel = mundo
    with pytest.raises(ValueError, match="Variante"):
        pipeline.rodar(
            pipeline.Configuracao("t", "logistica"),
            painel,
            series,
            None,
            "x",
            CPCV_PEQUENO,
        )


def test_especificacao_inclui_parametros_e_familia():
    c = pipeline.Configuracao("lgbm", "lightgbm", ajustes={"num_leaves": 7})
    spec = c.especificacao()
    assert c.familia == "H2" and spec["parametros"]["num_leaves"] == 7
    assert spec["parametros"]["min_child_samples"] == 500
    assert pipeline.Configuracao("l", "logistica").familia == "H1"


def test_especificacao_por_classe_tem_os_grupos_e_outro_hash():
    from trader.registro import hash_da_especificacao

    um = pipeline.Configuracao("x", "lightgbm")
    por = pipeline.Configuracao("x", "lightgbm", por_classe=True)
    assert (
        "por_classe" not in um.especificacao()
    )  # configurações antigas: mesmo formato
    assert por.especificacao()["grupos"]["metais"] == "commodities"
    assert hash_da_especificacao(um.especificacao()) != hash_da_especificacao(
        por.especificacao()
    )
    # o universo entra pelo rodar_modelo: o mesmo modelo noutro universo é outra tentativa
    assert hash_da_especificacao(um.especificacao({"universo": ["A"]})) != (
        hash_da_especificacao(um.especificacao({"universo": ["A", "B"]}))
    )


def test_grupos_cobrem_todas_as_classes_operaveis():
    from trader.universo import UNIVERSO

    classes = {a.classe for a in UNIVERSO if a.papel == "operar"}
    assert classes <= set(pipeline.GRUPO_DA_CLASSE)


def test_por_classe_treina_um_modelo_por_grupo_com_a_propria_escala():
    rng = np.random.default_rng(2)
    n = 400
    x = rng.normal(size=(n, 2))
    grupos = np.array(["a"] * 200 + ["b"] * 200)
    # no grupo a o atributo 0 prevê alta; no grupo b prevê QUEDA (relações opostas)
    y = np.where(grupos == "a", x[:, 0] > 0, x[:, 0] < 0).astype(float)
    treino = np.r_[0:150, 200:350]
    teste = np.r_[150:200, 350:400]
    completos = np.ones(n, dtype=bool)
    p, escala = pipeline._treinar_e_prever(
        "logistica", {"C": 10.0}, 0, x, y, treino, teste, completos, None, grupos=grupos
    )
    acerto = ((p > 0.5) == (y[teste] == 1)).mean()
    assert acerto > 0.9  # um modelo só, misturando os dois, ficaria perto de 50%
    assert escala.shape == teste.shape
    p1, _ = pipeline._treinar_e_prever(
        "logistica", {"C": 10.0}, 0, x, y, treino, teste, completos, None
    )
    assert ((p1 > 0.5) == (y[teste] == 1)).mean() < 0.7


def test_pipeline_por_classe_roda(mundo):
    series, painel = mundo
    res = pipeline.rodar(
        pipeline.Configuracao("t", "logistica", por_classe=True),
        painel,
        series,
        None,
        cpcv=CPCV_PEQUENO,
    )
    assert len(res.caminhos) == 3 and all(c.notna().all() for c in res.caminhos)


def test_dados_do_acaso_alinham_qualquer_caminho(mundo):
    from trader import criterio

    series, painel = mundo
    res = pipeline.rodar(
        pipeline.Configuracao("teste", "logistica"),
        painel,
        series,
        None,
        cpcv=CPCV_PEQUENO,
    )
    for caminho in range(len(res.posicoes)):
        posicoes, retornos, custo = pipeline.dados_do_acaso(res, caminho)
        assert posicoes.index.equals(retornos.index)
        assert list(posicoes.columns) == list(retornos.columns) == list(custo.index)
        criterio.p_valor_do_acaso_da_carteira(posicoes, retornos, custo, sorteios=100)
