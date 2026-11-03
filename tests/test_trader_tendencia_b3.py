"""Tendência na B3, ficha P0-2 do pré-registro quant v0.1: o motor com dados sintéticos."""

import numpy as np
import pandas as pd
import pytest

from trader.custos_br import CustosBR
from trader.estrategias import tendencia_b3 as tb

PREGOES = pd.bdate_range("2012-01-02", periods=900)
CDI = pd.Series(0.0004, index=PREGOES)
SEM_CUSTO = tb.com(tb.Parametros(), custos=tb.SEM_CUSTOS, fator_de_impacto=0.0)


def _fechamento(semente=7, media=None):
    """Tendências longas alternadas: a regra tem o que seguir."""
    gerador = np.random.default_rng(semente)
    if media is None:
        fase = (np.arange(len(PREGOES)) // 150) % 2
        media = np.where(fase == 0, 0.002, -0.0015)
    retornos = gerador.normal(media, 0.015, size=len(PREGOES))
    return pd.Series(100 * np.cumprod(1 + retornos), index=PREGOES)


def _bova11(fechamento=None, volume=5e8):
    fechamento = _fechamento() if fechamento is None else fechamento
    abertura = fechamento.shift(1).fillna(fechamento.iloc[0]) * 1.001
    return tb.a_vista(
        "BOVA11", abertura, fechamento, pd.Series(volume, index=PREGOES), CDI
    )


def _curva(taxa=0.11):
    return pd.DataFrame(
        {
            "data_base": PREGOES,
            "curva": "nominal",
            "prazo_anos": 2.0,
            "taxa": taxa + 0.01 * np.sin(np.arange(len(PREGOES)) / 60),
        }
    )


# --- a regra -------------------------------------------------------------------------------------


def test_sinal_olha_o_excesso_ao_cdi_e_nao_o_preco():
    # O preço sobe todo dia, mas menos que o CDI: no preço seria compra; no excesso, nunca.
    fechamento = pd.Series(100 * (1.0003 ** np.arange(len(PREGOES))), index=PREGOES)
    ativo = _bova11(fechamento)
    assert (ativo.excesso.iloc[1:] < 0).all()
    assert tb.tc.sinal(fechamento).dropna().eq(1.0).all()
    assert tb.fracao_alvo(ativo, tb.Parametros()).max() == 0.0


def test_aquecimento_e_a_maior_janela_em_pregoes():
    ativo = _bova11()
    alvo = tb.fracao_alvo(ativo, tb.Parametros())
    assert (alvo.iloc[: tb.AQUECIMENTO_EM_PREGOES] == 0).all()
    resultado = tb.simular(ativo, CDI)
    assert resultado.retorno.index[0] == PREGOES[tb.AQUECIMENTO_EM_PREGOES]


def test_peso_fica_entre_zero_e_um_e_respeita_a_vol_alvo():
    ativo = _bova11()
    alvo = tb.fracao_alvo(ativo, tb.Parametros())
    assert alvo.between(0, 1).all()
    sigma = tb.volatilidade_do_excesso(ativo.excesso, tb.JANELA_DA_VOL)
    teto = (tb.VOL_ALVO / sigma).clip(upper=1.0).fillna(0.0)
    assert (alvo <= teto + 1e-12).all()


def test_executa_no_leilao_de_abertura_do_pregao_seguinte():
    ativo = _bova11()
    resultado = tb.simular(ativo, CDI, SEM_CUSTO)
    alvo = tb.fracao_alvo(ativo, SEM_CUSTO)
    esperado = alvo.shift(1).fillna(0.0).iloc[tb.AQUECIMENTO_EM_PREGOES :]
    assert resultado.alvos.equals(esperado)
    dia = resultado.negociado[resultado.negociado > 0].index[0]
    cotas = resultado.negociado.loc[dia] / ativo.abertura.loc[dia]
    assert cotas == pytest.approx(round(cotas))  # preço da abertura, não do fechamento
    assert round(cotas) % tb.LOTE == 0


def test_cortar_o_futuro_nao_muda_o_passado():
    ativo = _bova11()
    corte = PREGOES[700]
    assert tb.cortar_o_futuro_nao_muda_o_passado(ativo, CDI, tb.Parametros(), corte)


def test_olhar_o_futuro_infla_o_resultado():
    ativo = _bova11()
    base = tb.simular(ativo, CDI, SEM_CUSTO)
    futuro = tb.simular(ativo, CDI, tb.com(SEM_CUSTO, olhar_o_futuro=True))
    assert tb.sharpe_do_excesso(futuro.retorno, CDI) > tb.sharpe_do_excesso(
        base.retorno, CDI
    )


# --- custos, lote e imposto ----------------------------------------------------------------------


def test_bova11_paga_a_tarifa_do_leilao_e_ir_de_etf_sem_isencao():
    ativo = _bova11()
    custos = CustosBR(emolumentos_no_leilao=0.001, emolumentos_a_vista=0.0)
    parametros = tb.com(tb.Parametros(), custos=custos, fator_de_impacto=0.0)
    resultado = tb.simular(ativo, CDI, parametros)
    assert resultado.custos.sum() == pytest.approx(
        0.001 * resultado.negociado.abs().sum()
    )
    assert resultado.meses_acima_da_isencao() == 0  # ETF não tem isenção
    ganhos = resultado.ir[resultado.ir["base"] > 0]
    assert len(ganhos) and (ganhos["imposto"] > 0).all()
    assert resultado.imposto.sum() == pytest.approx(resultado.ir["imposto"].sum())


def test_posicao_zerada_rende_o_cdi():
    queda = _fechamento(media=np.full(len(PREGOES), -0.002))
    resultado = tb.simular(_bova11(queda), CDI, SEM_CUSTO)
    parado = (resultado.exposicao == 0) & (resultado.exposicao.shift(1) == 0)
    assert parado.any()
    assert np.allclose(resultado.retorno[parado].to_numpy(), 0.0004)


def test_estresse_dobra_bolsa_spread_e_impacto_mas_nao_o_imposto():
    normal = tb.Parametros()
    estresse = normal.em_estresse(2.0)
    assert estresse.fator_de_impacto == 2.0
    assert estresse.spread_do_futuro_por_lado == pytest.approx(2 * tb.SPREAD_POR_LADO)
    assert estresse.custos.emolumentos_no_leilao == pytest.approx(
        2 * normal.custos.emolumentos_no_leilao
    )
    assert estresse.custos.ir_swing == normal.custos.ir_swing


def test_nenhuma_saida_vira_day_trade_com_uma_ordem_por_pregao():
    for ativo in (_bova11(), tb.win_sintetico(_bova11(), CDI)):
        assert tb.simular(ativo, CDI).day_trades == 0


# --- futuros sintéticos --------------------------------------------------------------------------


def test_win_segue_o_excesso_do_bova11_com_o_caixa_a_cdi():
    bova11 = _bova11()
    win = tb.win_sintetico(bova11, CDI)
    assert win.classe == "futuros" and win.valor_do_contrato == 20_000
    assert win.rolagens and all(d.month % 2 == 0 for d in win.rolagens)
    sem = tb.com(SEM_CUSTO, spread_do_futuro_por_lado=0.0)
    r_win = tb.simular(win, CDI, sem)
    r_bova = tb.simular(bova11, CDI, sem)
    # mesma regra sobre o mesmo excesso: exposições parecidas (o lote de 100 muda um pouco)
    assert (r_win.exposicao - r_bova.exposicao).abs().mean() < 0.05
    assert r_win.custos.sum() == 0 and r_win.rolagem.sum() == 0


def test_rolagem_do_win_paga_as_duas_pernas_e_entra_no_custo_por_ano():
    win = tb.win_sintetico(_bova11(), CDI)
    resultado = tb.simular(win, CDI)
    no_periodo = [d for d in win.rolagens if d in resultado.retorno.index]
    assert no_periodo
    assert (resultado.rolagem > 0).sum() <= len(no_periodo)
    assert resultado.rolagem.sum() > 0
    assert resultado.custo_de_rolagem_por_ano() > 0


def test_ir_do_futuro_e_sobre_o_ajuste_do_mes_sem_isencao():
    win = tb.win_sintetico(_bova11(), CDI)
    resultado = tb.simular(win, CDI)
    assert resultado.ir["resultado"].sum() == pytest.approx(
        resultado.resultado_realizado.sum()
    )
    assert resultado.meses_acima_da_isencao() == 0
    ganhos = resultado.ir[resultado.ir["base"] > 0]
    assert len(ganhos) and (ganhos["imposto"] > 0).all()


def test_di1_executa_na_marcacao_e_rola_uma_vez_por_ano():
    di1 = tb.di1_sintetico(_curva(), CDI, _bova11())
    assert di1.abertura.equals(di1.fechamento)
    anos = {d.year for d in di1.rolagens}
    assert di1.rolagens and len(di1.rolagens) == len(anos)
    resultado = tb.simular(di1, CDI)
    assert resultado.retorno.notna().all()


def test_cesta_de_acoes_tem_isencao_de_20_mil():
    fechamentos = pd.DataFrame(
        {f"P{k}": _fechamento(semente=k) for k in range(3)}, index=PREGOES
    )
    aberturas = fechamentos.shift(1).fillna(fechamentos.iloc[0])
    volumes = pd.DataFrame(1e8, index=PREGOES, columns=fechamentos.columns)
    ativo = tb.cesta(aberturas, fechamentos, volumes, CDI)
    assert ativo.classe == "acoes"
    resultado = tb.simular(ativo, CDI)
    isentos = resultado.ir[resultado.ir["vendas"] <= 20_000]
    assert (isentos["imposto"] == 0).all()


# --- réguas e conferências -----------------------------------------------------------------------


def test_comprar_e_segurar_compra_na_abertura_e_segue_o_fechamento():
    ativo = _bova11()
    regua = tb.comprar_e_segurar(ativo, SEM_CUSTO)
    i = tb.AQUECIMENTO_EM_PREGOES
    assert regua.index[0] == PREGOES[i]
    assert regua.iloc[0] == pytest.approx(
        ativo.fechamento.iloc[i] / ativo.abertura.iloc[i] - 1
    )
    assert np.allclose(
        regua.iloc[1:].to_numpy(), ativo.fechamento.pct_change().iloc[i + 1 :]
    )


def test_reexecucao_identica():
    ativo = _bova11()
    assert tb.hash_do_resultado(tb.simular(ativo, CDI)) == tb.hash_do_resultado(
        tb.simular(ativo, CDI)
    )


def test_entradas_erradas_sao_recusadas():
    a = _bova11()
    with pytest.raises(ValueError, match="CDI"):
        tb.simular(a, CDI.iloc[:-5])
    with pytest.raises(ValueError, match="classe"):
        tb.Ativo("X", a.abertura, a.fechamento, a.excesso, a.volume, "cripto")
    with pytest.raises(ValueError, match="mesmas datas"):
        tb.Ativo("X", a.abertura.iloc[1:], a.fechamento, a.excesso, a.volume, "etf")
    curto = tb.a_vista(
        "X", a.abertura.iloc[:300], a.fechamento.iloc[:300], a.volume.iloc[:300], CDI
    )
    with pytest.raises(ValueError, match="aquecimento"):
        tb.simular(curto, CDI)
    with pytest.raises(ValueError, match="janela"):
        tb.Parametros(janelas=(1, 5))


def test_especificacao_diz_a_execucao_e_o_candidato():
    spec = tb.Parametros().especificacao()
    assert spec["execucao"] == "leilão de abertura de D+1"
    assert spec["candidato"] == "BOVA11"
    assert spec["janelas"] == list(tb.JANELAS)
    assert spec["custos"]["emolumentos_no_leilao"] == pytest.approx(0.00032)
