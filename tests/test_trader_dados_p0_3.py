"""Dados da ficha P0-3: NTN-B sintética, conversão para reais, cache das séries do BCB e montagem."""

import numpy as np
import pandas as pd
import pytest

from trader.estrategias import dados_p0_3 as dados
from trader.estrategias.carteira_rp import ATIVOS_DE_RISCO

DATAS = pd.bdate_range("2018-01-02", "2020-12-30")


def _ipca(valor=0.0, datas=DATAS):
    meses = pd.period_range(datas[0], datas[-1], freq="M")
    return pd.Series(valor, index=meses.to_timestamp())


def test_ntnb_sintetica_com_juro_constante_rende_o_juro_real():
    taxa = pd.Series(0.06, index=DATAS)
    indice = dados.indice_sintetico_da_ntnb(taxa, _ipca())
    anos = len(DATAS) / 252
    assert indice.iloc[0] == pytest.approx(100.0)
    assert indice.iloc[-1] / indice.iloc[0] == pytest.approx(1.06**anos, rel=0.01)


def test_ntnb_sintetica_cai_quando_o_juro_sobe():
    taxa = pd.Series(0.05, index=DATAS)
    dia = DATAS[300]
    taxa.loc[dia:] = 0.06
    retorno = dados.indice_sintetico_da_ntnb(taxa, _ipca()).pct_change()
    assert -0.06 < retorno.loc[dia] < -0.03  # ~ -duração × 1 ponto, prazo de 5 anos
    assert retorno.loc[DATAS[301]] > 0


def test_ntnb_sintetica_acumula_o_ipca_do_mes_ao_longo_dos_pregoes():
    taxa = pd.Series(0.0, index=DATAS)
    ipca = _ipca()
    ipca.loc["2019-03-01"] = 0.01
    indice = dados.indice_sintetico_da_ntnb(taxa, ipca)
    marco = indice.loc["2019-03"]
    fevereiro = indice.loc["2019-02"]
    assert marco.iloc[-1] / fevereiro.iloc[-1] == pytest.approx(1.01, abs=5e-4)
    assert (
        marco.pct_change().dropna() > 0
    ).all()  # pro rata pelos pregões, não num dia só


def test_ntnb_sintetica_exige_o_ipca_de_todos_os_meses():
    taxa = pd.Series(0.05, index=DATAS)
    with pytest.raises(ValueError, match="IPCA"):
        dados.indice_sintetico_da_ntnb(taxa, _ipca().iloc[:-3])


def test_em_reais_usa_o_ultimo_valor_em_feriado_la_fora():
    usd = pd.Series(
        [10.0, 11.0, 12.0],
        index=pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-07"]),
    )
    brl = pd.Series(
        [4.0, 4.1, 4.2, 4.3],
        index=pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"]),
    )
    em_reais = dados.em_reais(usd, brl)
    assert list(em_reais.index) == list(brl.index)
    assert em_reais.to_numpy() == pytest.approx([40.0, 45.1, 11.0 * 4.2, 12.0 * 4.3])


def test_cache_das_series_do_bcb_baixa_uma_vez_so(tmp_path):
    chamadas = []

    def baixar(inicio, fim):
        chamadas.append((inicio, fim))
        return pd.Series(0.0004, index=pd.bdate_range(inicio, fim))

    a = dados.carregar_com_cache(
        "cdi", pd.Timestamp("2020-01-01"), pd.Timestamp("2020-03-31"), tmp_path, baixar
    )
    b = dados.carregar_com_cache(
        "cdi", pd.Timestamp("2020-01-01"), pd.Timestamp("2020-03-31"), tmp_path, baixar
    )
    assert len(chamadas) == 1 and a.equals(b)
    assert list(tmp_path.glob("cdi_*.parquet"))


def test_montar_precos_alinha_ao_calendario_da_b3_e_corta_no_comeco_comum():
    bova = pd.Series(np.linspace(80, 120, len(DATAS)), index=DATAS)
    ntnb = pd.Series(np.linspace(100, 130, len(DATAS) - 50), index=DATAS[50:])
    usd = pd.bdate_range("2018-01-01", "2020-12-31")
    ouro = pd.Series(np.linspace(1300, 1900, len(usd)), index=usd)
    sp = pd.Series(np.linspace(2700, 3700, len(usd)), index=usd)
    brl = pd.Series(np.linspace(3.3, 5.2, len(usd)), index=usd)
    precos = dados.montar_precos(
        bova11=bova, ntnb=ntnb, ouro_usd=ouro, sp500_usd=sp, brl=brl
    )
    assert list(precos.columns) == list(ATIVOS_DE_RISCO)
    assert precos.index[0] == DATAS[50] and precos.index[-1] == DATAS[-1]
    assert precos.index.isin(DATAS).all()
    assert not precos.isna().any().any()
    assert precos["OURO"].iloc[-1] == pytest.approx(1900 * 5.2, rel=0.01)


def test_volumes_declarados_cobrem_os_quatro_ativos():
    assert set(dados.VOLUME_MEDIO_EM_REAIS) == set(ATIVOS_DE_RISCO)
    assert all(v > 0 for v in dados.VOLUME_MEDIO_EM_REAIS.values())
