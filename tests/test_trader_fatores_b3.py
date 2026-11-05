"""Ficha F-B3: universo por liquidez, balanço ponto no tempo, notas, carteira e sobrevivência."""

import json

import numpy as np
import pandas as pd
import pytest

from tests.ajudantes_f_b3 import (
    CNPJS,
    DATAS,
    DESLISTADA,
    DIA_DA_DESLISTAGEM,
    LIQUIDO,
    dados_sinteticos,
    fundamentos,
    variar_balancos_por_ano,
)
from trader.custos_br import CustosBR
from trader.estrategias import fatores_b3 as fb

SEM_ATRITO = fb.Parametros(custos=fb.SEM_CUSTOS, fator_de_impacto=0.0)
D = pd.Timestamp("2018-03-01")  # primeiro pregão de março de 2018


# --- ponto no tempo -----------------------------------------------------------------------------------


def test_vigentes_em_so_usa_o_que_foi_divulgado_antes_do_dia():
    base = fundamentos(cnpjs=["x"])
    dfp_2017 = base[(base["fim"] == "2017-12-31") & (base["conta"] == "3.05")]
    divulgado = dfp_2017["divulgado_em"].iloc[0]  # 31/03/2018
    no_dia = fb.vigentes_em(base, divulgado)
    no_dia_seguinte = fb.vigentes_em(base, divulgado + pd.Timedelta(days=1))
    assert "2017-12-31" not in no_dia["fim"].astype(str).to_numpy()
    assert "2017-12-31" in no_dia_seguinte["fim"].astype(str).to_numpy()


def test_vigentes_em_respeita_o_ate_da_reapresentacao():
    base = fundamentos(cnpjs=["x"]).copy()
    linha = (base["fim"] == "2016-12-31") & (base["conta"] == "3.05")
    base.loc[linha, "ate"] = pd.Timestamp("2017-06-01")
    vigente = fb.vigentes_em(base, pd.Timestamp("2017-09-01"))
    assert not ((vigente["fim"] == "2016-12-31") & (vigente["conta"] == "3.05")).any()


def test_ultimos_12_meses_soma_dfp_e_acumulado_menos_o_acumulado_do_ano_anterior():
    linhas = [
        ("x", "DRE", "3.05", "2017-01-01", "2017-12-31", 100.0),
        ("x", "DRE", "3.05", "2017-01-01", "2017-06-30", 40.0),
        ("x", "DRE", "3.05", "2018-01-01", "2018-06-30", 70.0),
        (
            "x",
            "DRE",
            "3.05",
            "2018-04-01",
            "2018-06-30",
            35.0,
        ),  # trimestre isolado não entra
    ]
    base = pd.DataFrame(
        linhas, columns=["cnpj", "demonstracao", "conta", "inicio", "fim", "valor"]
    )
    base["inicio"] = pd.to_datetime(base["inicio"])
    base["fim"] = pd.to_datetime(base["fim"])
    ttm = fb.ultimos_12_meses(base, "3.05")
    assert ttm["x"] == pytest.approx(100.0 + 70.0 - 40.0)


def test_ultimos_12_meses_sem_o_acumulado_do_ano_anterior_fica_vazio():
    linhas = [
        ("x", "DRE", "3.05", "2017-01-01", "2017-12-31", 100.0),
        ("x", "DRE", "3.05", "2018-01-01", "2018-06-30", 70.0),
        ("y", "DRE", "3.05", "2017-01-01", "2017-12-31", 10.0),
    ]
    base = pd.DataFrame(
        linhas, columns=["cnpj", "demonstracao", "conta", "inicio", "fim", "valor"]
    )
    base["inicio"] = pd.to_datetime(base["inicio"])
    base["fim"] = pd.to_datetime(base["fim"])
    ttm = fb.ultimos_12_meses(base, "3.05")
    assert np.isnan(ttm["x"])
    assert ttm["y"] == 10.0  # só a DFP: os 12 meses são o próprio ano


# --- universo (seção 8) ---------------------------------------------------------------------------------


def test_universo_exige_liquidez_classe_de_acao_e_um_ano_de_pregao():
    dados = dados_sinteticos()
    dados.volume["AAA3"] = 1e6  # abaixo do piso
    dados.cadastro.loc["BBB3", "classe"] = "outro"  # BDR, ETF, FII
    dados.cadastro.loc["CCC3", "inicio_negociacao"] = D - pd.Timedelta(days=200)
    universo = fb.universo_em(D, dados, fb.Parametros())
    assert {"AAA3", "BBB3", "CCC3"}.isdisjoint(universo)
    assert "DDD3" in universo


def test_universo_mede_a_liquidez_nos_60_pregoes_anteriores_sem_o_proprio_dia():
    dados = dados_sinteticos()
    posicao = DATAS.get_loc(D)
    dados.volume.iloc[posicao - 60 : posicao, dados.volume.columns.get_loc("AAA3")] = (
        1e6
    )
    dados.volume.loc[D, "AAA3"] = 1e12  # o próprio dia não conta
    assert "AAA3" not in fb.universo_em(D, dados, fb.Parametros())


def test_universo_uma_classe_por_empresa_a_mais_liquida():
    dados = dados_sinteticos()
    dados.cadastro.loc["BBB3", "cnpj"] = CNPJS["AAA3"]
    dados.cadastro.loc["BBB3", "classe"] = "PN"
    dados.volume["BBB3"] = 3 * LIQUIDO
    universo = fb.universo_em(D, dados, fb.Parametros())
    assert "BBB3" in universo and "AAA3" not in universo


def test_universo_so_tem_acoes_que_existiam_na_data():
    dados = dados_sinteticos()
    depois = pd.Timestamp("2019-03-01")
    assert DESLISTADA in fb.universo_em(D, dados, fb.Parametros())
    assert DESLISTADA not in fb.universo_em(depois, dados, fb.Parametros())


def test_universo_sem_balanco_nos_ultimos_12_meses_fica_fora():
    dados = dados_sinteticos()
    cnpj = CNPJS["AAA3"]
    e_dela = dados.fundamentos["cnpj"] == cnpj
    recente = dados.fundamentos["divulgado_em"] >= pd.Timestamp("2016-01-01")
    dados.fundamentos = dados.fundamentos[~(e_dela & recente)]
    assert "AAA3" not in fb.universo_em(D, dados, fb.Parametros())
    assert "AAA3" in fb.universo_em(pd.Timestamp("2016-03-01"), dados, fb.Parametros())


def test_universo_em_recuperacao_judicial_fica_fora_so_enquanto_dura():
    dados = dados_sinteticos()
    dados.recuperacao_judicial = pd.DataFrame(
        {
            "cnpj": [CNPJS["AAA3"]],
            "inicio": [pd.Timestamp("2018-01-10")],
            "fim": [pd.Timestamp("2018-12-01")],
        }
    )
    assert "AAA3" not in fb.universo_em(D, dados, fb.Parametros())
    assert "AAA3" in fb.universo_em(pd.Timestamp("2019-03-01"), dados, fb.Parametros())


def test_sem_deslistadas_so_mantem_quem_existe_no_fim_dosdados_sinteticos():
    dados = dados_sinteticos()
    com = fb.universo_em(D, dados, fb.Parametros(com_deslistadas=True))
    sem = fb.universo_em(D, dados, fb.Parametros(com_deslistadas=False))
    assert DESLISTADA in com and DESLISTADA not in sem


# --- fatores e notas ---------------------------------------------------------------------------------


def test_valor_e_ebit_sobre_o_valor_da_firma_e_qualidade_e_lucro_sobre_o_patrimonio():
    dados = dados_sinteticos()
    fatores = fb.fatores_em(D, dados, ["AAA3"])
    preco = dados.fechamento.loc[D, "AAA3"]
    valor_da_firma = 1e7 * preco + 1e8 - 2e7
    assert fatores.loc["AAA3", "valor"] == pytest.approx(1e8 / valor_da_firma)
    assert fatores.loc["AAA3", "qualidade"] == pytest.approx(6e7 / 5e8)


def test_momento_pula_o_ultimo_mes_e_baixa_vol_e_menos_o_desvio():
    dados = dados_sinteticos()
    fatores = fb.fatores_em(D, dados, ["AAA3"])
    serie = dados.fechamento["AAA3"]
    posicao = DATAS.get_loc(D)
    esperado = (
        serie.iloc[posicao - fb.PULAR_NO_MOMENTO]
        / serie.iloc[posicao - fb.JANELA_DO_MOMENTO]
        - 1
    )
    assert fatores.loc["AAA3", "momento"] == pytest.approx(esperado)
    retornos = (
        serie.iloc[posicao - fb.JANELA_DA_VOL : posicao + 1].pct_change().dropna()
    )
    assert fatores.loc["AAA3", "baixa_vol"] == pytest.approx(-retornos.std())


def test_balanco_divulgado_no_dia_nao_entra_no_fator_do_dia():
    dados = dados_sinteticos()
    dia = pd.Timestamp("2018-04-02")  # primeiro pregão depois do DFP de 2017 (31/03)
    vespera = pd.Timestamp("2018-03-29")
    cnpj = CNPJS["AAA3"]
    e_2017 = (dados.fundamentos["cnpj"] == cnpj) & (
        dados.fundamentos["fim"] == "2017-12-31"
    )
    dados.fundamentos.loc[e_2017 & (dados.fundamentos["conta"] == "3.05"), "valor"] = (
        5e8
    )
    dados.fundamentos.loc[e_2017, "divulgado_em"] = dia
    no_dia = fb.fatores_em(dia, dados, ["AAA3"])
    na_vespera = fb.fatores_em(vespera, dados, ["AAA3"])
    assert no_dia.loc["AAA3", "valor"] == pytest.approx(
        na_vespera.loc["AAA3", "valor"]
        * dados.fechamento.loc[vespera, "AAA3"]
        / dados.fechamento.loc[dia, "AAA3"],
        rel=0.2,
    )  # mesmo EBIT de 2016: só o preço mudou
    seguinte = fb.fatores_em(pd.Timestamp("2018-04-03"), dados, ["AAA3"])
    assert seguinte.loc["AAA3", "valor"] > 3 * no_dia.loc["AAA3", "valor"]


def test_notas_sao_a_media_dos_escores_z_com_pelo_menos_tres_fatores():
    fatores = pd.DataFrame(
        {
            "valor": [0.1, 0.2, 0.3, np.nan],
            "qualidade": [0.1, 0.1, 0.4, 0.2],
            "momento": [0.0, 0.5, 1.0, np.nan],
            "baixa_vol": [-0.01, -0.02, -0.03, -0.02],
        },
        index=["a", "b", "c", "d"],
    )
    notas = fb.notas(fatores)
    z = (fatores - fatores.mean()) / fatores.std()
    assert notas["a"] == pytest.approx(z.loc["a"].mean())
    assert np.isnan(notas["d"])  # só 2 fatores


def test_alvo_compra_o_quintil_melhor_em_pesos_iguais():
    notas = pd.Series(np.arange(10, dtype=float), index=[f"t{i}" for i in range(10)])
    alvo = fb.carteira_alvo(notas, quintil=0.2)
    assert set(alvo.index) == {"t8", "t9"}
    assert alvo.sum() == pytest.approx(1.0) and alvo.nunique() == 1


# --- simulação --------------------------------------------------------------------------------------


def test_simular_decide_no_primeiro_pregao_do_mes_e_executa_na_abertura_seguinte():
    dados = dados_sinteticos()
    resultado = fb.simular(dados, SEM_ATRITO)
    decisoes = pd.DatetimeIndex(resultado.alvos.keys())
    primeiros = pd.Series(DATAS.to_period("M"), index=DATAS).groupby(level=0).head(1)
    assert decisoes.isin(primeiros.index).all()
    primeira = decisoes[0]
    seguinte = DATAS[DATAS.get_loc(primeira) + 1]
    assert resultado.negociado.loc[:primeira].abs().sum().sum() == 0
    assert resultado.negociado.loc[seguinte].abs().sum() > 0
    comprados = resultado.negociado.loc[seguinte]
    comprados = comprados[comprados > 0]
    quantidades = comprados / dados.abertura.loc[seguinte, comprados.index]
    assert np.allclose(quantidades, np.round(quantidades))  # ações inteiras


def test_antes_da_primeira_decisao_o_caixa_rende_o_cdi():
    dados = dados_sinteticos(cdi_diario=0.001)
    resultado = fb.simular(dados, SEM_ATRITO)
    primeira = next(iter(resultado.alvos))
    ate = DATAS.get_loc(primeira)
    assert np.allclose(resultado.retorno.iloc[1 : ate + 1], 0.001)


def test_simular_vende_a_deslistada_no_ultimo_preco_e_zera_o_peso():
    dados = dados_sinteticos()
    e_dela = (dados.fundamentos["cnpj"] == CNPJS[DESLISTADA]) & (
        dados.fundamentos["demonstracao"] == "DRE"
    )
    dados.fundamentos.loc[e_dela, "valor"] *= 3  # EBIT e lucro 3x: entra no quintil
    resultado = fb.simular(dados, SEM_ATRITO)
    antes = DATAS[DATAS.get_loc(DIA_DA_DESLISTAGEM)]
    depois = DATAS[DATAS.get_loc(DIA_DA_DESLISTAGEM) + 1]
    assert resultado.pesos.loc[antes, DESLISTADA] > 0
    assert resultado.pesos.loc[depois:, DESLISTADA].eq(0).all()
    assert resultado.negociado.loc[depois, DESLISTADA] < 0
    assert np.isfinite(resultado.patrimonio).all()


def test_pesos_somam_no_maximo_um_e_nao_ha_caixa_negativo():
    resultado = fb.simular(dados_sinteticos(), fb.Parametros())
    assert (resultado.pesos.sum(axis=1) <= 1 + 1e-9).all()
    assert (resultado.patrimonio > 0).all()
    assert resultado.custos.sum() > 0


def test_banda_evita_negociar_quando_a_carteira_nao_mudou():
    dados = dados_sinteticos()
    for i, cnpj in enumerate(CNPJS.values()):  # alvo quase fixo: só a banda muda o giro
        e_dela = (dados.fundamentos["cnpj"] == cnpj) & (
            dados.fundamentos["demonstracao"] == "DRE"
        )
        dados.fundamentos.loc[e_dela, "valor"] *= 1 + i
    larga = fb.simular(dados, fb.com(SEM_ATRITO, banda=10.0))
    estreita = fb.simular(dados, fb.com(SEM_ATRITO, banda=0.0))
    assert larga.giro < estreita.giro


def test_isencao_de_20_mil_zera_o_imposto_da_carteira_pequena():
    dados = dados_sinteticos()
    pequena = fb.simular(
        dados, fb.com(fb.Parametros(fator_de_impacto=0.0), capital_inicial=10_000.0)
    )
    grande = fb.simular(
        dados, fb.com(fb.Parametros(fator_de_impacto=0.0), capital_inicial=2_000_000.0)
    )
    assert pequena.imposto.sum() == 0
    assert grande.imposto.sum() > 0


def test_olhar_o_futuro_usa_a_data_do_balanco_e_muda_a_carteira():
    dados = variar_balancos_por_ano(dados_sinteticos())
    normal = fb.simular(dados, SEM_ATRITO)
    futuro = fb.simular(dados, fb.com(SEM_ATRITO, olhar_o_futuro=True))
    assert fb.hash_do_resultado(normal) != fb.hash_do_resultado(futuro)


def test_cortar_o_futuro_nao_muda_o_passado():
    assert fb.cortar_o_futuro_nao_muda_o_passado(
        dados_sinteticos(), fb.Parametros(), pd.Timestamp("2019-06-03")
    )


def test_reexecucao_e_identica():
    dados = dados_sinteticos()
    assert fb.hash_do_resultado(
        fb.simular(dados, fb.Parametros())
    ) == fb.hash_do_resultado(fb.simular(dados, fb.Parametros()))


def test_estresse_piora_o_resultado():
    dados = dados_sinteticos()
    base = fb.simular(dados, fb.Parametros())
    estresse = fb.simular(
        dados,
        fb.com(
            fb.Parametros(), custos=CustosBR().em_estresse(2.0), fator_de_impacto=2.0
        ),
    )
    assert estresse.patrimonio.iloc[-1] < base.patrimonio.iloc[-1]


# --- sobrevivência e registro -------------------------------------------------------------------------


def test_conferencia_de_sobrevivencia_avisa_quando_nao_ha_deslistadas():
    com = fb.conferir_sobrevivencia(dados_sinteticos(com_deslistada=True))
    sem = fb.conferir_sobrevivencia(dados_sinteticos(com_deslistada=False))
    assert not com.vies and com.deslistadas == 1
    assert sem.vies and "sobrevivência" in sem.aviso and "dinheiro" in sem.aviso


def test_especificacao_vai_para_o_registro_em_tipos_simples():
    spec = fb.Parametros().especificacao()
    json.dumps(spec)
    assert spec["versao"] == fb.VERSAO and spec["quintil"] == fb.QUINTIL
    assert spec["custos"]["ir_swing"] == CustosBR().ir_swing


def test_parametros_invalidos_sao_recusados():
    with pytest.raises(ValueError):
        fb.Parametros(quintil=0.0)
    with pytest.raises(ValueError):
        fb.Parametros(banda=-0.1)
