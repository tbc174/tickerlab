"""CPCV (45 divisões, 9 caminhos, expurgo e embargo) e bootstrap em blocos."""

import numpy as np
import pandas as pd
import pytest

from trader.validacao import CPCV, bootstrap_diferenca_de_sharpe


@pytest.fixture
def datas():
    return pd.bdate_range("2000-01-03", "2023-09-08")


def test_numeros_do_criterio(datas):
    cpcv = CPCV()
    assert cpcv.n_divisoes == 45 and cpcv.n_caminhos == 9
    assert len(cpcv.divisoes(datas)) == 45


def test_grupos_cobrem_todas_as_datas_em_ordem_sem_sobrepor(datas):
    grupos = CPCV().grupos(datas)
    assert len(grupos) == 10
    juntos = grupos[0].append(grupos[1:])
    assert juntos.equals(datas)
    tamanhos = [len(g) for g in grupos]
    assert max(tamanhos) - min(tamanhos) <= 1


def test_treino_e_teste_nunca_se_tocam_e_respeitam_expurgo_e_embargo(datas):
    cpcv = CPCV()
    grupos = cpcv.grupos(datas)
    pos = {d: i for i, d in enumerate(datas)}
    for d in cpcv.divisoes(datas):
        assert len(d.treino.intersection(d.teste)) == 0
        posicoes_de_treino = np.array([pos[x] for x in d.treino])
        for g in d.grupos_de_teste:
            inicio, fim = pos[grupos[g][0]], pos[grupos[g][-1]]
            # nenhum dia de treino nos 21 pregões antes nem nos 21 depois do bloco de teste
            perto = (posicoes_de_treino >= inicio - 21) & (
                posicoes_de_treino <= fim + 21
            )
            assert not perto.any()


def test_treino_fica_com_quase_todo_o_resto(datas):
    for d in CPCV().divisoes(datas):
        maximo_retirado = 2 * (21 + 21)
        assert len(d.treino) >= len(datas) - len(d.teste) - maximo_retirado
        assert len(d.teste) == pytest.approx(len(datas) * 0.2, abs=2)


def test_sem_expurgo_nem_embargo_treino_e_o_complemento(datas):
    for d in CPCV(expurgo=0, embargo=0).divisoes(datas):
        assert d.treino.append(d.teste).sort_values().equals(datas)


def test_cada_grupo_e_teste_em_9_divisoes_e_cada_par_usado_uma_vez():
    cpcv = CPCV()
    caminhos = cpcv.caminhos()
    assert len(caminhos) == 9
    usados = [(g, n) for mapa in caminhos for g, n in mapa.items()]
    assert len(usados) == len(set(usados)) == 10 * 9  # cada (grupo, divisão) uma vez
    combinacoes = dict(enumerate(cpcv._combinacoes))
    for g, n in usados:
        assert g in combinacoes[n]  # o grupo é mesmo teste naquela divisão


def test_montar_caminhos_cobre_todas_as_datas_uma_vez(datas):
    cpcv = CPCV()
    retornos = {
        d.numero: pd.Series(float(d.numero), index=d.teste)
        for d in cpcv.divisoes(datas)
    }
    caminhos = cpcv.montar_caminhos(datas, retornos)
    assert len(caminhos) == 9
    for c in caminhos:
        assert c.index.equals(datas) and c.notna().all()
    # caminhos diferentes usam divisões diferentes no mesmo grupo
    assert caminhos[0].iloc[0] != caminhos[1].iloc[0]


def test_montar_caminhos_reclama_de_divisao_faltando(datas):
    with pytest.raises(ValueError, match="Faltam"):
        CPCV().montar_caminhos(datas, {0: pd.Series(dtype=float)})


def test_parametros_invalidos(datas):
    with pytest.raises(ValueError):
        CPCV(n_grupos=3, k_teste=3)
    with pytest.raises(ValueError):
        CPCV(expurgo=-1)
    with pytest.raises(ValueError, match="Poucas datas"):
        CPCV().grupos(datas[:100])


# --- bootstrap -----------------------------------------------------------------------------


def _ruido(n, media, seed):
    rng = np.random.default_rng(seed)
    return pd.Series(
        rng.normal(media, 0.01, n), index=pd.bdate_range("2000-01-03", periods=n)
    )


def test_bootstrap_ve_vantagem_clara():
    bom = _ruido(5000, 0.0012, 1)  # Sharpe ~1,9
    ruim = _ruido(5000, 0.0, 2)
    r = bootstrap_diferenca_de_sharpe(bom, ruim, sorteios=800)
    assert r["diferenca"] > 1 and r["ic90_inferior"] > 0
    assert r["ic90_inferior"] < r["diferenca"] < r["ic90_superior"]


def test_bootstrap_nao_inventa_vantagem_entre_iguais():
    a = _ruido(5000, 0.0003, 3)
    r = bootstrap_diferenca_de_sharpe(a, a.copy(), sorteios=300)
    assert r["diferenca"] == pytest.approx(0)
    assert r["ic90_inferior"] == pytest.approx(0) and r[
        "ic90_superior"
    ] == pytest.approx(0)


def test_bootstrap_com_sinal_fraco_nao_aprova():
    a, b = _ruido(3000, 0.0002, 4), _ruido(3000, 0.0001, 5)
    r = bootstrap_diferenca_de_sharpe(a, b, sorteios=800)
    assert r["ic90_inferior"] < 0  # diferença pequena não passa no critério A5


def test_bootstrap_usa_so_datas_em_comum_e_e_reproduzivel():
    a, b = _ruido(3000, 0.0005, 6), _ruido(2000, 0.0, 7)
    r1 = bootstrap_diferenca_de_sharpe(a, b, sorteios=200, semente=42)
    r2 = bootstrap_diferenca_de_sharpe(a, b, sorteios=200, semente=42)
    assert r1 == r2 and r1["dias"] == 2000
    with pytest.raises(ValueError, match="Poucos dias"):
        bootstrap_diferenca_de_sharpe(a.iloc[:10], b.iloc[:10])
