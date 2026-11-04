"""Ficha P0-1b do pré-registro quant v0.2: a regra da P0-1 no par em reais, com a banda de 20%.

A regra é a da P0-1 sem mudança (importada, não copiada); a P0-1b só acrescenta a banda, o spread
do livro em reais (0,3% por lado no critério) e tira o câmbio.
"""

import numpy as np
import pandas as pd
import pytest

from trader import criterio_quant
from trader.estrategias import tendencia_cripto as tc
from trader.estrategias import tendencia_cripto_brl as brl

DIAS = pd.date_range("2020-10-13", periods=900, freq="D")
CDI = pd.Series(0.0004, index=DIAS)
VOLUMES = pd.DataFrame(1e9, index=DIAS, columns=list(tc.ATIVOS))
CAPITAL = 100_000.0
SEM_CUSTOS = brl.Parametros(
    custos=tc.SEM_CUSTOS, fator_de_impacto=0.0, spread_por_lado=0.0
)


def _precos(semente=3, media=0.001, desvio=0.03):
    gerador = np.random.default_rng(semente)
    retornos = gerador.normal(media, desvio, (len(DIAS), len(tc.ATIVOS)))
    return pd.DataFrame(
        100 * np.cumprod(1 + retornos, axis=0), index=DIAS, columns=list(tc.ATIVOS)
    )


# --- parâmetros --------------------------------------------------------------------------------


def test_parametros_sao_os_da_p0_1_mais_a_banda_e_o_spread():
    p = brl.Parametros()
    assert p.janelas == tc.JANELAS and p.vol_alvo == tc.VOL_ALVO
    assert p.janela_da_vol == tc.JANELA_DA_VOL
    assert p.fracao_por_ativo == tc.FRACAO_POR_ATIVO
    assert p.banda == 0.20 and p.spread_por_lado == 0.003
    assert p.com_cambio is False  # par em reais: sem IOF nem spread de câmbio
    assert brl.SPREAD_DE_LEITURA == 0.001
    assert criterio_quant.ORCAMENTO_POR_FICHA["P0-1b"] == brl.ORCAMENTO == 2


def test_parametros_recusam_banda_e_spread_fora_do_lugar():
    with pytest.raises(ValueError):
        brl.Parametros(banda=0.0)
    with pytest.raises(ValueError):
        brl.Parametros(banda=1.0)
    with pytest.raises(ValueError):
        brl.Parametros(spread_por_lado=-0.001)
    brl.Parametros(banda=None)  # sem banda: a regra da P0-1 (teste d)


def test_estresse_dobra_tambem_o_spread():
    p = brl.Parametros().em_estresse(2.0)
    assert p.spread_por_lado == pytest.approx(0.006)
    assert p.fator_de_impacto == 2.0
    assert p.custos.taxa_cripto_por_lado == pytest.approx(
        2 * tc.PADRAO.taxa_cripto_por_lado
    )
    assert p.banda == 0.20  # a banda é regra, não custo


def test_especificacao_em_tipos_simples_com_banda_e_spread():
    spec = brl.Parametros().especificacao()
    assert spec["banda"] == 0.20 and spec["spread_por_lado"] == 0.003
    assert spec["com_cambio"] is False
    assert spec["versao_do_codigo_p0_1b"] == brl.VERSAO
    assert spec["banda_minima"] == tc.BANDA_MINIMA
    assert "regra_da_banda" in spec


# --- a banda -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("posicao", "alvo", "negocia"),
    [
        (0.30, 0.30, False),
        (0.25, 0.30, False),  # 0,05 é menos de 20% de 0,30
        (0.35, 0.30, False),
        (0.23, 0.30, True),  # 0,07 passa de 20% de 0,30
        (0.37, 0.30, True),
        (0.10, 0.0, True),  # alvo zero: zera
        (0.001, 0.0, True),  # mesmo pequena
        (0.0, 0.0, False),
        (0.0, 0.004, False),  # posição zero só abre acima de 0,5%
        (0.0, 0.006, True),
        (0.0035, 0.0050, False),  # passa da banda, mas a ordem é menor que 0,5% (P0-1)
    ],
)
def test_banda_de_20_por_cento(posicao, alvo, negocia):
    assert brl.deve_negociar(posicao, alvo, 0.20) is negocia


@pytest.mark.parametrize(
    ("posicao", "alvo", "negocia"),
    [
        (0.25, 0.30, True),
        (0.297, 0.30, False),
        (0.0, 0.004, False),
        (0.003, 0.0, False),
    ],
)
def test_sem_banda_e_a_regra_da_p0_1(posicao, alvo, negocia):
    assert brl.deve_negociar(posicao, alvo, None) is negocia


def test_banda_corta_o_giro():
    precos = _precos()
    com_banda = brl.simular(precos, CDI, VOLUMES, brl.Parametros(), CAPITAL)
    sem_banda = brl.simular(precos, CDI, VOLUMES, brl.Parametros(banda=None), CAPITAL)
    assert 0 < com_banda.giro < sem_banda.giro
    assert (com_banda.negociado != 0).to_numpy().sum() < (
        sem_banda.negociado != 0
    ).to_numpy().sum()


def test_quando_negocia_vai_ao_alvo():
    resultado = brl.simular(_precos(), CDI, VOLUMES, SEM_CUSTOS, CAPITAL)
    dias = resultado.negociado.index[(resultado.negociado["BTC"] != 0)]
    assert len(dias) > 0
    exposto = resultado.exposicao.loc[dias, "BTC"]
    alvo = resultado.alvos.loc[dias, "BTC"]
    # Sem custo, o fechamento do dia da ordem fica no alvo (preço do mesmo fechamento).
    assert np.allclose(exposto.to_numpy(), alvo.to_numpy(), atol=1e-9)


# --- simulação ---------------------------------------------------------------------------------


def test_sem_custos_e_sem_banda_e_a_p0_1_sem_cambio():
    """A P0-1b sem spread e sem banda reproduz a P0-1 sem câmbio (a regra é a mesma)."""
    precos = _precos()
    p0_1 = tc.simular(precos, CDI, VOLUMES, tc.Parametros(com_cambio=False), CAPITAL)
    p0_1b = brl.simular(
        precos, CDI, VOLUMES, brl.Parametros(banda=None, spread_por_lado=0.0), CAPITAL
    )
    assert np.allclose(
        p0_1.retorno.to_numpy(), p0_1b.retorno.to_numpy(), rtol=0, atol=1e-12
    )
    assert float(p0_1b.spread.sum()) == 0.0


def test_spread_por_lado_custa_o_valor_negociado():
    precos = _precos()
    sem = brl.simular(precos, CDI, VOLUMES, SEM_CUSTOS, CAPITAL)
    com = brl.simular(
        precos, CDI, VOLUMES, brl.com(SEM_CUSTOS, spread_por_lado=0.003), CAPITAL
    )
    assert float(com.spread.sum()) > 0
    primeiro = com.negociado.abs().sum(axis=1).ne(0).idxmax()
    negociado = float(com.negociado.loc[primeiro].abs().sum())
    assert float(com.spread.loc[primeiro]) == pytest.approx(0.003 * negociado)
    assert float(com.cambio.sum()) == 0.0
    assert com.patrimonio.iloc[-1] < sem.patrimonio.iloc[-1]


def test_par_que_comeca_depois_fica_fora_ate_o_proprio_aquecimento():
    precos = _precos()
    precos.loc[precos.index < DIAS[17], "ETH"] = (
        np.nan
    )  # o ETHBRL começou 17 dias depois
    resultado = brl.simular(precos, CDI, VOLUMES, brl.Parametros(), CAPITAL)
    assert resultado.retorno.index[0] == DIAS[0] + pd.Timedelta(days=365)
    eth = resultado.alvos["ETH"]
    assert (eth[eth.index <= DIAS[17] + pd.Timedelta(days=365)] == 0).all()
    assert np.isfinite(resultado.retorno.to_numpy()).all()


def test_comprar_e_segurar_paga_o_spread_sem_cambio():
    precos = _precos()
    regua = brl.comprar_e_segurar(
        precos["BTC"], VOLUMES["BTC"], brl.Parametros(), CAPITAL
    )
    sem_spread = brl.comprar_e_segurar(
        precos["BTC"],
        VOLUMES["BTC"],
        brl.com(brl.Parametros(), spread_por_lado=0.0),
        CAPITAL,
    )
    assert regua.iloc[0] == pytest.approx(sem_spread.iloc[0] - 0.003)
    assert regua.iloc[1:].equals(sem_spread.iloc[1:])
    assert sem_spread.iloc[0] > -0.005  # sem o IOF e o spread de câmbio da P0-1


def test_cortar_o_futuro_nao_muda_o_passado_e_reexecucao_identica():
    precos = _precos()
    corte = DIAS[700]
    assert brl.cortar_o_futuro_nao_muda_o_passado(
        precos, CDI, VOLUMES, brl.Parametros(), corte, CAPITAL
    )
    a = brl.simular(precos, CDI, VOLUMES, brl.Parametros(), CAPITAL)
    b = brl.simular(precos, CDI, VOLUMES, brl.Parametros(), CAPITAL)
    assert tc.hash_do_resultado(a) == tc.hash_do_resultado(b)


def test_ir_continua_com_a_isencao_de_35_mil():
    precos = _precos()
    resultado = brl.simular(precos, CDI, VOLUMES, brl.Parametros(), 1_000_000.0)
    acima = resultado.ir["vendas"] > tc.PADRAO.isencao_cripto_no_mes
    assert (resultado.ir.loc[~acima, "imposto"] == 0).all()
    assert resultado.meses_acima_da_isencao() == int(acima.sum())
