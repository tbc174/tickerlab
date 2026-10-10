"""Testes de src/carteiras.py."""

import numpy as np
import pandas as pd
import pytest

from src.backtest import executar_backtest
from src.carteiras import (
    ESTRATEGIAS_DE_CARTEIRA,
    dias_de_decisao,
    executar_backtest_de_carteira,
    gerar_pesos,
    simular_carteira,
)


def _precos(n=900, ativos=("A", "B", "C", "D"), semente=1):
    rng = np.random.default_rng(semente)
    deriva = np.linspace(0.0008, -0.0002, len(ativos))
    dados = {
        a: 100 * np.cumprod(1 + rng.normal(d, 0.01 + 0.004 * i, n))
        for i, (a, d) in enumerate(zip(ativos, deriva))
    }
    return pd.DataFrame(dados, index=pd.bdate_range("2021-01-04", periods=n))


# --- dias de decisão ----------------------------------------------------------------------


def test_dias_de_decisao_sao_o_ultimo_pregao_de_cada_mes():
    indice = pd.bdate_range("2026-01-01", "2026-03-31")
    decisao = dias_de_decisao(indice)
    assert list(decisao.strftime("%Y-%m-%d")) == [
        "2026-01-30",
        "2026-02-27",
        "2026-03-31",
    ]


# --- motor: conferência contra o motor de um ativo ----------------------------------------


def test_um_ativo_com_pesos_zero_ou_um_bate_com_o_motor_simples():
    fechamento = _precos(ativos=("A",))["A"]
    rng = np.random.default_rng(3)
    desejada = pd.Series(
        rng.integers(0, 2, len(fechamento)).astype(float), index=fechamento.index
    )
    esperado = executar_backtest(fechamento, desejada, 0.001)
    r = executar_backtest_de_carteira(
        fechamento.to_frame(), desejada.to_frame("A"), 0.001
    )
    assert np.allclose(r.retorno, esperado.retorno)
    assert r.giro == pytest.approx(esperado.giro)


def test_pesos_derivam_entre_rebalanceamentos():
    indice = pd.bdate_range("2026-01-05", periods=4)  # tudo dentro do mesmo mês
    precos = pd.DataFrame(
        {"A": [100, 200, 200, 200], "B": [100, 100, 150, 150]},
        index=indice,
        dtype=float,
    )
    pesos = pd.DataFrame(0.5, index=indice, columns=["A", "B"])
    r = executar_backtest_de_carteira(precos, pesos, custo_por_operacao=0.0)
    assert r.retorno.iloc[1] == pytest.approx(0.5)  # 50% em A que dobrou
    # depois do dia 1: A pesa 1/1,5 e B pesa 0,5/1,5
    assert r.pesos.iloc[2]["A"] == pytest.approx(2 / 3)
    assert r.retorno.iloc[2] == pytest.approx((1 / 3) * 0.5)


def test_custo_incide_sobre_o_valor_negociado():
    indice = pd.bdate_range("2026-01-05", periods=3)
    precos = pd.DataFrame({"A": [100.0] * 3, "B": [100.0] * 3}, index=indice)
    pesos = pd.DataFrame(0.5, index=indice, columns=["A", "B"])
    r = executar_backtest_de_carteira(precos, pesos, custo_por_operacao=0.01)
    assert r.retorno.iloc[1] == pytest.approx(-0.01)  # comprou 100% do capital
    assert r.retorno.iloc[2] == 0
    assert r.giro == pytest.approx(1.0)


def test_o_dinheiro_parado_rende_o_cdi():
    indice = pd.bdate_range("2026-01-05", periods=5)
    precos = pd.DataFrame({"A": [100.0] * 5, "B": [100.0] * 5}, index=indice)
    pesos = pd.DataFrame(0.0, index=indice, columns=["A", "B"])
    cdi = pd.Series(0.0005, index=indice)
    r = executar_backtest_de_carteira(precos, pesos, 0.0, cdi)
    assert list(r.retorno.iloc[1:]) == pytest.approx([0.0005] * 4)
    assert r.retorno.iloc[0] == 0
    assert (r.exposicao == 0).all()


def test_motor_recusa_entradas_ruins():
    precos = _precos(50)
    bom = pd.DataFrame(0.25, index=precos.index, columns=precos.columns)
    with pytest.raises(ValueError, match="negativo"):
        executar_backtest_de_carteira(precos, bom, -0.1)
    with pytest.raises(ValueError, match="mesmas datas"):
        executar_backtest_de_carteira(precos, bom.iloc[1:])
    with pytest.raises(ValueError, match="somar no máximo 1"):
        executar_backtest_de_carteira(precos, bom * 2)
    ruim = bom.copy()
    ruim.iloc[3, 0] = np.nan
    with pytest.raises(ValueError, match="vazios"):
        executar_backtest_de_carteira(precos, ruim)


# --- estratégias --------------------------------------------------------------------------


@pytest.mark.parametrize("nome", list(ESTRATEGIAS_DE_CARTEIRA))
def test_pesos_ficam_entre_zero_e_um_e_somam_no_maximo_um(nome):
    pesos = gerar_pesos(nome, _precos())
    assert pesos.shape == _precos().shape
    assert (pesos >= 0).all().all()
    assert (pesos.sum(axis=1) <= 1 + 1e-9).all()
    assert not pesos.isna().any().any()


@pytest.mark.parametrize("nome", list(ESTRATEGIAS_DE_CARTEIRA))
def test_nenhuma_estrategia_olha_o_futuro(nome):
    precos = _precos()
    completo = gerar_pesos(nome, precos)
    cortado = gerar_pesos(nome, precos.iloc[:-60])
    # o último dia do corte vira um "fim de mês" falso (o calendário real continuaria),
    # então a conferência vai até o penúltimo dia
    assert np.allclose(completo.iloc[:-61].to_numpy(), cortado.iloc[:-1].to_numpy())


@pytest.mark.parametrize("nome", list(ESTRATEGIAS_DE_CARTEIRA))
def test_simular_carteira_roda_para_todas(nome):
    r = simular_carteira(nome, _precos(), 0.0005)
    assert len(r.retorno) == 900 and r.curva_de_capital.iloc[-1] > 0
    assert (r.exposicao <= 1 + 1e-9).all()


def test_decisoes_so_mudam_no_fim_do_mes():
    pesos = gerar_pesos("Rotação por momentum", _precos())
    mudou = pesos.diff().abs().sum(axis=1) > 1e-12
    assert set(pesos.index[mudou]) <= set(dias_de_decisao(pesos.index))


def test_rotacao_escolhe_o_ativo_de_maior_momentum():
    indice = pd.bdate_range("2021-01-04", periods=400)
    precos = pd.DataFrame(
        {
            "fraco": np.linspace(100, 90, 400),
            "forte": np.linspace(100, 200, 400),
            "medio": np.linspace(100, 120, 400),
        },
        index=indice,
    )
    pesos = gerar_pesos("Rotação por momentum", precos, melhores=1)
    ultimo = pesos.iloc[-1]
    assert ultimo["forte"] == 1 and ultimo["fraco"] == 0 and ultimo["medio"] == 0


def test_momentum_dual_vai_para_o_caixa_quando_tudo_cai():
    indice = pd.bdate_range("2021-01-04", periods=400)
    precos = pd.DataFrame(
        {"A": np.linspace(100, 60, 400), "B": np.linspace(100, 80, 400)}, index=indice
    )
    assert gerar_pesos("Momentum dual", precos).iloc[-1].sum() == 0
    assert gerar_pesos("Rotação por momentum", precos, melhores=1).iloc[-1].sum() == 1


def test_inverso_da_volatilidade_da_mais_peso_ao_ativo_calmo():
    rng = np.random.default_rng(0)
    indice = pd.bdate_range("2021-01-04", periods=300)
    precos = pd.DataFrame(
        {
            "calmo": 100 * np.cumprod(1 + rng.normal(0, 0.005, 300)),
            "agitado": 100 * np.cumprod(1 + rng.normal(0, 0.02, 300)),
        },
        index=indice,
    )
    ultimo = gerar_pesos("Pesos pelo inverso da volatilidade", precos).iloc[-1]
    assert ultimo.sum() == pytest.approx(1)
    assert ultimo["calmo"] > 2 * ultimo["agitado"]


def test_baixa_volatilidade_fica_com_o_mais_calmo():
    rng = np.random.default_rng(1)
    indice = pd.bdate_range("2021-01-04", periods=300)
    precos = pd.DataFrame(
        {
            "calmo": 100 * np.cumprod(1 + rng.normal(0, 0.004, 300)),
            "medio": 100 * np.cumprod(1 + rng.normal(0, 0.01, 300)),
            "agitado": 100 * np.cumprod(1 + rng.normal(0, 0.03, 300)),
        },
        index=indice,
    )
    ultimo = gerar_pesos("Baixa volatilidade", precos, melhores=1).iloc[-1]
    assert ultimo["calmo"] == 1 and ultimo.sum() == 1


def test_canario_desliga_tudo_quando_o_primeiro_ativo_cai():
    indice = pd.bdate_range("2021-01-04", periods=400)
    precos = pd.DataFrame(
        {"canario": np.linspace(100, 70, 400), "outro": np.linspace(100, 200, 400)},
        index=indice,
    )
    assert gerar_pesos("Ativo-canário", precos).iloc[-1].sum() == 0
    invertido = precos[["outro", "canario"]]
    assert gerar_pesos("Ativo-canário", invertido).iloc[-1].sum() == pytest.approx(1)


def test_pesos_iguais_comecam_no_primeiro_dia_e_somam_um():
    pesos = gerar_pesos("Pesos iguais (referência)", _precos())
    assert (pesos == 0.25).all().all()


# --- validações ---------------------------------------------------------------------------


def test_gerar_pesos_valida_estrategia_parametros_e_numero_de_ativos():
    precos = _precos()
    with pytest.raises(ValueError, match="desconhecida"):
        gerar_pesos("Inexistente", precos)
    with pytest.raises(ValueError, match="desconhecidos"):
        gerar_pesos("Momentum dual", precos, xis=1)
    with pytest.raises(ValueError, match="deve ficar entre"):
        gerar_pesos("Momentum dual", precos, melhores=99)
    with pytest.raises(ValueError, match="Use de"):
        gerar_pesos("Momentum dual", precos[["A"]])
    with pytest.raises(ValueError, match="mais ativos"):
        gerar_pesos("Momentum dual", precos[["A", "B"]], melhores=3)


def test_hrp_comeca_com_60_dias_de_historico_e_nao_um_ano():
    pesos = gerar_pesos("Paridade hierárquica de risco (HRP)", _precos())
    primeiro = pesos.index[(pesos.sum(axis=1) > 0).to_numpy()][0]
    assert (primeiro - pesos.index[0]).days < 130
    assert pesos.loc[primeiro].sum() == pytest.approx(1.0)
