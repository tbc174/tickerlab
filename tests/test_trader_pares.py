"""Ficha P0-4: janelas, Engle-Granger com BH, sinal, execução, aluguel, IR e deslistagem."""

import json
import math
from itertools import pairwise

import numpy as np
import pandas as pd
import pytest

from tests.ajudantes_pares import (
    DESLISTADA,
    TICKERS,
    dados_sinteticos,
    deslistar,
)
from trader.estrategias import pares

# Com 12 meses de formação e meia-vida >= 5, o t do ADF fica perto de -4 (ver o relatório da
# ficha); os testes de mecânica usam 24 meses para os pares sintéticos passarem pelo BH.
FORMACAO_DOS_TESTES = 24
P = pares.Parametros(meses_de_formacao=FORMACAO_DOS_TESTES)


@pytest.fixture(scope="module")
def dados():
    return dados_sinteticos()


@pytest.fixture(scope="module")
def candidato(dados):
    return pares.simular(dados, P)


def _janelas(dados):
    return pares.janelas(pd.DatetimeIndex(dados.fechamento.index), FORMACAO_DOS_TESTES)


# --- janelas -------------------------------------------------------------------------------------


def test_janelas_de_6_meses_sem_sobreposicao_depois_de_12_meses_de_formacao():
    datas = pd.bdate_range("2015-01-02", "2017-12-29")
    lista = pares.janelas(datas)
    assert datas[lista[0].inicio] == pd.Timestamp("2016-01-04")
    assert datas[lista[0].inicio_da_formacao] == datas[0]
    assert lista[0].fim_da_formacao == lista[0].inicio - 1
    for atual, seguinte in pairwise(lista):
        assert seguinte.inicio == atual.fim + 1
    assert [datas[j.inicio].strftime("%Y-%m") for j in lista] == [
        "2016-01",
        "2016-07",
        "2017-01",
        "2017-07",
    ]
    assert lista[-1].fim == len(datas) - 1


def test_formacao_mais_longa_pula_as_janelas_sem_dados_e_mantem_o_calendario():
    datas = pd.bdate_range("2015-01-02", "2017-12-29")
    curta = pares.janelas(datas, 12)
    longa = pares.janelas(datas, 14)
    assert [j.inicio for j in longa] == [j.inicio for j in curta[1:]]
    assert datas[longa[0].inicio_da_formacao] == pd.Timestamp("2015-05-04")


# --- Benjamini-Hochberg e Engle-Granger ----------------------------------------------------------


def test_benjamini_hochberg_bate_com_a_conta_a_mao():
    p = np.array([0.01, 0.04, 0.03, 0.20])
    # ordenados 0,01 0,03 0,04 0,20 → × 4 ÷ posição = 0,04 0,06 0,0533 0,20 → mínimo acumulado de trás
    esperado = np.array([0.04, 0.0533333, 0.0533333, 0.20])
    assert pares.benjamini_hochberg(p) == pytest.approx(esperado, abs=1e-6)
    assert pares.benjamini_hochberg(np.array([])).size == 0


def test_formar_acha_os_pares_cointegrados_e_deixa_o_ruido(dados):
    lista = _janelas(dados)
    formacao = pares.formar(dados, lista[2], P)
    achados = {(par.y, par.x) for par in formacao.candidatos}
    assert {("CCC3", "DDD3"), ("GGG3", "HHH3")} <= {tuple(sorted(a)) for a in achados}
    ruido = {"EEE3", "FFF3"}
    assert not any({par.y, par.x} <= ruido for par in formacao.candidatos)
    assert formacao.testados == math.comb(
        8, 2
    )  # 8 empresas: AAA4 fica fora (uma por empresa)
    for par in formacao.candidatos:
        assert pares.MEIA_VIDA_MINIMA <= par.meia_vida <= pares.MEIA_VIDA_MAXIMA
        assert par.beta > 0 and par.p_ajustado <= P.q_do_bh
    ordem = [(par.p_ajustado, par.meia_vida) for par in formacao.candidatos]
    assert ordem == sorted(ordem)


def test_beta_negativo_nao_e_par():
    gerador = np.random.default_rng(3)
    log_x = pd.Series(np.cumsum(gerador.normal(0, 0.01, 300)))
    log_y = -log_x + gerador.normal(0, 0.001, 300)
    *_, p_valor = pares._testar(log_y, log_x)
    assert p_valor == 1.0


def test_on_pn_testa_so_as_classes_da_mesma_empresa_e_y_e_a_mais_liquida(dados):
    formacao = pares.formar(dados, _janelas(dados)[0], pares.com(P, conjunto="on_pn"))
    assert formacao.testados == 1
    assert [(par.y, par.x) for par in formacao.candidatos] == [("AAA3", "AAA4")]


def test_setor_so_testa_pares_do_mesmo_setor_conhecido_antes_do_dia(dados):
    p = pares.com(P, conjunto="setor")
    formacao = pares.formar(dados, _janelas(dados)[0], p)
    assert all(
        {par.y, par.x} <= {"AAA3", "BBB3", "GGG3", "HHH3"}
        for par in formacao.candidatos
    )
    # Energia (AAA, BBB, GGG, HHH): 6 pares; Bancos (CCC, EEE): 1; Varejo (DDD, FFF): 1
    assert formacao.testados == 8
    depois = dados.setores.assign(conhecido_em=pd.Timestamp("2030-01-01"))
    sem_setor = pares.formar(
        pares.Dados(**{**dados.__dict__, "setores": depois}), _janelas(dados)[0], p
    )
    assert sem_setor.testados == 0


def test_sem_deslistadas_tira_quem_nao_chega_ao_fim_dos_dados(dados):
    formacao = pares.formar(
        dados, _janelas(dados)[0], pares.com(P, com_deslistadas=False)
    )
    assert all(DESLISTADA not in (par.y, par.x) for par in formacao.candidatos)
    assert formacao.testados == math.comb(7, 2)


def test_formacao_nao_ve_o_que_vem_depois(dados):
    janela = _janelas(dados)[0]
    mexido = dados.fechamento.copy()
    mexido.iloc[janela.inicio :] *= np.linspace(1, 3, len(mexido) - janela.inicio)[
        :, None
    ] ** np.arange(1, len(TICKERS) + 1)
    outros = pares.Dados(**{**dados.__dict__, "fechamento": mexido})
    assert pares.formar(outros, janela, P) == pares.formar(dados, janela, P)


# --- sinal ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("z", "lado", "pregoes", "esperado"),
    [
        (2.5, 0, 0, pares.VENDER_SPREAD),
        (-2.5, 0, 0, pares.COMPRAR_SPREAD),
        (1.9, 0, 0, ""),
        (4.5, 0, 0, ""),  # além do stop não entra
        (0.3, 1, 3, pares.SAIR),
        (-0.3, -1, 3, pares.SAIR),
        (1.0, 1, 3, ""),
        (4.1, -1, 3, pares.STOP),
        (1.0, 1, 20, pares.STOP),  # 3 × meia-vida de 6,6 = 20 pregões
        (float("nan"), 1, 3, ""),
    ],
)
def test_decidir(z, lado, pregoes, esperado):
    assert (
        pares.decidir(z, lado, pregoes, math.ceil(3 * 6.6), pares.Parametros())
        == esperado
    )


# --- motor ------------------------------------------------------------------------------------------


def test_opera_e_executa_no_fechamento_do_pregao_seguinte(dados, candidato):
    operacoes = candidato.operacoes
    assert len(operacoes) >= 5
    datas = pd.DatetimeIndex(dados.fechamento.index)
    seguinte = datas[datas.get_indexer(operacoes["sinal"]) + 1]
    assert (pd.DatetimeIndex(operacoes["entrada"]) == seguinte).all()
    no_sinal = pares.simular(dados, pares.com(P, executar_no_sinal=True))
    assert (no_sinal.operacoes["entrada"] == no_sinal.operacoes["sinal"]).all()


def test_pernas_em_lados_opostos_e_no_tamanho_do_beta(dados, candidato):
    operacoes = candidato.operacoes
    assert (np.sign(operacoes["q_y"]) == operacoes["lado"]).all()
    assert (np.sign(operacoes["q_x"]) == -operacoes["lado"]).all()
    primeira = operacoes.iloc[0]
    par = next(
        par
        for janela in candidato.janelas
        for par in janela["pares"]
        if (par["y"], par["x"]) == (primeira["y"], primeira["x"])
    )
    preco_y = dados.fechamento.loc[primeira["entrada"], primeira["y"]]
    preco_x = dados.fechamento.loc[primeira["entrada"], primeira["x"]]
    alocacao = P.capital_inicial / P.max_pares  # a 1ª operação é da 1ª janela
    assert abs(primeira["q_y"]) * preco_y == pytest.approx(
        alocacao / (1 + par["beta"]), abs=preco_y
    )
    assert abs(primeira["q_x"]) * preco_x == pytest.approx(
        alocacao * par["beta"] / (1 + par["beta"]), abs=preco_x
    )


def test_pesos_sao_neutros_e_a_carteira_fica_zerada_no_fim_de_cada_janela(
    dados, candidato
):
    assert (candidato.pesos.sum(axis=1).abs() < 0.05).all()
    for janela in _janelas(dados):
        fim = dados.fechamento.index[janela.fim]
        assert (candidato.pesos.loc[fim] == 0).all()
        assert not (candidato.operacoes["entrada"] == fim).any()


def test_sem_day_trade_no_mesmo_par_e_pelo_menos_um_pregao_na_posicao(candidato):
    assert candidato.fechadas_no_dia_da_entrada == 0
    assert (candidato.operacoes["saida"] > candidato.operacoes["entrada"]).all()
    assert candidato.dias_de_day_trade == 0


def test_lote_de_100_so_negocia_multiplos_de_100(dados):
    resultado = pares.simular(dados, pares.com(P, fracionario=False))
    for coluna in ("q_y", "q_x"):
        assert (resultado.operacoes[coluna] % 100 == 0).all()
    assert len(resultado.operacoes) < len(pares.simular(dados, P).operacoes)


def test_aluguel_cobrado_na_perna_vendida_com_minimo_de_10(dados, candidato):
    assert candidato.aluguel.sum() >= 10 * len(candidato.operacoes)
    caro = pares.simular(dados, pares.com(P, taxa_do_aluguel=0.50))
    assert caro.aluguel.sum() > candidato.aluguel.sum()
    assert caro.patrimonio.iloc[-1] < candidato.patrimonio.iloc[-1]


def test_stop_tira_o_par_da_janela(dados):
    resultado = pares.simular(dados, pares.com(P, multiplo_da_meia_vida=0.01))
    operacoes = resultado.operacoes
    assert (operacoes["motivo"].isin(["stop", "deslistagem", "fim_da_janela"])).all()
    janela = pd.cut(
        pd.DatetimeIndex(operacoes["entrada"]),
        [pd.Timestamp(j["inicio"]) for j in resultado.janelas]
        + [pd.Timestamp("2100-01-01")],
        right=False,
    )
    assert not operacoes.assign(janela=janela).duplicated(["janela", "y", "x"]).any()


def test_deslistagem_fecha_as_duas_pernas_e_tira_o_par(dados, candidato):
    longa = candidato.operacoes[
        (candidato.operacoes["saida"] - candidato.operacoes["entrada"]).dt.days >= 5
    ].iloc[0]
    dia = longa["entrada"] + pd.offsets.BDay(1)
    quebrado = pares.simular(deslistar(dados, longa["x"], dia), P)
    linha = quebrado.operacoes[
        (quebrado.operacoes["y"] == longa["y"])
        & (quebrado.operacoes["entrada"] == longa["entrada"])
    ].iloc[0]
    assert linha["motivo"] == "deslistagem"
    assert linha["saida"] == dia + pd.offsets.BDay(1)
    assert quebrado.quebrados_por_deslistagem >= 1
    depois = quebrado.pesos.loc[quebrado.pesos.index > dia, longa["x"]]
    assert (depois == 0).all()


def test_imposto_quando_as_vendas_passam_da_isencao_e_darf_no_fim_do_mes(dados):
    grande = pares.simular(dados, pares.com(P, capital_inicial=5_000_000.0))
    pagos = grande.imposto[grande.imposto > 0]
    assert len(pagos) > 0
    fins = (
        pd.DatetimeIndex(grande.imposto.index)
        .to_series()
        .groupby(grande.imposto.index.to_period("M"))
        .max()
    )
    assert set(pagos.index) <= set(fins)


def test_sem_pares_o_caixa_rende_o_cdi(dados):
    sem_setores = pares.Dados(**{**dados.__dict__, "setores": None})
    resultado = pares.simular(sem_setores, pares.com(P, conjunto="setor"))
    assert resultado.operacoes.empty
    assert resultado.retorno.to_numpy() == pytest.approx(0.0003)


def test_estresse_e_custos_pioram(dados, candidato):
    estresse = pares.simular(
        dados, pares.com(P, custos=P.custos.em_estresse(2.0), fator_de_impacto=2.0)
    )
    assert estresse.custos.sum() > candidato.custos.sum()
    assert estresse.patrimonio.iloc[-1] < candidato.patrimonio.iloc[-1]


def test_cortar_o_futuro_nao_muda_o_passado(dados):
    corte = dados.fechamento.index[int(len(dados.fechamento) * 0.8)]
    assert pares.cortar_o_futuro_nao_muda_o_passado(dados, P, corte)


def test_reexecucao_identica_e_o_cache_nao_muda_nada(dados, candidato):
    cache: dict = {}
    primeira = pares.simular(dados, P, cache)
    assert cache
    vizinho = pares.simular(dados, pares.com(P, z_entrada=2.4), cache)
    assert pares.hash_do_resultado(primeira) == pares.hash_do_resultado(candidato)
    assert pares.hash_do_resultado(
        pares.simular(dados, P, cache)
    ) == pares.hash_do_resultado(candidato)
    assert pares.hash_do_resultado(vizinho) == pares.hash_do_resultado(
        pares.simular(dados, pares.com(P, z_entrada=2.4))
    )


def test_especificacao_vai_para_o_registro_em_tipos_simples():
    spec = pares.Parametros().especificacao()
    json.dumps(spec)
    assert spec["z_entrada"] == 2.0 and spec["meia_vida"] == [5.0, 30.0]
    assert spec["meses_de_operacao"] == 6 and spec["versao"] == pares.VERSAO


@pytest.mark.parametrize(
    "mudanca",
    [
        {"conjunto": "qualquer"},
        {"z_saida": 2.5},
        {"z_stop": 1.5},
        {"max_pares": 0},
        {"q_do_bh": 1.0},
        {"taxa_do_aluguel": -0.01},
    ],
)
def test_parametros_invalidos_sao_recusados(mudanca):
    with pytest.raises(ValueError):
        pares.Parametros(**mudanca)
