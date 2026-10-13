"""Entradas do modelo C-1 (pré-registro v2, seção 3), só com dados sintéticos."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from base.cripto.c1.entradas import (
    COLUNAS,
    montar_entradas,
    posicoes_em_btc,
    variacao_log,
    variacao_relativa,
)

INICIO = date(2018, 1, 1)
N = 400
DIAS = [INICIO + timedelta(days=i) for i in range(N)]


def _meia_noite(dias, mais=1):
    return pd.to_datetime(pd.Series(dias)).dt.tz_localize("UTC") + pd.Timedelta(
        days=mais
    )


def _tabelas(semente: int = 3) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(semente)
    fechamento = 10_000 * np.exp(np.cumsum(rng.normal(0, 0.03, N)))
    precos = pd.DataFrame(
        {
            "dia": DIAS,
            "fechamento": fechamento,
            "maxima": fechamento * 1.02,
            "minima": fechamento * 0.98,
            "divulgado_em": _meia_noite(DIAS),
        }
    )
    rede = pd.DataFrame({"dia": DIAS, "divulgado_em": _meia_noite(DIAS)})
    for coluna in (
        "taxas_total",
        "taxa_mediana_por_vbyte",
        "n_transacoes",
        "valor_movimentado",
        "dias_moeda_destruidos",
        "fracao_parada_1_ano",
        "dificuldade",
    ):
        rede[coluna] = rng.uniform(1, 2, N)
    terças = [d for d in DIAS if d.weekday() == 1]
    cot = pd.DataFrame(
        {
            "relatorio": terças * 2,
            "contrato": ["bitcoin"] * len(terças) + ["micro_bitcoin"] * len(terças),
            "contratos_em_aberto": rng.integers(100, 200, 2 * len(terças)),
            "gestores_comprados": rng.integers(10, 50, 2 * len(terças)),
            "gestores_vendidos": rng.integers(10, 50, 2 * len(terças)),
            "alavancados_comprados": rng.integers(10, 50, 2 * len(terças)),
            "alavancados_vendidos": rng.integers(10, 50, 2 * len(terças)),
        }
    )
    cot["divulgado_em"] = _meia_noite(cot["relatorio"], mais=6)
    wikipedia = pd.DataFrame(
        {"dia": DIAS, "projeto": "en.wikipedia", "acessos": rng.integers(1000, 5000, N)}
    )
    wikipedia["divulgado_em"] = _meia_noite(DIAS, mais=2)
    gdelt = pd.DataFrame(
        {
            "dia": DIAS,
            "fracao_das_noticias": rng.uniform(0.001, 0.01, N),
            "tom": rng.normal(0, 2, N),
        }
    )
    gdelt["divulgado_em"] = _meia_noite(DIAS)
    macro = {
        "ptax": pd.DataFrame(
            {"dia": DIAS, "valor": 5 + rng.normal(0, 0.05, N).cumsum() * 0.01}
        ),
        "juro_2_anos_eua": pd.DataFrame({"dia": DIAS, "valor": rng.uniform(1, 5, N)}),
        "selic": pd.DataFrame({"dia": DIAS, "valor": rng.uniform(2, 14, N)}),
    }
    for tabela in macro.values():
        tabela["divulgado_em"] = _meia_noite(tabela["dia"])
    return {
        "precos": precos,
        "rede": rede,
        "cot": cot,
        "wikipedia": wikipedia,
        "gdelt": gdelt,
        **macro,
    }


def _cortar(
    tabelas: dict[str, pd.DataFrame], momento: pd.Timestamp
) -> dict[str, pd.DataFrame]:
    return {nome: t[t["divulgado_em"] <= momento] for nome, t in tabelas.items()}


def test_entradas_tem_a_lista_fechada_do_pre_registro():
    entradas = montar_entradas(_tabelas(), DIAS[200:210])

    assert list(entradas.columns) == COLUNAS
    assert list(entradas.index) == DIAS[200:210]


def test_entradas_nao_olham_o_futuro():
    tabelas = _tabelas()
    dias = DIAS[150:300]
    corte = pd.Timestamp(DIAS[250], tz="UTC")  # tudo divulgado depois disto some

    completas = montar_entradas(tabelas, dias)
    cortadas = montar_entradas(_cortar(tabelas, corte), dias)

    ate_o_corte = [d for d in dias if pd.Timestamp(d, tz="UTC") <= corte]
    pd.testing.assert_frame_equal(completas.loc[ate_o_corte], cortadas.loc[ate_o_corte])


def test_entrada_so_entra_depois_do_divulgado_em():
    tabelas = _tabelas()
    d = DIAS[300]
    # o preço do dia D-1 só vale às 00:00 de D: atrasar a divulgação em 1 hora tira ele da previsão de D
    atrasado = tabelas["precos"].copy()
    atrasado.loc[atrasado["dia"] == DIAS[299], "divulgado_em"] += pd.Timedelta(hours=1)

    normal = montar_entradas(tabelas, [d]).loc[d]
    com_atraso = montar_entradas({**tabelas, "precos": atrasado}, [d]).loc[d]

    assert normal["retorno_30"] != com_atraso["retorno_30"]


def test_volatilidade_de_1_dia_e_o_retorno_absoluto_de_d_menos_1():
    tabelas = _tabelas()
    d = DIAS[300]
    fechamento = tabelas["precos"].set_index("dia")["fechamento"]

    entradas = montar_entradas(tabelas, [d]).loc[d]

    esperado = abs(np.log(fechamento[DIAS[299]] / fechamento[DIAS[298]]))
    assert entradas["vol_1"] == pytest.approx(esperado)


def test_variacao_log_contra_a_media_dos_90_dias_anteriores():
    serie = pd.Series([1.0] * 90 + [2.0], index=pd.to_datetime(DIAS[:91]))

    assert variacao_log(serie).iloc[-1] == pytest.approx(np.log(2.0))
    assert np.isnan(variacao_log(serie).iloc[0])  # sem passado, sem variação


def test_variacao_relativa_aceita_valores_negativos():
    serie = pd.Series([-1.0, 1.0] * 45 + [3.0], index=pd.to_datetime(DIAS[:91]))

    # média dos 90 anteriores = 0; média dos absolutos = 1: (3 - 0) / 1
    assert variacao_relativa(serie).iloc[-1] == pytest.approx(3.0)


def test_posicao_liquida_em_btc():
    cot = pd.DataFrame(
        {
            "relatorio": [date(2021, 5, 4)] * 2,
            "contrato": ["bitcoin", "micro_bitcoin"],
            "contratos_em_aberto": [100, 1000],
            "gestores_comprados": [10, 100],
            "gestores_vendidos": [4, 50],
            "alavancados_comprados": [1, 0],
            "alavancados_vendidos": [3, 10],
            "divulgado_em": pd.to_datetime(["2021-05-10"] * 2, utc=True),
        }
    )

    btc = posicoes_em_btc(cot).iloc[0]

    # Bitcoin: 5 BTC por contrato; Micro Bitcoin: 0,1 BTC
    assert btc["gestores_liquido"] == pytest.approx(6 * 5 + 50 * 0.1)
    assert btc["alavancados_liquido"] == pytest.approx(-2 * 5 + -10 * 0.1)
    assert btc["contratos_em_aberto"] == pytest.approx(100 * 5 + 1000 * 0.1)
