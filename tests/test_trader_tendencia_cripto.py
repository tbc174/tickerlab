"""Tendência em cripto em reais, ficha P0-1 do pré-registro quant v0.1.

Conjunto de canais de Donchian (9 janelas), peso pela volatilidade alvo de 25%, BTC e ETH com
metade do capital cada, alavancagem ≤ 1, caixa a CDI, sinal no fechamento de D e execução no
fechamento de D+1, todo dia do ano (365).
"""

import io
import zipfile

import numpy as np
import pandas as pd
import pytest

from trader import criterio_quant
from trader.custos_br import CustosBR
from trader.estrategias import dados_tendencia_cripto as dados
from trader.estrategias import tendencia_cripto as tc

DIAS = pd.date_range("2018-01-01", periods=900, freq="D")
CDI = pd.Series(0.0004, index=DIAS)
SEM_CDI = pd.Series(0.0, index=DIAS)
VOLUMES = pd.DataFrame(1e9, index=DIAS, columns=list(tc.ATIVOS))
CAPITAL = 100_000.0
SEM_CUSTOS = tc.Parametros(custos=tc.SEM_CUSTOS, fator_de_impacto=0.0, com_cambio=False)


def _precos(semente=3, media=0.001, desvio=0.03):
    gerador = np.random.default_rng(semente)
    retornos = gerador.normal(media, desvio, (len(DIAS), len(tc.ATIVOS)))
    return pd.DataFrame(
        100 * np.cumprod(1 + retornos, axis=0), index=DIAS, columns=list(tc.ATIVOS)
    )


def _constantes(valor=100.0):
    return pd.DataFrame(valor, index=DIAS, columns=list(tc.ATIVOS))


# --- a regra ---------------------------------------------------------------------------------


def test_parametros_fixos_sao_os_da_ficha():
    assert tc.JANELAS == (5, 10, 20, 30, 60, 90, 150, 250, 360)
    assert tc.VOL_ALVO == 0.25 and tc.JANELA_DA_VOL == 90
    assert tc.FRACAO_POR_ATIVO == 0.5 and tc.ATIVOS == ("BTC", "ETH")
    assert tc.DIAS_POR_ANO == 365 and tc.AQUECIMENTO_EM_DIAS == 365
    assert criterio_quant.CANDIDATOS["P0-1"] == tc.CANDIDATO == "BTC e ETH 50/50"
    assert criterio_quant.ORCAMENTO_POR_FICHA["P0-1"] == 10
    p = tc.Parametros()
    assert p.janelas == tc.JANELAS and p.vol_alvo == tc.VOL_ALVO


def test_canal_entra_acima_da_maxima_e_sai_abaixo_do_meio():
    fechamento = pd.Series(
        [10.0] * 10 + [11.0] + [10.6] * 3 + [10.4] + [10.0] * 5,
        index=DIAS[:20],
    )
    estado = tc.estado_do_canal(fechamento, janela=5)
    assert estado.iloc[:5].isna().all()  # ainda não há canal
    assert estado.iloc[5:10].eq(0).all()  # fechamento igual à máxima não entra
    assert estado.iloc[10] == 1  # 11 passa a máxima 10
    assert estado.iloc[11:14].eq(1).all()  # 10,6 fica acima do meio (10,5)
    assert estado.iloc[14] == 0  # 10,4 cai abaixo do meio (10,5): zera
    assert estado.iloc[15:].eq(0).all()


def test_sinal_e_a_media_dos_nove_canais():
    subida = pd.Series(np.linspace(100, 400, 400), index=DIAS[:400])
    sinal = tc.sinal(subida)
    assert sinal.iloc[: max(tc.JANELAS)].isna().all()
    assert sinal.iloc[max(tc.JANELAS) :].eq(1.0).all()
    fechamento = _precos()["BTC"]
    estados = pd.concat([tc.estado_do_canal(fechamento, j) for j in tc.JANELAS], axis=1)
    esperado = estados.mean(axis=1, skipna=False)
    pd.testing.assert_series_equal(tc.sinal(fechamento), esperado, check_names=False)
    assert tc.sinal(fechamento).dropna().between(0, 1).all()


def test_peso_limita_a_exposicao_pela_volatilidade_alvo():
    gerador = np.random.default_rng(1)
    agitado = pd.Series(
        100 * np.cumprod(1 + gerador.normal(0.004, 0.05, 500)), index=DIAS[:500]
    )
    calmo = pd.Series(
        100 * np.cumprod(1 + gerador.normal(0.001, 0.002, 500)), index=DIAS[:500]
    )
    p = tc.Parametros()
    sigma = tc.volatilidade_anualizada(agitado, p.janela_da_vol)
    assert sigma.dropna().gt(p.vol_alvo).all()
    esperado = tc.sinal(agitado) * (p.vol_alvo / sigma)
    pd.testing.assert_series_equal(tc.peso(agitado, p), esperado, check_names=False)
    assert tc.peso(agitado, p).dropna().le(1.0).all()
    pd.testing.assert_series_equal(
        tc.peso(calmo, p).dropna(),
        tc.sinal(calmo).dropna().loc[tc.peso(calmo, p).dropna().index],
        check_names=False,
    )


def test_fracoes_alvo_metade_por_ativo_e_zero_no_aquecimento():
    fracoes = tc.fracoes_alvo(_precos(), tc.Parametros())
    assert list(fracoes.columns) == list(tc.ATIVOS)
    assert fracoes.iloc[: tc.AQUECIMENTO_EM_DIAS].eq(0).all().all()
    depois = fracoes.iloc[tc.AQUECIMENTO_EM_DIAS :]
    assert depois.le(tc.FRACAO_POR_ATIVO + 1e-12).all().all()
    assert depois.sum(axis=1).le(1.0 + 1e-12).all()  # alavancagem ≤ 1
    assert depois.gt(0).any().any()


# --- a simulação -------------------------------------------------------------------------------


def test_simulacao_comeca_depois_do_aquecimento_e_o_caixa_rende_cdi():
    resultado = tc.simular(_constantes(), CDI, VOLUMES, SEM_CUSTOS, CAPITAL)
    assert resultado.retorno.index[0] == DIAS[tc.AQUECIMENTO_EM_DIAS]
    # preço constante nunca passa a máxima: tudo em caixa, a CDI
    assert np.allclose(resultado.retorno, 0.0004)
    assert (resultado.exposicao == 0).all().all()
    assert resultado.patrimonio.iloc[0] == pytest.approx(CAPITAL * 1.0004)


def test_sinal_em_d_executa_no_fechamento_de_d_mais_1():
    precos = _constantes()
    d = tc.AQUECIMENTO_EM_DIAS + 10
    precos.loc[DIAS[d], "BTC"] = 110.0  # D: passa a máxima
    precos.loc[DIAS[d + 1], "BTC"] = 121.0  # D+1: +10%, executa no fechamento
    precos.loc[DIAS[d + 2] :, "BTC"] = 133.1  # D+2: +10%, primeiro dia rendendo
    resultado = tc.simular(precos, SEM_CDI, VOLUMES, SEM_CUSTOS, CAPITAL)
    retorno = resultado.retorno
    assert retorno[DIAS[d]] == 0 and retorno[DIAS[d + 1]] == 0
    assert retorno[DIAS[d + 2]] > 0
    assert resultado.exposicao.loc[DIAS[d], "BTC"] == 0
    assert resultado.exposicao.loc[DIAS[d + 1], "BTC"] > 0
    peso = tc.fracoes_alvo(precos, SEM_CUSTOS).loc[DIAS[d], "BTC"]
    assert retorno[DIAS[d + 2]] == pytest.approx(peso * 0.10)


def test_custos_por_lado_corretora_cambio_e_impacto():
    precos = _constantes()
    d = tc.AQUECIMENTO_EM_DIAS + 10
    precos.loc[DIAS[d] :, "ETH"] = 110.0
    custos = CustosBR(corretagem_por_ordem=0.0)
    completo = tc.simular(
        precos, SEM_CDI, VOLUMES, tc.Parametros(custos=custos), CAPITAL
    )
    so_taxa = tc.simular(
        precos,
        SEM_CDI,
        VOLUMES,
        tc.Parametros(custos=custos, fator_de_impacto=0.0, com_cambio=False),
        CAPITAL,
    )
    dia = DIAS[d + 1]
    valor = tc.fracoes_alvo(precos, SEM_CUSTOS).loc[DIAS[d], "ETH"] * CAPITAL
    assert so_taxa.custos[dia] == pytest.approx(valor * custos.taxa_cripto_por_lado)
    assert so_taxa.cambio[dia] == 0
    assert completo.cambio[dia] == pytest.approx(
        valor * (custos.iof_cambio + custos.spread_cambio)
    )
    assert completo.custos[dia] > so_taxa.custos[dia] + completo.cambio[dia]  # impacto
    assert (completo.custos.drop(dia) == 0).all()
    assert completo.retorno[dia] == pytest.approx(-completo.custos[dia] / CAPITAL)


def _precos_que_compram_e_vendem(ganho: float):
    """Entra em D (passa a máxima), sobe `ganho` e cai abaixo do meio do canal em D+10."""
    precos = _constantes()
    d = tc.AQUECIMENTO_EM_DIAS + 10
    precos.loc[DIAS[d] :, "BTC"] = 110.0
    precos.loc[DIAS[d + 2] :, "BTC"] = 110.0 * (1 + ganho)
    precos.loc[DIAS[d + 10] :, "BTC"] = 50.0
    return precos, d


def test_ir_de_15_por_cento_so_quando_as_vendas_do_mes_passam_de_35_mil():
    custos = CustosBR(corretagem_por_ordem=0.0, taxa_cripto_por_lado=0.0)
    p = tc.Parametros(custos=custos, fator_de_impacto=0.0, com_cambio=False)
    precos, d = _precos_que_compram_e_vendem(ganho=0.5)
    pequeno = tc.simular(precos, SEM_CDI, VOLUMES, p, 20_000.0)
    assert pequeno.vendas.sum() > 0 and pequeno.vendas.sum() <= 35_000
    assert pequeno.imposto.sum() == 0 and pequeno.meses_acima_da_isencao() == 0
    grande = tc.simular(precos, SEM_CDI, VOLUMES, p, 1_000_000.0)
    assert grande.meses_acima_da_isencao() == 1
    ganho = float(grande.ir["resultado"].sum())
    assert ganho > 0
    assert grande.imposto.sum() == pytest.approx(0.15 * ganho)
    pago_em = grande.imposto[grande.imposto > 0].index
    assert len(pago_em) == 1
    mes_da_venda = DIAS[d + 10].to_period("M")
    assert pago_em[0].to_period("M") == mes_da_venda + 1
    assert pago_em[0] == pago_em[0] + pd.offsets.MonthEnd(0)  # último dia do mês


def test_prejuizo_nao_paga_imposto():
    p = tc.Parametros(custos=CustosBR(corretagem_por_ordem=0.0), fator_de_impacto=0.0)
    precos, _ = _precos_que_compram_e_vendem(ganho=-0.3)
    resultado = tc.simular(precos, SEM_CDI, VOLUMES, p, 1_000_000.0)
    assert resultado.vendas.sum() > 35_000
    assert resultado.imposto.sum() == 0


def test_cortar_o_futuro_nao_muda_o_passado_e_reexecucao_identica():
    precos = _precos()
    p = tc.Parametros()
    corte = DIAS[700]
    assert tc.cortar_o_futuro_nao_muda_o_passado(
        precos, CDI, VOLUMES, p, corte, CAPITAL
    )
    um = tc.simular(precos, CDI, VOLUMES, p, CAPITAL)
    outro = tc.simular(precos, CDI, VOLUMES, p, CAPITAL)
    assert tc.hash_do_resultado(um) == tc.hash_do_resultado(outro)


def test_olhar_o_futuro_infla_o_sharpe():
    precos = _precos()
    honesto = tc.simular(precos, CDI, VOLUMES, tc.Parametros(), CAPITAL)
    futuro = tc.simular(
        precos, CDI, VOLUMES, tc.Parametros(olhar_o_futuro=True), CAPITAL
    )
    assert tc.sharpe_do_excesso(futuro.retorno, CDI) > tc.sharpe_do_excesso(
        honesto.retorno, CDI
    )


def test_indice_tem_de_ser_de_dias_corridos_e_o_cdi_completo():
    uteis = pd.bdate_range("2018-01-01", periods=900)
    precos = _precos().set_axis(uteis)
    with pytest.raises(ValueError, match="dias corridos"):
        tc.simular(precos, CDI.set_axis(uteis), VOLUMES.set_axis(uteis), SEM_CUSTOS)
    with pytest.raises(ValueError, match="CDI"):
        tc.simular(_precos(), CDI.iloc[:-5], VOLUMES, SEM_CUSTOS)
    with pytest.raises(ValueError, match="ativos"):
        tc.simular(_precos()[["BTC"]], CDI, VOLUMES, SEM_CUSTOS)


def test_comprar_e_segurar_paga_a_compra_uma_vez_e_segue_o_preco():
    precos = _precos()
    inicio = DIAS[tc.AQUECIMENTO_EM_DIAS]
    regua = tc.comprar_e_segurar(
        precos["BTC"], VOLUMES["BTC"], tc.Parametros(), CAPITAL
    )
    assert regua.index[0] == inicio
    assert regua.iloc[0] < 0  # o dia da compra paga corretora, câmbio e impacto
    assert np.allclose(regua.iloc[1:], precos["BTC"].pct_change().loc[inicio:].iloc[1:])
    sem_custo = tc.comprar_e_segurar(precos["BTC"], VOLUMES["BTC"], SEM_CUSTOS, CAPITAL)
    assert sem_custo.iloc[0] == 0


def test_p_valor_do_acaso_vem_entre_0_e_1():
    precos = _precos()
    resultado = tc.simular(precos, CDI, VOLUMES, tc.Parametros(), CAPITAL)
    acaso = tc.p_valor_do_acaso(
        resultado.exposicao, precos.pct_change().fillna(0.0), CDI, 0.001, sorteios=50
    )
    assert 0 < acaso["p_valor"] <= 1
    assert {"sharpe_real", "percentil_95"} <= set(acaso)


def test_estresse_dobra_corretora_cambio_e_impacto():
    base = tc.Parametros()
    estresse = base.em_estresse(2.0)
    assert estresse.custos.taxa_cripto_por_lado == 2 * base.custos.taxa_cripto_por_lado
    assert estresse.custos.spread_cambio == 2 * base.custos.spread_cambio
    assert estresse.custos.ir_cripto == base.custos.ir_cripto  # não mexe em lei
    assert estresse.fator_de_impacto == 2.0
    precos = _precos()
    normal = tc.simular(precos, CDI, VOLUMES, base, CAPITAL)
    dobrado = tc.simular(precos, CDI, VOLUMES, estresse, CAPITAL)
    assert dobrado.custos.sum() > 1.5 * normal.custos.sum()


def test_especificacao_e_o_freio_em_tipos_simples():
    spec = tc.Parametros().especificacao()
    assert spec["janelas"] == list(tc.JANELAS) and spec["vol_alvo"] == 0.25
    assert spec["execucao"] == "fechamento de D+1" and spec["dias_por_ano"] == 365
    assert isinstance(spec["custos"], dict) and spec["com_cambio"] is True
    vizinho = tc.com(tc.Parametros(), vol_alvo=0.30)
    assert vizinho.vol_alvo == 0.30 and vizinho.janelas == tc.JANELAS
    assert tc.escalar_janelas(tc.JANELAS, 1.2) == (
        6,
        12,
        24,
        36,
        72,
        108,
        180,
        300,
        432,
    )


def test_resumo_traz_giro_exposicao_e_meses_do_ir():
    resultado = tc.simular(_precos(), CDI, VOLUMES, tc.Parametros(), CAPITAL)
    assert resultado.giro > 0
    assert 0 <= resultado.exposicao_media() <= 1
    assert resultado.meses_acima_da_isencao() >= 0
    assert list(resultado.ir.columns) == [
        "vendas",
        "resultado",
        "isento",
        "prejuizo_compensado",
        "base",
        "imposto",
        "prejuizo_acumulado",
    ]


# --- os dados --------------------------------------------------------------------------------------


def _zip_de_klines(
    linhas: list[list[float]], nome: str = "BTCUSDT-1d-2017-08.csv"
) -> bytes:
    conteudo = "\n".join(",".join(str(v) for v in linha) for linha in linhas)
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr(nome, conteudo)
    return saida.getvalue()


def _kline(dia: str, fechamento: float, quote_volume: float) -> list[float]:
    abertura = int(pd.Timestamp(dia, tz="UTC").timestamp() * 1000)
    return [
        abertura,
        1,
        2,
        0.5,
        fechamento,
        10,
        abertura + 86_399_999,
        quote_volume,
        5,
        1,
        1,
        0,
    ]


def test_ler_kline_zip_da_o_fechamento_e_o_volume_em_usdt_por_dia():
    tabela = dados.ler_kline_zip(
        _zip_de_klines(
            [
                _kline("2017-08-17", 4285.08, 3454770.05),
                _kline("2017-08-18", 4108.37, 5086958.3),
            ]
        )
    )
    assert list(tabela.columns) == ["fechamento", "volume"]
    assert list(tabela.index) == [
        pd.Timestamp("2017-08-17"),
        pd.Timestamp("2017-08-18"),
    ]
    assert (
        tabela["fechamento"].iloc[1] == 4108.37
        and tabela["volume"].iloc[0] == 3454770.05
    )


def test_baixar_par_grava_um_zip_por_mes_e_carregar_junta(tmp_path):
    pedidos = []

    def baixar(url: str) -> bytes:
        pedidos.append(url)
        mes = url[-11:-4]
        return _zip_de_klines(
            [_kline(f"{mes}-01", 100.0, 1.0), _kline(f"{mes}-02", 101.0, 2.0)]
        )

    gravados = dados.baixar_par(
        "BTCUSDT", pd.period_range("2017-08", "2017-10", freq="M"), tmp_path, baixar
    )
    assert gravados == 3 and len(pedidos) == 3
    assert pedidos[0].endswith("/BTCUSDT/1d/BTCUSDT-1d-2017-08.zip")
    assert (
        dados.baixar_par(
            "BTCUSDT", pd.period_range("2017-08", "2017-10", freq="M"), tmp_path, baixar
        )
        == 0
    )
    tabela = dados.carregar_par("BTCUSDT", tmp_path)
    assert len(tabela) == 6 and tabela.index.is_monotonic_increasing
    with pytest.raises(FileNotFoundError):
        dados.carregar_par("ETHUSDT", tmp_path)


def test_dolar_da_vespera_usa_a_ultima_cotacao_conhecida_antes_do_dia():
    uteis = pd.bdate_range("2023-01-02", "2023-01-13")
    dolar = pd.Series(np.arange(1.0, 1.0 + len(uteis)), index=uteis)
    corridos = pd.date_range("2023-01-02", "2023-01-15", freq="D")
    vespera = dados.dolar_da_vespera(dolar, corridos)
    assert np.isnan(vespera[pd.Timestamp("2023-01-02")])  # nada antes
    assert vespera[pd.Timestamp("2023-01-03")] == 1.0  # a de segunda
    assert vespera[pd.Timestamp("2023-01-07")] == 5.0  # sábado: a de sexta
    assert vespera[pd.Timestamp("2023-01-09")] == 5.0  # segunda: ainda a de sexta
    assert vespera[pd.Timestamp("2023-01-10")] == 6.0  # terça: a de segunda


def test_montar_precos_em_reais_no_calendario_corrido():
    dias = pd.date_range("2020-01-01", "2020-01-10", freq="D")
    btc = pd.DataFrame({"fechamento": 100.0, "volume": 10.0}, index=dias)
    eth = pd.DataFrame({"fechamento": 10.0, "volume": 1.0}, index=dias.drop(dias[4]))
    dolar = pd.Series(4.0, index=pd.bdate_range("2019-12-30", "2020-01-10"))
    precos, volumes = dados.montar_precos({"BTC": btc, "ETH": eth}, dolar)
    assert list(precos.columns) == ["BTC", "ETH"] and precos.index.equals(dias)
    assert precos["BTC"].eq(400.0).all()
    assert precos.loc[dias[4], "ETH"] == 40.0  # dia sem candle repete o anterior
    assert volumes.loc[dias[4], "ETH"] == 0.0  # e não negocia
    assert volumes["BTC"].eq(40.0).all()
    with pytest.raises(ValueError, match="dólar"):
        dados.montar_precos({"BTC": btc, "ETH": eth}, dolar.iloc[5:])
