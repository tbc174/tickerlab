"""P0-8: o filtro de regime em dados sintéticos (cortes, aquecimento neutro, atraso e sem olhar o futuro)."""

import numpy as np
import pandas as pd
import pytest

from src import regimes
from trader import criterio_quant
from trader.estrategias import regime

DIAS = pd.bdate_range("2010-01-04", periods=900)


def _precos(semente: int = 0, deriva: float = 0.0003) -> pd.Series:
    gerador = np.random.default_rng(semente)
    retornos = gerador.normal(deriva, 0.015, len(DIAS))
    return pd.Series(100 * np.cumprod(1 + retornos), index=DIAS)


def test_media_de_200_dias_liga_acima_e_e_vazia_no_aquecimento():
    subida = pd.Series(np.linspace(100, 200, len(DIAS)), index=DIAS)
    acima = regime.acima_da_media(subida)
    assert acima.iloc[: regime.DIAS_DA_MEDIA - 1].isna().all()
    assert acima.iloc[regime.DIAS_DA_MEDIA :].all()
    assert not regime.acima_da_media(subida[::-1].set_axis(DIAS)).dropna().any()


def test_queda_desliga_abaixo_de_20_por_cento_do_pico():
    precos = pd.Series([100.0, 120.0, 100.0, 95.0, 97.0, 130.0], index=DIAS[:6])
    # 100/120 − 1 = −16,7% liga; 95/120 − 1 = −20,8% desliga; 97/120 − 1 = −19,2% liga
    assert list(regime.queda_acima_do_limite(precos)) == [
        True,
        True,
        True,
        False,
        True,
        True,
    ]


def test_vol_desliga_no_topo_da_propria_historia():
    gerador = np.random.default_rng(1)
    retornos = gerador.normal(0, 0.01, len(DIAS))
    retornos[-30:] = gerador.normal(0, 0.06, 30)  # a vol sobe muito no fim
    precos = pd.Series(100 * np.cumprod(1 + retornos), index=DIAS)
    vol = regime.vol_fora_do_topo(precos)
    minimo = regime.DIAS_DA_VOL + regimes.HISTORICO_MINIMO_DA_VOLATILIDADE - 1
    assert vol.iloc[:minimo].isna().all()
    assert not vol.iloc[-5:].any()
    assert vol.iloc[minimo:-40].mean() > 0.85


def test_percentil_e_contra_o_passado():
    serie = pd.Series(np.arange(300, dtype=float), index=DIAS[:300])
    percentil = regime.percentil_na_historia(serie)
    assert percentil.iloc[-1] == 1.0  # cada valor é o maior até ali
    assert percentil.iloc[: regime.HISTORICO_MINIMO_DO_PERCENTIL - 1].isna().all()


def test_selic_alta_esperada_desliga_e_vale_ate_o_proximo_focus():
    precos = _precos()
    semanas = DIAS[::5]
    mudanca = pd.Series(0.0, index=semanas)
    mudanca.iloc[100:110] = 0.5  # o Focus passa a esperar alta
    tabela = regime.estado(precos, selic=mudanca)
    inicio, fim = semanas[100], semanas[110]
    assert not tabela.loc[inicio : fim - pd.Timedelta(days=1), "selic"].any()
    assert tabela.loc[: inicio - pd.Timedelta(days=1), "selic"].all()
    assert not tabela.loc[inicio : fim - pd.Timedelta(days=1), "ligado"].any()


def test_extremos_do_funding_e_do_open_interest():
    gerador = np.random.default_rng(2)
    funding = pd.Series(gerador.normal(0.05, 0.02, len(DIAS)), index=DIAS)
    funding.iloc[-1] = 0.50  # extremo de cima
    funding.iloc[-2] = -0.50  # extremo de baixo
    dentro = regime.fora_dos_extremos(funding)
    assert not dentro.iloc[-1] and not dentro.iloc[-2]
    assert dentro.iloc[regime.HISTORICO_MINIMO_DO_PERCENTIL : -2].mean() > 0.7
    oi = pd.Series(np.linspace(1e6, 2e6, len(DIAS)), index=DIAS)
    tabela = regime.estado(_precos(), funding=funding, open_interest=oi)
    assert {"funding", "open_interest"} <= set(tabela.columns)


def test_sem_historia_o_filtro_e_neutro():
    curta = _precos().iloc[:50]
    tabela = regime.estado(curta)
    assert tabela[["media_200", "vol_21"]].isna().all().all()
    assert tabela["queda"].notna().all()  # a queda do pico vale desde o 1º preço
    assert tabela["ligado"].all()


def test_entrada_ausente_nao_entra_no_filtro():
    tabela = regime.estado(_precos())
    assert list(tabela.columns) == [*regime.CONDICOES_DE_PRECO, "ligado"]


@pytest.mark.parametrize("semente", range(5))
def test_cortar_o_futuro_nao_muda_o_passado(semente):
    precos = _precos(semente, deriva=0.0)
    gerador = np.random.default_rng(semente + 10)
    funding = pd.Series(gerador.normal(0, 0.1, len(DIAS)), index=DIAS)
    completo = regime.estado(precos, funding=funding)
    corte = DIAS[700]
    cortado = regime.estado(precos[:corte], funding=funding[:corte])
    pd.testing.assert_frame_equal(completo.loc[:corte], cortado)


def test_aplicar_respeita_o_atraso_da_execucao():
    retorno = pd.Series(0.01, index=DIAS[:6])
    cdi = pd.Series(0.0001, index=DIAS[:6])
    ligado = pd.Series([True, True, False, False, True, True], index=DIAS[:6])
    com = regime.aplicar(retorno, cdi, ligado)
    # desligado em D=2: executa no fechamento de 3, o retorno de 4 é o primeiro no CDI
    assert list(com) == pytest.approx([0.01, 0.01, 0.01, 0.01, 0.0001, 0.0001])


def test_aplicar_cobra_cada_troca_no_dia_da_execucao():
    retorno = pd.Series(0.0, index=DIAS[:6])
    cdi = pd.Series(0.0, index=DIAS[:6])
    ligado = pd.Series([True, False, False, True, True, True], index=DIAS[:6])
    com = regime.aplicar(retorno, cdi, ligado, custo_por_troca=0.001)
    assert list(com) == pytest.approx([0, 0, -0.001, 0, -0.001, 0])


def test_aplicar_sempre_ligado_e_a_estrategia_sem_filtro():
    retorno = _precos().pct_change().fillna(0.0)
    cdi = pd.Series(0.0003, index=DIAS)
    ligado = pd.Series(True, index=DIAS)
    pd.testing.assert_series_equal(
        regime.aplicar(retorno, cdi, ligado, custo_por_troca=0.01), retorno
    )


def test_o_estado_de_hoje_nao_decide_o_retorno_de_hoje_nem_de_amanha():
    retorno = _precos(3).pct_change().fillna(0.0)
    cdi = pd.Series(0.0003, index=DIAS)
    ligado = pd.Series(True, index=DIAS)
    base = regime.aplicar(retorno, cdi, ligado)
    ligado.iloc[500] = False
    mudou = regime.aplicar(retorno, cdi, ligado)
    diferentes = DIAS[(base != mudou).to_numpy()]
    assert list(diferentes) == [DIAS[502]]


@pytest.mark.parametrize(
    ("argumentos", "entra"),
    [
        ((0.90, 0.95, -0.30, -0.25), True),
        ((0.90, 0.90, -0.30, -0.25), False),  # o DSR precisa melhorar
        ((0.90, 0.95, -0.30, -0.31), False),  # a queda não pode piorar
        ((0.90, 0.95, -0.30, -0.30, 0.20, 0.25), False),  # nem o PBO
        ((0.90, 0.95, -0.30, -0.30, 0.20, 0.20), True),
    ],
)
def test_regra_da_ficha_para_o_filtro_entrar(argumentos, entra):
    assert regime.filtro_entra(*argumentos) is entra


def test_cortes_estao_no_texto_da_ficha():
    texto = criterio_quant.ARQUIVO.read_text(encoding="utf-8")
    ficha = texto.split("### Ficha P0-8")[1].split("## 10.")[0]
    assert f"média de {regime.DIAS_DA_MEDIA} dias" in ficha
    assert f"vol realizada de {regime.DIAS_DA_VOL} dias" in ficha
    assert f"abaixo de {regime.PERCENTIL_MAXIMO_DA_VOL:.0%}" in ficha
    assert f"acima de −{abs(regime.QUEDA_MAXIMA_DO_ATIVO):.0%}" in ficha
    assert "com e sem" in ficha
