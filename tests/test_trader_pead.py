"""Ficha P0-5: lucro do trimestre ponto no tempo, SUE, datas do IPE, tercil, carteira e CAR."""

import json
import math
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from tests.ajudantes_pead import (
    CNPJS,
    DATAS,
    DIAS_ATE_O_BALANCO,
    DIAS_DO_IPE_ANTES_DO_BALANCO,
    TICKERS,
    dados_sinteticos,
    deslistar,
)
from trader.estrategias import pead

P = pead.Parametros()


@pytest.fixture(scope="module")
def dados():
    return dados_sinteticos()


@pytest.fixture(scope="module")
def eventos(dados):
    return pead.eventos_de_lucro(dados, P)


@pytest.fixture(scope="module")
def candidato(dados, eventos):
    return pead.simular(dados, P, *eventos)


# --- o lucro do trimestre e a surpresa -------------------------------------------------------------


def _q(texto):
    return pd.Period(texto, freq="Q")


def test_lucro_do_trimestre_sai_do_acumulado_no_ano():
    acumulados = {
        _q("2015Q1"): 10.0,
        _q("2015Q2"): 25.0,
        _q("2015Q3"): 33.0,
        _q("2015Q4"): 50.0,
    }
    assert pead.lucro_do_trimestre(acumulados, _q("2015Q1")) == 10.0
    assert pead.lucro_do_trimestre(acumulados, _q("2015Q3")) == 8.0
    assert (
        pead.lucro_do_trimestre(acumulados, _q("2015Q4")) == 17.0
    )  # DFP menos o de setembro
    assert math.isnan(pead.lucro_do_trimestre(acumulados, _q("2016Q2")))


def test_surpresa_e_a_variacao_sazonal_sobre_o_desvio_das_8_anteriores():
    trimestres = pd.period_range("2012Q1", "2015Q4", freq="Q")
    so_do_trimestre = pd.Series(np.arange(len(trimestres)) ** 1.5, index=trimestres)
    acumulados = {
        t: float(so_do_trimestre[(trimestres.year == t.year) & (trimestres <= t)].sum())
        for t in trimestres
    }
    variacoes = so_do_trimestre - so_do_trimestre.shift(4)
    esperado = variacoes.iloc[-1] / variacoes.iloc[-9:-1].std(ddof=1)
    sue, variacao, desvio = pead.surpresa(acumulados, trimestres[-1], 8)
    assert sue == pytest.approx(esperado)
    assert variacao == pytest.approx(variacoes.iloc[-1])
    assert desvio == pytest.approx(variacoes.iloc[-9:-1].std(ddof=1))
    sem_um = {t: v for t, v in acumulados.items() if t != _q("2013Q2")}
    assert math.isnan(pead.surpresa(sem_um, trimestres[-1], 8)[0])


def test_surpresa_com_desvio_zero_fica_de_fora():
    trimestres = pd.period_range("2012Q1", "2015Q4", freq="Q")
    acumulados = {t: 10.0 * t.quarter for t in trimestres}  # 10 por trimestre, sempre
    sue, variacao, desvio = pead.surpresa(acumulados, trimestres[-1], 8)
    assert math.isnan(sue) and variacao == 0 and desvio == 0


def test_reapresentacao_so_vale_a_partir_da_propria_data():
    linhas = pd.DataFrame(
        {
            "cnpj": "x",
            "trimestre": [_q("2015Q1"), _q("2015Q1")],
            "divulgado_em": pd.to_datetime(["2015-05-10", "2016-05-10"]),
            "valor": [10.0, 99.0],
        }
    )
    assert pead.acumulados_vigentes(linhas, pd.Timestamp("2015-05-11")) == {
        _q("2015Q1"): 10.0
    }
    assert pead.acumulados_vigentes(linhas, pd.Timestamp("2016-05-10")) == {
        _q("2015Q1"): 10.0
    }
    assert pead.acumulados_vigentes(linhas, pd.Timestamp("2016-05-11")) == {
        _q("2015Q1"): 99.0
    }
    assert pead.acumulados_vigentes(linhas, pd.Timestamp("2015-05-10")) == {}


def test_trimestre_isolado_nao_entra_como_acumulado(dados):
    isolado = dados.fundamentos.iloc[[0]].assign(
        inicio=pd.Timestamp("2009-04-01"), fim=pd.Timestamp("2009-06-30"), valor=1e9
    )
    acumulados = pead.acumulados_do_lucro(pd.concat([dados.fundamentos, isolado]))
    assert 1e9 not in acumulados["valor"].to_numpy()


# --- o dia do resultado e as datas da entrada -------------------------------------------------------


def test_dia_do_resultado_e_a_primeira_entrega_entre_o_ipe_e_o_balanco(dados):
    acumulados = pead.acumulados_do_lucro(dados.fundamentos)
    dias = pead.dias_dos_resultados(acumulados, dados.documentos)
    cnpj = CNPJS["E003"]
    fim = pd.Timestamp("2014-06-30")
    assert dias[cnpj, _q("2014Q2")] == fim + pd.Timedelta(
        days=DIAS_ATE_O_BALANCO - DIAS_DO_IPE_ANTES_DO_BALANCO
    )
    sem_ipe = pead.dias_dos_resultados(acumulados, None)
    assert sem_ipe[cnpj, _q("2014Q2")] == fim + pd.Timedelta(days=DIAS_ATE_O_BALANCO)
    # o fato relevante (10 dias depois do fim) não é documento de resultado
    so_outros = dados.documentos[dados.documentos["tema"] != "resultados"]
    assert pead.dias_dos_resultados(acumulados, so_outros).equals(sem_ipe)


def test_documento_recebido_antes_do_fim_do_trimestre_nao_e_o_anuncio(dados):
    acumulados = pead.acumulados_do_lucro(dados.fundamentos)
    cedo = pd.DataFrame(
        {
            "cnpj": [CNPJS["E003"]],
            "categoria": "Dados Econômico-Financeiros",
            "tipo": "Apresentações a analistas",
            "tema": "resultados",
            "referencia": pd.Timestamp("2014-06-30"),
            "publicado_em": pd.Timestamp("2014-06-30"),
        }
    )
    dias = pead.dias_dos_resultados(acumulados, pd.concat([dados.documentos, cedo]))
    assert dias[CNPJS["E003"], _q("2014Q2")] > pd.Timestamp("2014-06-30")


@pytest.mark.parametrize(
    ("dia", "mudanca", "dia_zero", "entrada"),
    [
        (
            "2015-06-10",
            {},
            "2015-06-11",
            "2015-06-12",
        ),  # quarta: zero na quinta, entra na sexta
        ("2015-06-12", {}, "2015-06-15", "2015-06-16"),  # sexta: zero na segunda
        ("2015-06-13", {}, "2015-06-15", "2015-06-16"),  # sábado
        ("2015-06-10", {"dia_zero_em_d": True}, "2015-06-10", "2015-06-11"),  # otimista
        (
            "2015-06-10",
            {"executar_no_sinal": True},
            "2015-06-11",
            "2015-06-10",
        ),  # V (1)
    ],
)
def test_dia_zero_e_entrada(dia, mudanca, dia_zero, entrada):
    p = pead.com(P, **mudanca)
    zero, entra = pead.posicoes_do_evento(DATAS, pd.Timestamp(dia), p)
    assert DATAS[zero] == pd.Timestamp(dia_zero)
    assert DATAS[entra] == pd.Timestamp(entrada)


# --- os eventos -------------------------------------------------------------------------------------


def test_eventos_tem_sue_ticker_e_dia_zero_e_a_contagem_fecha(eventos):
    tabela, contagem = eventos
    assert len(tabela) > 300
    assert set(tabela["ticker"]) <= set(TICKERS)
    assert tabela["sue"].notna().all()
    assert (tabela["dia_zero"] > tabela["dia_do_resultado"]).all()
    descartes = sum(
        v for k, v in contagem.items() if k not in ("trimestres", "com_sue")
    )
    assert contagem["trimestres"] == descartes + contagem["com_sue"]
    # os 2 primeiros anos de trimestres servem de histórico das 8 variações
    assert contagem["sem_sue"] > 0


def test_resultado_atrasado_mais_de_6_meses_fica_de_fora(dados):
    docs = dados.documentos[dados.documentos["tema"] != "resultados"]
    fundamentos = dados.fundamentos.copy()
    alvo = (fundamentos["cnpj"] == CNPJS["E013"]) & (fundamentos["fim"] == "2014-06-30")
    fundamentos.loc[alvo, "divulgado_em"] = pd.Timestamp("2015-02-02")
    _, contagem = pead.eventos_de_lucro(
        replace(dados, documentos=docs, fundamentos=fundamentos), P
    )
    assert contagem["atrasados"] == 1


def test_linha_do_balanco_divulgada_so_depois_da_entrada_tira_o_evento(dados):
    fundamentos = dados.fundamentos.copy()
    alvo = (fundamentos["cnpj"] == CNPJS["E023"]) & (fundamentos["fim"] == "2014-06-30")
    fundamentos.loc[alvo, "divulgado_em"] = pd.Timestamp(
        "2014-09-01"
    )  # o IPE saiu em 08/08
    tabela, contagem = pead.eventos_de_lucro(replace(dados, fundamentos=fundamentos), P)
    assert contagem["sem_linha"] == 1
    assert not (
        (tabela["cnpj"] == CNPJS["E023"]) & (tabela["trimestre"] == "2014Q2")
    ).any()


def test_fora_do_universo_quem_nao_tem_liquidez(dados):
    volume = dados.volume.copy()
    volume["E033"] = 1e5
    tabela, contagem = pead.eventos_de_lucro(replace(dados, volume=volume), P)
    assert "E033" not in set(tabela["ticker"])
    assert contagem["fora_do_universo"] > 0


def test_corte_do_tercil_so_com_o_passado_e_pelo_menos_30_eventos():
    eventos = pd.DataFrame(
        {
            "dia_zero": pd.bdate_range("2015-01-01", periods=40),
            "sue": np.arange(40, dtype=float),
        }
    )
    assert math.isnan(pead.corte_do_tercil(eventos, eventos["dia_zero"][29], 1 / 3))
    corte = pead.corte_do_tercil(eventos, eventos["dia_zero"][35], 1 / 3)
    assert corte == pytest.approx(np.quantile(np.arange(35.0), 2 / 3))
    um_ano_depois = eventos["dia_zero"][39] + pd.Timedelta(days=400)
    assert math.isnan(pead.corte_do_tercil(eventos, um_ano_depois, 1 / 3))


def test_sinais_sao_so_o_tercil_de_cima(dados, eventos):
    tabela, _ = eventos
    lista = pead.sinais(dados, P, tabela)
    assert lista
    for s in lista[:50]:
        dia = DATAS[
            pead.posicoes_do_evento(
                DATAS,
                tabela.set_index(["cnpj", "trimestre"]).loc[
                    (s.cnpj, s.trimestre), "dia_do_resultado"
                ],
                P,
            )[0]
        ]
        assert s.sue > pead.corte_do_tercil(tabela, dia, 1 / 3)
    escolhidos = len(lista) / len(tabela)
    assert 0.2 < escolhidos < 0.45


# --- a carteira -------------------------------------------------------------------------------------


def test_entra_na_abertura_de_d_mais_2_e_sai_60_pregoes_depois(dados, candidato):
    posicoes = candidato.posicoes
    normais = posicoes[posicoes["motivo"] == "60 pregões"]
    assert len(normais) > 50
    for linha in normais.head(30).itertuples():
        entrada, saida = pd.Timestamp(linha.entrada), pd.Timestamp(linha.saida)
        assert DATAS.get_loc(saida) - DATAS.get_loc(entrada) == P.pregoes_na_posicao
        assert linha.preco_de_entrada == pytest.approx(
            dados.abertura.loc[entrada, linha.ticker]
        )
        assert linha.preco_de_saida == pytest.approx(
            dados.abertura.loc[saida, linha.ticker]
        )


def test_cada_entrada_e_cerca_de_1_30_do_patrimonio(candidato):
    pesos = candidato.pesos
    primeiras = candidato.posicoes.head(10)
    for linha in primeiras.itertuples():
        peso = pesos.loc[pd.Timestamp(linha.entrada), linha.ticker]
        assert peso == pytest.approx(1 / P.posicoes, rel=0.15)
    assert (pesos.sum(axis=1) <= 1 + 1e-9).all()


def test_novo_evento_com_a_posicao_aberta_nao_muda_nada():
    p = pead.com(
        P, pregoes_na_posicao=200
    )  # a posição fica aberta além do próximo trimestre
    dados = dados_sinteticos(1)
    resultado = pead.simular(dados, p)
    assert resultado.contagem["sinais_ignorados"] > 0
    abertas_ao_mesmo_tempo = resultado.posicoes.groupby("ticker").apply(
        lambda g: (
            pd.to_datetime(g["entrada"]).iloc[1:].to_numpy()
            < pd.to_datetime(g["saida"]).iloc[:-1].to_numpy()
        ).any()
    )
    assert not abertas_ao_mesmo_tempo.any()


def test_deslistada_e_vendida_pelo_ultimo_preco(dados, candidato):
    linha = candidato.posicoes[candidato.posicoes["motivo"] == "60 pregões"].iloc[5]
    entrada = DATAS.get_loc(pd.Timestamp(linha.entrada))
    dia = DATAS[entrada + 10]
    resultado = pead.simular(deslistar(dados, linha.ticker, dia), P)
    vendida = resultado.posicoes[
        (resultado.posicoes["ticker"] == linha.ticker)
        & (resultado.posicoes["entrada"] == linha.entrada)
    ].iloc[0]
    assert vendida["motivo"] == "deslistada"
    assert vendida["preco_de_saida"] == pytest.approx(
        dados.fechamento.loc[dia, linha.ticker]
    )


def test_sem_sinais_o_caixa_rende_o_cdi(dados):
    resultado = pead.simular(
        replace(dados, documentos=None, fundamentos=dados.fundamentos.iloc[:0]), P
    )
    assert resultado.posicoes.empty
    assert resultado.retorno.iloc[1:].to_numpy() == pytest.approx(0.0004)


def test_otimista_entra_um_pregao_antes_com_os_mesmos_eventos(
    dados, eventos, candidato
):
    otimista = pead.simular(dados, pead.com(P, dia_zero_em_d=True), *eventos)
    a = pd.to_datetime(candidato.posicoes["entrada"]).head(20).to_numpy()
    b = pd.to_datetime(otimista.posicoes["entrada"]).head(20).to_numpy()
    assert [DATAS.get_loc(x) - DATAS.get_loc(y) for x, y in zip(a, b, strict=True)] == [
        1
    ] * 20


def test_custos_e_estresse_pioram_e_o_ir_e_pago(dados, eventos, candidato):
    sem = pead.simular(dados, pead.com(P, custos=pead.SEM_CUSTOS), *eventos)
    estresse = pead.simular(dados, pead.com(P, fator_de_impacto=3.0), *eventos)
    assert (
        sem.patrimonio.iloc[-1]
        > candidato.patrimonio.iloc[-1]
        > estresse.patrimonio.iloc[-1]
    )
    assert candidato.custos.sum() > 0
    assert candidato.imposto.sum() > 0


def test_cortar_o_futuro_nao_muda_o_passado(dados):
    assert pead.cortar_o_futuro_nao_muda_o_passado(dados, P, pd.Timestamp("2015-07-15"))


def test_cortar_tira_os_documentos_do_futuro(dados):
    cortado = pead.cortar(dados, pd.Timestamp("2014-12-31"))
    assert cortado.documentos is not None
    assert pd.to_datetime(cortado.documentos["publicado_em"]).max() <= pd.Timestamp(
        "2014-12-31"
    )


def test_reexecucao_identica(dados, candidato):
    de_novo = pead.simular(dados, P)
    assert pead.hash_do_resultado(de_novo) == pead.hash_do_resultado(candidato)


# --- o estudo dos eventos ---------------------------------------------------------------------------


def test_car_pelo_modelo_de_mercado_acha_o_salto_depois_do_evento():
    g = np.random.default_rng(3)
    n = 400
    mercado = g.normal(0, 0.01, n)
    acao = 0.0005 + 1.5 * mercado + g.normal(0, 0.0005, n)
    dia_zero = 300
    acao[dia_zero + 1 : dia_zero + 61] += 0.002
    car = pead.retornos_anormais(acao.reshape(-1, 1), mercado, 0, dia_zero)
    assert car == pytest.approx(60 * 0.002, abs=0.01)
    assert math.isnan(
        pead.retornos_anormais(acao.reshape(-1, 1), mercado, 0, 100)
    )  # sem 252 antes
    assert math.isnan(
        pead.retornos_anormais(acao.reshape(-1, 1), mercado, 0, 350)
    )  # sem os 60 depois


def test_estudo_resume_por_tipo_e_por_tercil(dados, eventos):
    estudo = pead.estudo_dos_eventos(dados, P, eventos[0])
    tipos = estudo["por_tipo"]
    assert set(tipos) == {
        "Dados Econômico-Financeiros · Press-release",
        "Fato Relevante",
    }
    for resumo in tipos.values():
        assert resumo["n"] > 100
        assert abs(resumo["media"]) < 0.05  # sem efeito nos dados sintéticos
    assert set(estudo["por_tercil_da_sue"]) == {"de cima", "do meio", "de baixo"}


def test_estudo_usa_so_a_primeira_versao_de_cada_documento(dados):
    docs = dados.documentos.assign(versao=1)
    reapresentados = docs[docs["tema"] == "outros"].assign(
        versao=2,
        tipo="Reapresentado",
        publicado_em=lambda d: d["publicado_em"] + pd.Timedelta(days=5),
    )
    estudo = pead.estudo_dos_eventos(
        replace(dados, documentos=pd.concat([docs, reapresentados])), P
    )
    assert not any("Reapresentado" in chave for chave in estudo["por_tipo"])


def test_estudo_sem_mercado_e_recusado(dados):
    with pytest.raises(ValueError, match="mercado"):
        pead.estudo_dos_eventos(replace(dados, ibovespa=None), P)


# --- parâmetros -------------------------------------------------------------------------------------


def test_especificacao_vai_para_o_registro_em_tipos_simples():
    spec = P.especificacao()
    json.dumps(spec)
    assert spec["versao"] == pead.VERSAO
    assert spec["trimestres_do_desvio"] == 8 and spec["posicoes"] == 30


@pytest.mark.parametrize(
    "mudanca",
    [
        {"trimestres_do_desvio": 1},
        {"fracao_de_cima": 0.0},
        {"fracao_de_cima": 1.0},
        {"pregoes_na_posicao": 0},
        {"posicoes": 0},
        {"capital_inicial": 0.0},
    ],
)
def test_parametros_invalidos_sao_recusados(mudanca):
    with pytest.raises(ValueError):
        pead.Parametros(**mudanca)
