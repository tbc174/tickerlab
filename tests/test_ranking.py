"""Testes de src/ranking.py."""

import numpy as np
import pandas as pd
import pytest

from src.estrategias import ESTRATEGIAS
from src.protecoes import Protecoes
from src.ranking import COLUNAS_DO_RANKING, montar_ranking


def _dados(n=900, semente=3):
    rng = np.random.default_rng(semente)
    f = 100 * np.cumprod(1 + rng.normal(0.0004, 0.012, n))
    return pd.DataFrame(
        {"Open": f, "High": f * 1.005, "Low": f * 0.995, "Close": f, "Volume": 1_000},
        index=pd.bdate_range("2021-01-04", periods=n),
    )


@pytest.fixture(scope="module")
def ranking():
    return montar_ranking(_dados(), 0.0005, sorteios=100)


def test_tem_uma_linha_por_estrategia_e_as_colunas_certas(ranking):
    tabela, resultados = ranking
    assert set(tabela.index) == set(ESTRATEGIAS) == set(resultados)
    assert list(tabela.columns) == COLUNAS_DO_RANKING


def test_ordenado_pelo_sharpe_do_maior_para_o_menor(ranking):
    sharpes = ranking[0]["Índice de Sharpe"].dropna()
    assert list(sharpes) == sorted(sharpes, reverse=True)


def test_comprar_e_segurar_nao_se_destaca_do_acaso(ranking):
    assert ranking[0].loc["Comprar e segurar", "p-valor (acaso)"] == 1.0


def test_numeros_batem_com_o_backtest_individual(ranking):
    tabela, resultados = ranking
    r = resultados["Filtro de tendência"]
    assert tabela.loc["Filtro de tendência", "Retorno total"] == pytest.approx(
        r.curva_de_capital.iloc[-1] - 1
    )
    assert tabela.loc["Filtro de tendência", "Operações"] == len(r.operacoes)


def test_probabilidades_ficam_entre_zero_e_um(ranking):
    for coluna in ("Chance de não ser sorte", "p-valor (acaso)"):
        valores = ranking[0][coluna].dropna()
        assert valores.between(0, 1).all()


def test_mais_tentativas_extras_reduzem_a_chance_de_nao_ser_sorte():
    dados = _dados()
    sem, _ = montar_ranking(dados, 0.0005, sorteios=100)
    com, _ = montar_ranking(dados, 0.0005, tentativas_extras=500, sorteios=100)
    atribuidas = sem["Chance de não ser sorte"].notna()
    assert (
        com.loc[atribuidas.index[atribuidas], "Chance de não ser sorte"]
        <= sem.loc[atribuidas.index[atribuidas], "Chance de não ser sorte"] + 1e-12
    ).all()


def test_com_protecoes_o_ranking_muda():
    dados = _dados()
    sem, _ = montar_ranking(dados, 0.0005, sorteios=100)
    com, _ = montar_ranking(
        dados, 0.0005, sorteios=100, protecoes=Protecoes(alvo_de_volatilidade=0.10)
    )
    antes = sem["Volatilidade anual"].sort_index()
    depois = com["Volatilidade anual"].sort_index()
    assert not antes.equals(depois)
    assert (depois.dropna() <= antes.dropna() + 1e-9).all()
