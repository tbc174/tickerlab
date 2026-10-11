"""Dimensionamento por volatilidade, buffer, custos por ativo, baselines, avaliação e viabilidade."""

import numpy as np
import pandas as pd
import pytest

from trader import avaliacao, baselines, posicao, viabilidade
from trader.backtest import executar_backtest
from trader.custos import CARREGAMENTO_ANUAL, custos_do_ativo
from trader.universo import UNIVERSO, Ativo


def _retornos(n=1500, vol=0.01, media=0.0, seed=1, freq="B"):
    rng = np.random.default_rng(seed)
    indice = pd.date_range("2005-01-03", periods=n, freq=freq)
    return pd.Series(rng.normal(media, vol, n), index=indice)


# --- posição -------------------------------------------------------------------------------


def test_retornos_seguros_zeram_o_dia_de_preco_negativo():
    p = pd.Series(
        [18.0, -37.63, 10.0, 11.0], index=pd.bdate_range("2020-04-17", periods=4)
    )
    r = posicao.retornos_seguros(p)
    assert r.iloc[0] == 0 and r.iloc[1] == 0 and r.iloc[2] == 0
    assert r.iloc[3] == pytest.approx(0.1)


def test_volatilidade_mista_acerta_a_ordem_de_grandeza_e_nao_olha_o_futuro():
    r = _retornos(vol=0.01)
    vol = posicao.volatilidade_mista(r)
    assert vol.iloc[-1] == pytest.approx(0.01 * np.sqrt(252), rel=0.3)
    alterado = r.copy()
    alterado.iloc[-1] = 0.5  # choque no último dia
    pd.testing.assert_series_equal(
        posicao.volatilidade_mista(alterado).iloc[:-1], vol.iloc[:-1]
    )


def test_volatilidade_do_cripto_anualiza_com_365():
    r = _retornos(vol=0.03, freq="D")
    v252 = posicao.volatilidade_mista(r).iloc[-1]
    v365 = posicao.volatilidade_mista(r, dias_por_ano=365).iloc[-1]
    assert v365 / v252 == pytest.approx(np.sqrt(365 / 252), rel=0.05)


def test_posicao_por_volatilidade_respeita_alvo_teto_e_vol_desconhecida():
    indice = pd.RangeIndex(4)
    sinal = pd.Series([1.0, -1.0, 0.5, 1.0], index=indice)
    vol = pd.Series([0.20, 0.05, 0.10, np.nan], index=indice)
    p = posicao.posicao_por_volatilidade(sinal, vol, alvo=0.10, teto=1.5)
    assert p.tolist() == pytest.approx([0.5, -1.5, 0.5, 0.0])  # -2 vira -1,5 pelo teto
    with pytest.raises(ValueError):
        posicao.posicao_por_volatilidade(sinal, vol, alvo=0)


def test_buffer_so_negocia_fora_da_faixa_e_vai_ate_a_borda():
    ideal = pd.Series([1.0, 1.05, 0.95, 1.30, 1.25, 0.0])
    cheia = pd.Series(1.0, index=ideal.index)
    b = posicao.aplicar_buffer(ideal, cheia, largura=0.1)
    # entra até a borda inferior (0,9); fica parado dentro da faixa; sobe até 1,2; desce até 0,1
    assert b.tolist() == pytest.approx([0.9, 0.95, 0.95, 1.2, 1.2, 0.1])


def test_buffer_reduz_o_giro():
    r = _retornos()
    sinal = pd.Series(np.sin(np.arange(len(r)) / 7.0), index=r.index)
    sem = posicao.dimensionar(sinal, r, largura=0.0)
    com = posicao.dimensionar(sinal, r, largura=0.1)
    assert com.diff().abs().sum() < sem.diff().abs().sum()
    with pytest.raises(ValueError):
        posicao.aplicar_buffer(sem, sem, largura=-1)


# --- custos --------------------------------------------------------------------------------


def _ativo(simbolo):
    return next(a for a in UNIVERSO if a.simbolo == simbolo)


def test_custos_por_classe_da_secao_3():
    def por_lado(simbolo):
        c = custos_do_ativo(_ativo(simbolo))
        return float(c.custo_por_lado(pd.RangeIndex(1)).iloc[0])

    assert por_lado("EURUSD") == pytest.approx(
        0.0001
    )  # 0,5 pb de meio spread + 0,5 de deslizamento
    assert por_lado("USDMXN") == pytest.approx(0.0003)
    assert por_lado("XAUUSD") == pytest.approx(0.0003)
    assert por_lado("^BVSP") == pytest.approx(0.0002)
    assert por_lado("PETR4.SA") == pytest.approx(0.0005)
    assert por_lado("BTC-USD") == pytest.approx(0.0010)


def test_estresse_dobra_tudo_e_futuro_nao_paga_carregamento():
    c1, c2 = custos_do_ativo(_ativo("PETR4.SA")), custos_do_ativo(_ativo("PETR4.SA"), 2)
    assert c2.comissao == 2 * c1.comissao
    assert c1.swap_comprado_anual == c1.swap_vendido_anual == -CARREGAMENTO_ANUAL
    assert c2.swap_vendido_anual == -2 * CARREGAMENTO_ANUAL
    futuro = custos_do_ativo(
        Ativo("KC=F", "yfinance", "agro")
    )  # se voltar a ser operável
    assert futuro.swap_comprado_anual == futuro.swap_vendido_anual == 0


def test_custos_recusam_atributo_e_todo_ativo_operavel_tem_custo():
    with pytest.raises(ValueError, match="atributo"):
        custos_do_ativo(_ativo("^VIX"))
    for ativo in UNIVERSO:
        if ativo.papel == "operar":
            custos_do_ativo(ativo)  # nenhuma classe sem custo
    with pytest.raises(ValueError):
        custos_do_ativo(_ativo("EURUSD"), 0)


# --- baselines -----------------------------------------------------------------------------


def test_b0_compra_acoes_e_fica_fora_de_cambio_e_metais():
    indice = pd.RangeIndex(3)
    assert (baselines.sinal_b0(_ativo("PETR4.SA"), indice) == 1).all()
    for simbolo in ("EURUSD", "BRL=X", "XAUUSD", "HG=F"):
        assert (baselines.sinal_b0(_ativo(simbolo), indice) == 0).all()


def test_b1_segue_a_tendencia_e_respeita_os_limites():
    alta = _retornos(media=0.002, vol=0.01)
    baixa = _retornos(media=-0.002, vol=0.01, seed=2)
    s_alta, s_baixa = baselines.sinal_b1(alta), baselines.sinal_b1(baixa)
    assert s_alta.iloc[400:].mean() > 0.2 and s_baixa.iloc[400:].mean() < -0.2
    assert s_alta.between(-1, 1).all() and s_baixa.between(-1, 1).all()
    assert (s_alta.iloc[: baselines.MINIMO_DE_DIAS - 1] == 0).all()  # aquecimento


def test_b1_nao_olha_o_futuro():
    r = _retornos(media=0.001)
    s = baselines.sinal_b1(r)
    alterado = r.copy()
    alterado.iloc[-50:] = -0.05  # tombo no fim
    pd.testing.assert_series_equal(
        baselines.sinal_b1(alterado).iloc[:-50], s.iloc[:-50]
    )


def test_b1_tem_media_absoluta_perto_de_meio():
    s = baselines.sinal_b1(_retornos(n=4000))
    assert 0.25 < s.iloc[1000:].abs().mean() < 0.75  # previsão média 10 de 20


def test_b2_e_o_sinal_do_retorno_de_hoje():
    r = pd.Series([0.01, -0.02, 0.0, np.nan])
    assert baselines.sinal_b2(r).tolist() == [1.0, -1.0, 0.0, 0.0]


def test_preco_sintetico_refaz_os_retornos():
    r = _retornos(n=50)
    p = baselines.preco_sintetico(r)
    pd.testing.assert_series_equal(
        p.pct_change().iloc[1:], r.iloc[1:], check_names=False
    )


def test_pipeline_completo_com_teto_2_no_motor():
    r = _retornos(media=0.001)
    pos = posicao.dimensionar(baselines.sinal_b1(r), r)
    assert pos.abs().max() <= posicao.TETO_PADRAO
    res = executar_backtest(
        baselines.preco_sintetico(r),
        pos,
        custos_do_ativo(_ativo("^GSPC")),
        limite=posicao.TETO_PADRAO,
        retorno_do_ativo=r,
    )
    assert res.custos.sum() > 0 and len(res.retorno) == len(r)


# --- avaliação -----------------------------------------------------------------------------


def test_fim_de_semana_do_cripto_vai_para_a_segunda():
    indice = pd.to_datetime(["2024-01-05", "2024-01-06", "2024-01-07", "2024-01-08"])
    r = pd.Series([0.01, 0.10, -0.05, 0.02], index=indice)  # sex, sáb, dom, seg
    u = avaliacao.para_dias_uteis(r)
    assert list(u.index) == list(pd.to_datetime(["2024-01-05", "2024-01-08"]))
    assert u.iloc[1] == pytest.approx(1.10 * 0.95 * 1.02 - 1)


def test_metricas_basicas():
    r = _retornos(n=2520, media=0.0004, vol=0.01)
    resumo = avaliacao.resumir_serie(r)
    assert resumo["sharpe"] == pytest.approx(r.mean() / r.std() * np.sqrt(252))
    assert resumo["t"] == pytest.approx(resumo["sharpe"] * np.sqrt(2520 / 252))
    assert -1 < resumo["maior_queda"] < 0
    assert 0 <= resumo["anos_positivos"] <= 1
    assert np.isnan(avaliacao.sharpe(pd.Series([0.01])))


def test_carteira_media_e_participacao():
    indice = pd.bdate_range("2024-01-01", periods=4)
    a = pd.Series([0.02, 0.02, 0.02, 0.02], index=indice)
    b = pd.Series([0.0, 0.0, np.nan, np.nan], index=indice)
    tabela = avaliacao.montar_carteira({"A": a, "B": b})
    carteira = avaliacao.retorno_da_carteira(tabela)
    assert carteira.tolist() == pytest.approx([0.01, 0.01, 0.02, 0.02])
    part = avaliacao.participacao_por_ativo(tabela)
    assert part["A"] == pytest.approx(1.0) and part["B"] == pytest.approx(0.0)
    resumo = avaliacao.resumir_carteira({"A": a, "B": b + 0.001})
    assert resumo["ativos"] == 2 and resumo["ativo_de_maior_participacao"] == "A"


# --- viabilidade ---------------------------------------------------------------------------


def test_movimento_contra_custo_e_autocorrelacao():
    r = _retornos(n=2000, vol=0.01)
    linha = viabilidade.linha_de_viabilidade(r, custo_ida_e_volta=0.0002)
    assert (
        linha["movimento_maior_que_custo_1d"] > 0.95
    )  # 1% de vol contra 2 pb de custo
    caro = viabilidade.linha_de_viabilidade(r, custo_ida_e_volta=0.05)
    assert caro["movimento_maior_que_custo_1d"] < 0.01
    assert (
        linha["movimento_maior_que_custo_21d"]
        >= linha["movimento_maior_que_custo_1d"] - 0.05
    )
    assert abs(linha["autocorrelacao_1d"]) < 0.1  # ruído não tem memória


def test_apostas_independentes_contam_ativos_repetidos_uma_vez():
    base = _retornos(n=1500)
    outro = _retornos(n=1500, seed=9)
    iguais = {"A": base, "B": base, "C": base, "D": outro}
    resumo = viabilidade.apostas_independentes(viabilidade.retornos_semanais(iguais))
    assert resumo["ativos"] == 4
    assert resumo["apostas_independentes"] == pytest.approx(
        1.6, abs=0.15
    )  # (3+1)²/(9+1)
    independentes = {k: _retornos(n=1500, seed=s) for k, s in zip("ABCD", range(4))}
    resumo2 = viabilidade.apostas_independentes(
        viabilidade.retornos_semanais(independentes)
    )
    assert resumo2["apostas_independentes"] > 3.5


def test_ativo_ficticio_classe_desconhecida_da_erro_claro():
    with pytest.raises(KeyError, match="Classe"):
        custos_do_ativo(Ativo("XYZ", "yfinance", "classe_nova"))


def test_futuros_do_yahoo_sao_so_atributo_e_avaliacao_comeca_em_2000():
    from trader.holdout import INICIO_DA_AVALIACAO

    futuros = [a for a in UNIVERSO if a.simbolo.endswith("=F")]
    assert len(futuros) == 14
    assert all(a.papel == "atributo" for a in futuros)
    assert INICIO_DA_AVALIACAO == pd.Timestamp("2000-01-03")


def test_zerar_erros_de_ajuste_so_mexe_nos_saltos_impossiveis():
    r = pd.Series([0.01, 1.0, -0.997, 0.39, -0.41])
    limpo, n = posicao.zerar_erros_de_ajuste(r)
    assert n == 3
    assert limpo.tolist() == pytest.approx([0.01, 0.0, 0.0, 0.39, 0.0])


# --- carteira com risco igual por grupo (critério v0.3, seção 3) ----------------------------


def test_cada_grupo_recebe_o_mesmo_peso_qualquer_que_seja_o_tamanho():
    from trader import avaliacao

    datas = pd.bdate_range("2020-01-06", periods=3)
    # três ações da B3 (um grupo) e um par de moedas (outro grupo)
    tabela = pd.DataFrame(
        {"PETR4.SA": 0.03, "VALE3.SA": 0.03, "ITUB4.SA": 0.03, "EURUSD": -0.01},
        index=datas,
    )
    carteira = avaliacao.retorno_da_carteira(tabela)
    assert carteira.iloc[0] == pytest.approx(
        0.5 * 0.03 + 0.5 * -0.01
    )  # não 3/4 em ações
    pesos = avaliacao.pesos_por_grupo(tabela.notna().to_numpy(), list(tabela.columns))
    assert pesos[0].tolist() == pytest.approx([1 / 6, 1 / 6, 1 / 6, 1 / 2])
    assert pesos.sum(axis=1) == pytest.approx([1, 1, 1])


def test_grupo_sem_dado_no_dia_sai_e_o_peso_vai_para_os_outros():
    from trader import avaliacao

    datas = pd.bdate_range("2020-01-06", periods=2)
    tabela = pd.DataFrame(
        {
            "BTC-USD": [np.nan, 0.10],  # a cripto só existe a partir do 2º dia
            "EURUSD": [0.01, 0.01],
            "TLT": [0.02, 0.02],
        },
        index=datas,
    )
    carteira = avaliacao.retorno_da_carteira(tabela)
    assert carteira.iloc[0] == pytest.approx((0.01 + 0.02) / 2)
    assert carteira.iloc[1] == pytest.approx((0.10 + 0.01 + 0.02) / 3)


def test_concentracao_usa_os_pesos_por_grupo():
    from trader import avaliacao

    datas = pd.bdate_range("2020-01-06", periods=4)
    tabela = pd.DataFrame(
        {"PETR4.SA": 0.01, "VALE3.SA": 0.01, "EURUSD": 0.01}, index=datas
    )
    participacao = avaliacao.participacao_por_ativo(tabela)
    assert participacao["EURUSD"] == pytest.approx(0.5)  # sozinho no grupo: metade
    assert participacao["PETR4.SA"] == pytest.approx(0.25)


def test_nomes_fora_do_universo_continuam_com_peso_igual_por_ativo():
    from trader import avaliacao

    datas = pd.bdate_range("2020-01-06", periods=1)
    tabela = pd.DataFrame({"x1": [0.03], "x2": [0.0], "x3": [0.0]}, index=datas)
    assert avaliacao.retorno_da_carteira(tabela).iloc[0] == pytest.approx(0.01)


def test_todo_ativo_operavel_tem_grupo():
    from trader.universo import GRUPO_DA_CLASSE, UNIVERSO

    assert {a.classe for a in UNIVERSO if a.papel == "operar"} <= set(GRUPO_DA_CLASSE)
