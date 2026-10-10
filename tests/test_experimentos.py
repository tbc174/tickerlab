"""Testes de src/experimentos.py."""

import numpy as np
import pandas as pd
import pytest

from src import experimentos as ex


def _serie(valores, inicio="2026-01-05"):
    return pd.Series(
        np.array(valores, dtype=float),
        index=pd.bdate_range(inicio, periods=len(valores)),
    )


def _caminhada(n=900, semente=2, deriva=0.0004, vol=0.012):
    rng = np.random.default_rng(semente)
    return _serie(100 * np.cumprod(1 + rng.normal(deriva, vol, n)), "2021-01-04")


# --- aporte único × DCA -------------------------------------------------------------------


def test_dca_em_preco_constante_empata_com_o_aporte_unico():
    r = ex.simular_aporte_unico_e_dca(_serie([100.0] * 100), 1000, 4, intervalo=10)
    assert np.allclose(r["Aporte único"], 1000)
    assert np.allclose(r["Parcelado"], 1000)


def test_dca_em_mercado_so_de_alta_perde_para_o_aporte_unico():
    r = ex.simular_aporte_unico_e_dca(
        _serie(np.linspace(100, 200, 100)), 1000, 5, intervalo=10
    )
    assert r["Aporte único"].iloc[-1] > r["Parcelado"].iloc[-1]
    assert r["Aporte único"].iloc[-1] == pytest.approx(2000)


def test_dca_em_mercado_so_de_queda_ganha_do_aporte_unico():
    r = ex.simular_aporte_unico_e_dca(
        _serie(np.linspace(200, 100, 100)), 1000, 5, intervalo=10
    )
    assert r["Parcelado"].iloc[-1] > r["Aporte único"].iloc[-1]


def test_dca_comeca_com_o_total_em_caixa_e_conta_cada_parcela():
    # preço 100 e depois 50: a 1ª parcela (250) compra 2,5 cotas, as outras compram a 50
    precos = _serie([100.0] + [50.0] * 30)
    r = ex.simular_aporte_unico_e_dca(precos, 1000, 4, intervalo=10)
    assert r["Parcelado"].iloc[0] == pytest.approx(1000)
    cotas = 250 / 100 + 3 * 250 / 50
    assert r["Parcelado"].iloc[-1] == pytest.approx(cotas * 50)


def test_dca_valida_entradas():
    precos = _serie([100.0] * 30)
    with pytest.raises(ValueError, match="2 parcelas"):
        ex.simular_aporte_unico_e_dca(precos, 1000, 1)
    with pytest.raises(ValueError, match="suficientes"):
        ex.simular_aporte_unico_e_dca(precos, 1000, 10, intervalo=21)
    with pytest.raises(ValueError, match="maior que zero"):
        ex.simular_aporte_unico_e_dca(precos, 0, 3, intervalo=5)


def test_janelas_batem_com_a_simulacao_de_uma_janela():
    precos = _caminhada(300)
    janelas = ex.comparar_janelas(precos, parcelas=4, horizonte=120, intervalo=10)
    inicio = 37
    trecho = precos.iloc[inicio : inicio + 121]
    sim = ex.simular_aporte_unico_e_dca(trecho, 1.0, 4, intervalo=10)
    assert janelas["Aporte único"].iloc[inicio] == pytest.approx(
        sim["Aporte único"].iloc[-1]
    )
    assert janelas["Parcelado"].iloc[inicio] == pytest.approx(sim["Parcelado"].iloc[-1])
    assert len(janelas) == 300 - 120


def test_resumo_das_janelas():
    janelas = ex.comparar_janelas(_serie(np.linspace(100, 300, 400)), 4, 120, 10)
    resumo = ex.resumir_janelas(janelas)
    assert resumo["Aporte único vence"] == 1.0  # mercado só de alta
    assert resumo["Diferença mediana"] > 0
    assert resumo["Pior caso do aporte único"] > 0


def test_janelas_validam_entradas():
    precos = _caminhada(200)
    with pytest.raises(ValueError, match="maior que o histórico"):
        ex.comparar_janelas(precos, 3, 500, 10)
    with pytest.raises(ValueError, match="suficientes"):
        ex.comparar_janelas(precos, 12, 100, 21)
    with pytest.raises(ValueError, match="resumir"):
        ex.resumir_janelas(pd.DataFrame(columns=["Diferença"]))


# --- rebalanceamento ----------------------------------------------------------------------


def _dois_ativos(n=600, semente=4):
    rng = np.random.default_rng(semente)
    indice = pd.bdate_range("2021-01-04", periods=n)
    return pd.DataFrame(
        {
            "A": 100 * np.cumprod(1 + rng.normal(0.0006, 0.015, n)),
            "B": 100 * np.cumprod(1 + rng.normal(0.0003, 0.008, n)),
        },
        index=indice,
    )


def test_sem_rebalancear_e_comprar_e_segurar_a_carteira():
    f = _dois_ativos()
    r = ex.simular_rebalanceamento(f, 0.5, "Nunca", custo_por_operacao=0.0)
    esperado = 0.5 * f["A"] / f["A"].iloc[0] + 0.5 * f["B"] / f["B"].iloc[0]
    assert np.allclose(r.curva_de_capital, esperado)
    assert r.rebalanceamentos == 0 and r.giro == 1.0


def test_faixa_menor_rebalanceia_mais_vezes():
    f = _dois_ativos()
    pequena = ex.simular_rebalanceamento(f, 0.5, "Por faixa", 0.02)
    grande = ex.simular_rebalanceamento(f, 0.5, "Por faixa", 0.20)
    assert pequena.rebalanceamentos > grande.rebalanceamentos >= 0


def test_rebalancear_todo_mes_faz_uma_vez_por_mes():
    f = _dois_ativos()
    r = ex.simular_rebalanceamento(f, 0.5, "Todo mês")
    meses = f.index.to_period("M").nunique()
    assert abs(r.rebalanceamentos - meses) <= 1


def test_rebalancear_custa_dinheiro():
    f = _dois_ativos()
    barato = ex.simular_rebalanceamento(f, 0.5, "Por faixa", 0.02, 0.0)
    caro = ex.simular_rebalanceamento(f, 0.5, "Por faixa", 0.02, 0.01)
    assert caro.curva_de_capital.iloc[-1] < barato.curva_de_capital.iloc[-1]
    assert caro.giro == pytest.approx(barato.giro, rel=0.05)


def test_dois_ativos_iguais_nao_precisam_de_rebalanceamento():
    f = _dois_ativos()
    f["B"] = f["A"]
    r = ex.simular_rebalanceamento(f, 0.5, "Por faixa", 0.01)
    assert r.rebalanceamentos == 0


def test_rebalanceamento_valida_entradas():
    f = _dois_ativos()
    with pytest.raises(ValueError, match="dois ativos"):
        ex.simular_rebalanceamento(f.assign(C=f["A"]))
    with pytest.raises(ValueError, match="Regra"):
        ex.simular_rebalanceamento(f, regra="Sempre")
    with pytest.raises(ValueError, match="peso"):
        ex.simular_rebalanceamento(f, peso_do_primeiro=1.0)
    with pytest.raises(ValueError, match="faixa"):
        ex.simular_rebalanceamento(f, faixa=0)
    with pytest.raises(ValueError, match="negativo"):
        ex.simular_rebalanceamento(f, custo_por_operacao=-1)


# --- noite × dia --------------------------------------------------------------------------


def _ohlc():
    return pd.DataFrame(
        {"Open": [100, 102, 101, 105.0], "Close": [100, 101, 103, 104.0]},
        index=pd.bdate_range("2026-01-05", periods=4),
    )


def test_noite_e_dia_compostos_dao_o_retorno_total():
    dados = _ohlc()
    partes = ex.separar_noite_e_dia(dados)
    total = (1 + partes["Noite"]) * (1 + partes["Dia"]) - 1
    esperado = dados["Close"].pct_change().dropna()
    assert np.allclose(total, esperado)


def test_noite_e_dia_com_numeros_conferidos_a_mao():
    partes = ex.separar_noite_e_dia(_ohlc())
    assert partes["Noite"].iloc[0] == pytest.approx(102 / 100 - 1)
    assert partes["Dia"].iloc[0] == pytest.approx(101 / 102 - 1)


def test_resumo_da_noite_e_do_dia():
    partes = ex.separar_noite_e_dia(_caminhada_ohlc())
    resumo = ex.resumir_noite_e_dia(partes)
    assert list(resumo.index) == ["Noite", "Dia", "Total"]
    composto = (1 + resumo.loc["Noite", "Retorno total"]) * (
        1 + resumo.loc["Dia", "Retorno total"]
    )
    assert composto - 1 == pytest.approx(resumo.loc["Total", "Retorno total"])


def _caminhada_ohlc(n=300):
    fechamento = _caminhada(n)
    rng = np.random.default_rng(9)
    abertura = fechamento.shift(1).fillna(fechamento.iloc[0]) * (
        1 + rng.normal(0.0002, 0.004, n)
    )
    return pd.DataFrame({"Open": abertura, "Close": fechamento})


def test_custo_da_noite_cobra_duas_vezes_por_dia():
    partes = pd.DataFrame({"Noite": [0.0, 0.0], "Dia": [0.0, 0.0]})
    liquido = ex.calcular_retorno_da_noite_com_custo(partes, 0.01)
    assert liquido.iloc[0] == pytest.approx(0.99**2 - 1)
    with pytest.raises(ValueError, match="negativo"):
        ex.calcular_retorno_da_noite_com_custo(partes, -0.1)


def test_noite_e_dia_valida_dados():
    with pytest.raises(ValueError, match="Open"):
        ex.separar_noite_e_dia(pd.DataFrame({"Close": [1.0, 2.0, 3.0]}))
    sem_abertura = _ohlc().assign(Open=0.0)
    with pytest.raises(ValueError, match="Poucos dias"):
        ex.separar_noite_e_dia(sem_abertura)


# --- virada do mês ------------------------------------------------------------------------


def test_virada_marca_o_fim_de_um_mes_e_o_comeco_do_outro():
    indice = pd.bdate_range("2026-01-01", "2026-04-30")
    m = ex.marcar_virada_do_mes(indice, 1, 3)
    marcados = list(indice[m].strftime("%m-%d"))
    # janeiro começa inteiro; fevereiro: 3 primeiros + último de janeiro; abril é o último mês
    assert "01-30" in marcados and "02-02" in marcados and "02-04" in marcados
    assert "02-05" not in marcados
    assert "04-30" not in marcados  # o último mês chegou cortado: o fim dele não conta


def test_virada_no_primeiro_mes_cortado_nao_conta_o_comeco():
    indice = pd.bdate_range("2026-01-14", "2026-03-31")
    m = ex.marcar_virada_do_mes(indice, 1, 3)
    assert not m[indice[:5]].any()


def test_virada_valida_entradas():
    indice = pd.bdate_range("2026-01-01", periods=60)
    with pytest.raises(ValueError, match="pelo menos um"):
        ex.marcar_virada_do_mes(indice, 0, 0)
    with pytest.raises(ValueError, match="15 dias"):
        ex.marcar_virada_do_mes(indice, 10, 10)


def test_simulacao_da_virada_fica_comprada_so_nos_dias_marcados():
    precos = _caminhada(300)
    r, marcados = ex.simular_virada_do_mes(precos, 1, 3, custo_por_operacao=0.0)
    comprado = r.posicao > 0
    assert (comprado.iloc[1:] == marcados.iloc[1:]).all()  # o 1º dia nunca tem posição
    assert 0.05 < r.posicao.mean() < 0.35


def test_comparar_dentro_e_fora_separa_os_dias():
    precos = _caminhada(300)
    retorno = precos.pct_change().fillna(0.0)
    _, marcados = ex.simular_virada_do_mes(precos, 1, 3)
    r = ex.comparar_dentro_e_fora(retorno, marcados)
    assert r["Dias dentro"] + r["Dias fora"] == 300
    with pytest.raises(ValueError, match="suficientes"):
        ex.comparar_dentro_e_fora(retorno, pd.Series(False, index=retorno.index))
