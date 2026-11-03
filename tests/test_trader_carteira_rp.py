"""P0-3: esquemas de peso, motor da carteira (decisão em D, execução em D+1), custos, IR e aporte."""

import numpy as np
import pandas as pd
import pytest

from trader.custos_br import CustosBR
from trader.estrategias import carteira_rp as rp

ATIVOS = list(rp.ATIVOS_DE_RISCO)
DATAS = pd.bdate_range("2015-01-02", "2020-12-30")
VOLUMES = pd.Series(1e8, index=ATIVOS)
CDI_ZERO = pd.Series(0.0, index=DATAS)
SEM_ATRITO = rp.Parametros(custos=rp.SEM_CUSTOS, fator_de_impacto=0.0)


def _precos(semente=0, media=0.0003, vols=(0.004, 0.012, 0.009, 0.010), datas=DATAS):
    gerador = np.random.default_rng(semente)
    retornos = gerador.normal(media, vols, size=(len(datas), len(vols)))
    return pd.DataFrame(
        100 * np.cumprod(1 + retornos, axis=0), index=datas, columns=ATIVOS
    )


def _precos_com_regimes(semente=1, datas=DATAS):
    """A volatilidade troca de ativo todo mês: quem olha o mês seguinte escolhe sempre o calmo.

    O regime troca no 2º pregão do mês, porque a carteira decidida no último pregão do mês só
    começa a render no fechamento seguinte (decide em D, executa em D+1, rende de D+2).
    """
    gerador = np.random.default_rng(semente)
    mes_do_pregao_anterior = pd.Series(datas.month).shift(1).bfill().to_numpy()
    mes_par = mes_do_pregao_anterior % 2 == 0
    vol_a = np.where(mes_par, 0.04, 0.003)
    vol_b = np.where(mes_par, 0.003, 0.04)
    vols = np.column_stack(
        [vol_a, vol_b, np.full(len(datas), 0.01), np.full(len(datas), 0.01)]
    )
    retornos = gerador.normal(0.0004, vols)
    return pd.DataFrame(
        100 * np.cumprod(1 + retornos, axis=0), index=datas, columns=ATIVOS
    )


def _cdi(taxa_diaria=0.0004, datas=DATAS):
    return pd.Series(taxa_diaria, index=datas)


# --- Esquemas de peso --------------------------------------------------------------------


def test_inverso_da_volatilidade_pesa_pelo_inverso_do_desvio():
    retornos = _precos().pct_change().dropna()
    pesos = rp.pesos_inverso_da_volatilidade(retornos)
    esperado = 1 / retornos.std()
    esperado /= esperado.sum()
    assert pesos.sum() == pytest.approx(1.0)
    pd.testing.assert_series_equal(pesos, esperado, check_names=False)


def test_risk_parity_iguala_as_contribuicoes_ao_risco():
    retornos = _precos().pct_change().dropna()
    retornos["OURO"] = 0.5 * retornos["OURO"] + 0.5 * retornos["BOVA11"]  # correlação
    pesos = rp.pesos_risk_parity(retornos)
    contribuicoes = rp.contribuicoes_ao_risco(pesos, retornos.cov())
    assert pesos.sum() == pytest.approx(1.0)
    assert (pesos > 0).all()
    assert contribuicoes.to_numpy() == pytest.approx(0.25, abs=1e-6)


def test_minima_variancia_respeita_o_teto_e_tem_a_menor_variancia():
    retornos = (
        _precos().pct_change().dropna()
    )  # o NTNB tem a menor vol: sem teto levaria quase tudo
    pesos = rp.pesos_minima_variancia(retornos, teto=0.40)
    cov = retornos.cov()
    assert pesos.sum() == pytest.approx(1.0)
    assert (pesos >= -1e-12).all() and (pesos <= 0.40 + 1e-9).all()
    assert pesos["NTNB"] == pytest.approx(0.40, abs=1e-6)
    variancia = float(pesos @ cov @ pesos)
    iguais = pd.Series(0.25, index=ATIVOS)
    assert variancia < float(iguais @ cov @ iguais)
    sem_teto = rp.pesos_minima_variancia(retornos, teto=1.0)
    assert sem_teto["NTNB"] > 0.40
    assert float(sem_teto @ cov @ sem_teto) <= variancia + 1e-12


def test_teto_impossivel_e_esquema_desconhecido_sao_recusados():
    retornos = _precos().pct_change().dropna()
    with pytest.raises(ValueError, match="teto"):
        rp.pesos_minima_variancia(retornos, teto=0.2)
    with pytest.raises(ValueError, match="esquema"):
        rp.calcular_pesos("momentum", retornos)


def test_esquema_fixo_devolve_os_pesos_dados_e_o_resto_fica_em_caixa():
    retornos = _precos().pct_change().dropna()
    pesos = rp.calcular_pesos("fixo", retornos, pesos_fixos={"BOVA11": 0.6})
    assert pesos["BOVA11"] == 0.6 and pesos.drop("BOVA11").eq(0).all()


def test_fora_da_banda_compara_com_20_por_cento_do_alvo():
    alvo = pd.Series({"NTNB": 0.5, "BOVA11": 0.25, "OURO": 0.25, "SP500": 0.0})
    dentro = pd.Series({"NTNB": 0.45, "BOVA11": 0.29, "OURO": 0.26, "SP500": 0.0})
    fora = pd.Series({"NTNB": 0.39, "BOVA11": 0.30, "OURO": 0.31, "SP500": 0.0})
    assert not rp.fora_da_banda(dentro, alvo, 0.20)
    assert rp.fora_da_banda(fora, alvo, 0.20)
    assert rp.fora_da_banda(
        dentro.replace({0.0: 0.01}), alvo, 0.20
    )  # alvo zero e posição > 0


# --- Motor -------------------------------------------------------------------------------


def test_decisao_no_fim_do_mes_so_rende_dois_pregoes_depois():
    """Decisão em D (último pregão do mês), compra no fechamento de D+1: a carteira só rende em D+2."""
    precos = pd.DataFrame(100.0, index=DATAS, columns=ATIVOS)
    decisoes = rp.dias_de_decisao(DATAS)
    primeira = decisoes[decisoes >= DATAS[rp.JANELA]][0]
    pos = DATAS.get_loc(primeira)
    precos.loc[DATAS[pos + 1] :, "BOVA11"] *= (
        1.10  # salto em D+1 (compra-se depois dele)
    )
    precos.loc[DATAS[pos + 2] :, "BOVA11"] *= 1.10  # salto em D+2
    parametros = rp.Parametros(
        esquema="fixo",
        pesos_fixos={"BOVA11": 0.5},
        custos=rp.SEM_CUSTOS,
        fator_de_impacto=0.0,
    )
    resultado = rp.simular(precos, CDI_ZERO, VOLUMES, parametros)
    assert resultado.retorno.loc[: DATAS[pos + 1]].eq(0).all()
    assert resultado.retorno.loc[DATAS[pos + 2]] == pytest.approx(0.05)
    assert resultado.pesos.loc[DATAS[pos + 1], "BOVA11"] == pytest.approx(0.5)
    assert resultado.pesos.loc[DATAS[pos], "BOVA11"] == 0.0


def test_antes_de_um_ano_de_dados_tudo_fica_em_caixa_rendendo_o_cdi():
    precos = _precos()
    resultado = rp.simular(precos, _cdi(), VOLUMES, SEM_ATRITO)
    inicio = resultado.retorno.index[1 : rp.JANELA]
    assert resultado.retorno.loc[inicio].to_numpy() == pytest.approx(0.0004)
    assert resultado.pesos.loc[inicio].eq(0).all().all()
    assert resultado.alvos.index.min() >= DATAS[rp.JANELA]


def test_a_banda_evita_negociar_quando_a_carteira_esta_perto_do_alvo():
    precos = _precos(media=0.0, vols=(0.001, 0.001, 0.001, 0.001))  # quase nada deriva
    com_banda = rp.simular(precos, _cdi(), VOLUMES, SEM_ATRITO)
    sem_banda = rp.simular(
        precos, _cdi(), VOLUMES, rp.Parametros(**{**SEM_ATRITO.__dict__, "banda": 0.0})
    )
    dias_com = (com_banda.negociado.abs().sum(axis=1) > 0).sum()
    dias_sem = (sem_banda.negociado.abs().sum(axis=1) > 0).sum()
    assert dias_com < dias_sem
    assert dias_sem == len(com_banda.alvos)  # sem banda, negocia em toda execução


def test_olhar_o_futuro_usa_a_janela_do_mes_seguinte_e_infla():
    precos = _precos_com_regimes()
    base = rp.Parametros(
        esquema="inverso_vol", custos=rp.SEM_CUSTOS, fator_de_impacto=0.0
    )
    normal = rp.simular(precos, CDI_ZERO, VOLUMES, base)
    futuro = rp.simular(
        precos,
        CDI_ZERO,
        VOLUMES,
        rp.Parametros(**{**base.__dict__, "olhar_o_futuro": True}),
    )
    assert rp.sharpe(futuro.retorno) > rp.sharpe(normal.retorno) + 0.3
    assert not normal.alvos.equals(futuro.alvos)


def test_custos_imposto_e_impacto_reduzem_o_resultado():
    precos = _precos(media=0.0008)
    cdi = _cdi()
    bruto = rp.simular(precos, cdi, VOLUMES, SEM_ATRITO)
    liquido = rp.simular(
        precos, cdi, VOLUMES, rp.Parametros(custos=CustosBR(corretagem_por_ordem=5.0))
    )
    assert liquido.custos.sum() > 0 and liquido.imposto.sum() > 0
    assert bruto.custos.sum() == 0 and bruto.imposto.sum() == 0
    assert liquido.patrimonio.iloc[-1] < bruto.patrimonio.iloc[-1]
    assert liquido.giro > 0
    estresse = rp.simular(
        precos,
        cdi,
        VOLUMES,
        rp.Parametros(
            custos=CustosBR(corretagem_por_ordem=5.0).em_estresse(2.0),
            fator_de_impacto=2.0,
        ),
    )
    assert estresse.custos.sum() > liquido.custos.sum()


def test_imposto_e_pago_no_ultimo_pregao_do_mes_seguinte_vendendo_se_preciso():
    precos = _precos(media=0.0008)
    resultado = rp.simular(precos, _cdi(), VOLUMES, rp.Parametros())
    pagamentos = resultado.imposto[resultado.imposto > 0]
    assert len(pagamentos) > 0
    ultimos_pregoes = rp.dias_de_decisao(resultado.imposto.index)
    assert pagamentos.index.isin(ultimos_pregoes).all()  # o DARF vence no mês seguinte
    nos_dias_de_pagamento = resultado.negociado.loc[pagamentos.index]
    assert (
        (nos_dias_de_pagamento <= 1e-9).all().all()
    )  # nesses dias só se vende, para pagar
    # o imposto do mês só existe depois de uma venda: o primeiro pagamento vem depois da 1ª venda
    primeira_venda = resultado.negociado.index[(resultado.negociado < 0).any(axis=1)][0]
    assert pagamentos.index[0] > primeira_venda


def test_modo_aporte_so_compra_e_o_retorno_e_ponderado_no_tempo():
    precos = _precos(media=0.0008)
    cdi = _cdi()
    aporte = rp.simular(precos, cdi, VOLUMES, rp.Parametros(modo="aporte"))
    assert (aporte.negociado >= -1e-9).all().all()
    assert aporte.imposto.sum() == 0
    assert aporte.aportes.sum() > 0
    assert (
        (
            aporte.aportes[aporte.aportes > 0]
            / aporte.patrimonio.shift(1)[aporte.aportes > 0]
        )
        .round(6)
        .le(0.0101)
        .all()
    )
    composto = rp.CAPITAL_INICIAL * float((1 + aporte.retorno).prod())
    assert (
        aporte.patrimonio.iloc[-1] > composto
    )  # o dinheiro novo não conta como retorno
    vender = rp.simular(precos, cdi, VOLUMES, rp.Parametros(modo="vender"))
    assert vender.aportes.sum() == 0


def test_regua_60_40_rebalanceia_todo_mes_para_60_por_cento():
    precos = _precos()
    resultado = rp.simular(precos, _cdi(), VOLUMES, rp.REGUA_60_40)
    execucoes = resultado.negociado.index[resultado.negociado.abs().sum(axis=1) > 0]
    assert len(execucoes) == len(resultado.alvos)
    assert resultado.pesos.loc[execucoes, "BOVA11"].to_numpy() == pytest.approx(
        0.6, abs=1e-3
    )
    assert (
        resultado.pesos.loc[execucoes].drop(columns="BOVA11").abs().max().max() < 1e-12
    )


def test_reexecucao_identica_e_hash_do_resultado():
    precos = _precos()
    a = rp.simular(precos, _cdi(), VOLUMES, rp.Parametros())
    b = rp.simular(precos, _cdi(), VOLUMES, rp.Parametros())
    assert a.retorno.equals(b.retorno)
    assert rp.hash_do_resultado(a) == rp.hash_do_resultado(b)
    c = rp.simular(precos, _cdi(), VOLUMES, rp.Parametros(esquema="inverso_vol"))
    assert rp.hash_do_resultado(a) != rp.hash_do_resultado(c)


def test_cortar_o_futuro_nao_muda_o_passado():
    precos = _precos()
    corte = DATAS[int(len(DATAS) * 0.7)]
    assert rp.cortar_o_futuro_nao_muda_o_passado(
        precos, _cdi(), VOLUMES, rp.Parametros(), corte
    )
    assert rp.cortar_o_futuro_nao_muda_o_passado(
        precos, _cdi(), VOLUMES, rp.Parametros(modo="aporte"), corte
    )


def test_entradas_invalidas_sao_recusadas():
    precos = _precos()
    with pytest.raises(ValueError, match="vazio"):
        com_buraco = precos.copy()
        com_buraco.loc[DATAS[10], "OURO"] = np.nan
        rp.simular(com_buraco, _cdi(), VOLUMES, rp.Parametros())
    with pytest.raises(ValueError, match="datas"):
        rp.simular(precos, _cdi(datas=DATAS[:-5]), VOLUMES, rp.Parametros())
    with pytest.raises(ValueError, match="ativos"):
        rp.simular(precos.drop(columns="OURO"), _cdi(), VOLUMES, rp.Parametros())
    with pytest.raises(ValueError, match="modo"):
        rp.Parametros(modo="alavancar")
    with pytest.raises(ValueError, match="esquema"):
        rp.Parametros(esquema="hrp")


def test_especificacao_e_json_estavel():
    spec = rp.Parametros().especificacao()
    assert spec["esquema"] == "risk_parity" and spec["modo"] == "vender"
    assert spec["custos"]["ir_swing"] == 0.15 and spec["versao"] == rp.VERSAO
    assert spec == rp.Parametros().especificacao()


# --- Contra o acaso ----------------------------------------------------------------------


def test_p_valor_do_acaso_e_reproduzivel_e_fica_entre_zero_e_um():
    precos = _precos()
    cdi = _cdi()
    resultado = rp.simular(precos, cdi, VOLUMES, rp.Parametros())
    retornos = precos.pct_change().fillna(0.0)
    a = rp.p_valor_do_acaso(resultado.pesos, retornos, cdi, 0.0003, sorteios=200)
    b = rp.p_valor_do_acaso(resultado.pesos, retornos, cdi, 0.0003, sorteios=200)
    assert set(a) == {"sharpe_real", "percentil_95", "p_valor"}
    assert 0 < a["p_valor"] <= 1 and a == b


def test_p_valor_do_acaso_ve_quem_sabe_o_futuro():
    """Pesos que vão para o ativo que vai subir amanhã: o deslocamento no tempo destrói isso."""
    precos = _precos(media=0.0)
    retornos = precos.pct_change().fillna(0.0)
    melhor_de_amanha = retornos.shift(-1).fillna(0.0).idxmax(axis=1)
    pesos = (
        pd.get_dummies(melhor_de_amanha)
        .reindex(columns=ATIVOS, fill_value=0)
        .astype(float)
    )
    acaso = rp.p_valor_do_acaso(pesos, retornos, CDI_ZERO, 0.0, sorteios=200)
    assert acaso["p_valor"] < 0.05


def test_janela_sem_variacao_e_recusada_em_vez_de_virar_nan():
    """Achado da tentativa 1 real: a NTN-B ficou parada por 80 pregões (buraco na curva) e o
    risk parity virou 0/0 em silêncio na rodada que olha o futuro."""
    janela = _precos().pct_change().iloc[1:300]
    janela["NTNB"] = 0.0
    for esquema in ("risk_parity", "inverso_vol", "min_var"):
        with pytest.raises(ValueError, match="sem variação em NTNB"):
            rp.calcular_pesos(esquema, janela)
    precos = _precos()
    precos.loc[: DATAS[400], "NTNB"] = 100.0  # preço repetido por mais de um ano
    with pytest.raises(ValueError, match="sem variação"):
        rp.simular(precos, _cdi(), VOLUMES, rp.Parametros())
