"""Alavancagem do núcleo a 1,3x via WIN ou DI1 (pré-registro quant v0.1, seção 7).

A camada A1 a 1,0x é a própria base; a 1,3x soma um futuro com nocional tal que a exposição total
dividida pelo patrimônio dá 1,3 nos dias de ajuste, com a margem em CDI e a rolagem pelo calendário.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from trader import calendario, criterio_quant
from trader.custos_br import CustosBR
from trader.estrategias import alavancagem, dados_alavancagem

DATAS = pd.DatetimeIndex(calendario.pregoes(date(2016, 1, 4), date(2019, 12, 30)))
CDI = pd.Series(0.0004, index=DATAS)
CAPITAL = 100_000.0
SEM_CUSTO = alavancagem.Parametros(
    fator=1.3,
    instrumento="WIN",
    spread_por_lado=0.0,
    custos=CustosBR(
        corretagem_por_ordem=0.0,
        emolumentos_a_vista=0.0,
        tarifa_futuro_por_contrato=0.0,
    ),
)


def _serie(semente: int, media: float, desvio: float) -> pd.Series:
    gerador = np.random.default_rng(semente)
    return pd.Series(gerador.normal(media, desvio, len(DATAS)), index=DATAS)


BASE = _serie(1, 0.0004, 0.006)
EXCESSO = _serie(2, 0.0003, 0.012)


def _primeiros_pregoes_dos_meses(datas: pd.DatetimeIndex) -> pd.DatetimeIndex:
    meses = pd.Series(datas.to_period("M"), index=datas)
    return datas[meses.ne(meses.shift(1)).to_numpy()]


def test_a_1_0x_e_identica_a_base():
    resultado = alavancagem.simular(
        BASE, CDI, EXCESSO, alavancagem.Parametros(fator=1.0), CAPITAL
    )
    assert np.allclose(resultado.retorno, BASE)
    assert (resultado.custos == 0).all()
    assert np.allclose(resultado.exposicao, 1.0)
    assert resultado.rolagens == ()


def test_so_as_duas_versoes_do_pre_registro():
    assert alavancagem.FATORES == criterio_quant.ALAVANCAGENS_DO_NUCLEO == (1.0, 1.3)
    for fator in (1.15, 1.5, 0.8):
        with pytest.raises(ValueError, match="1,0x ou 1,3x"):
            alavancagem.Parametros(fator=fator)
    with pytest.raises(ValueError, match="instrumento"):
        alavancagem.Parametros(instrumento="BIT")


def test_exposicao_e_1_3_vezes_o_patrimonio_nos_dias_de_ajuste():
    resultado = alavancagem.simular(BASE, CDI, EXCESSO, SEM_CUSTO, CAPITAL)
    ajustes = _primeiros_pregoes_dos_meses(DATAS)
    assert np.allclose(resultado.exposicao[ajustes], 1.3)
    assert np.allclose(resultado.exposicao[list(resultado.rolagens)], 1.3)
    assert resultado.exposicao.between(1.2, 1.4).all()
    assert resultado.patrimonio.iloc[0] == pytest.approx(CAPITAL * (1 + BASE.iloc[0]))


def test_margem_rende_cdi_e_o_futuro_rende_o_excesso():
    base = pd.Series(0.001, index=DATAS)
    excesso = pd.Series(0.002, index=DATAS)
    resultado = alavancagem.simular(base, CDI, excesso, SEM_CUSTO, CAPITAL)
    primeiro_ajuste = _primeiros_pregoes_dos_meses(DATAS)[1]
    posicao = DATAS.get_loc(primeiro_ajuste)
    patrimonio = resultado.patrimonio.iloc[posicao]
    margem = alavancagem.MARGEM_DO_FUTURO["WIN"]
    nocional = 0.3 * patrimonio / (1 - margem)
    garantia = margem * nocional
    esperado = (
        (patrimonio - garantia) * 1.001 + garantia * 1.0004 + nocional * 0.002
    ) / patrimonio - 1
    assert resultado.retorno.iloc[posicao + 1] == pytest.approx(esperado)
    assert resultado.margem.iloc[posicao] == pytest.approx(garantia / patrimonio)


def test_rolagem_do_win_nas_datas_do_calendario_e_custa():
    parametros = alavancagem.Parametros(fator=1.3, instrumento="WIN")
    resultado = alavancagem.simular(BASE, CDI, EXCESSO, parametros, CAPITAL)
    esperadas = tuple(
        pd.Timestamp(calendario.rolagem_do_win(ano, mes))
        for ano in range(2016, 2020)
        for mes in calendario.MESES_DO_WIN
    )
    assert resultado.rolagens == esperadas
    assert (resultado.custos[list(esperadas)] > 0).all()
    dias_sem_negocio = DATAS.difference(esperadas).difference(
        _primeiros_pregoes_dos_meses(DATAS)
    )
    assert (resultado.custos[dias_sem_negocio] == 0).all()
    assert resultado.custo_de_rolagem_por_ano() > 0


def test_rolagem_do_di1_quando_o_vertice_de_dois_anos_troca_de_janeiro():
    parametros = alavancagem.Parametros(fator=1.3, instrumento="DI1")
    resultado = alavancagem.simular(BASE, CDI, EXCESSO, parametros, CAPITAL)
    assert len(resultado.rolagens) == 4  # uma troca por ano, perto de julho
    for dia in resultado.rolagens:
        vespera = DATAS[DATAS.get_loc(dia) - 1]
        assert calendario.di1_de_janeiro(dia.date(), 2) != calendario.di1_de_janeiro(
            vespera.date(), 2
        )
        assert dia.month == 7


def test_conta_os_dias_em_que_a_margem_passou_do_aviso():
    folgada = alavancagem.simular(BASE, CDI, EXCESSO, SEM_CUSTO, CAPITAL)
    assert folgada.dias_com_margem_acima() == 0
    apertada = alavancagem.simular(
        BASE, CDI, EXCESSO, alavancagem.com(SEM_CUSTO, margem=0.9), CAPITAL
    )
    assert apertada.dias_com_margem_acima() == len(DATAS)
    assert alavancagem.MARGEM_DE_AVISO == criterio_quant.MARGEM_DE_AVISO == 0.30


def test_queda_maior_que_35_por_cento_volta_a_1_0x_sozinha():
    """Um dia de −30% na base e no índice: a 1,0x cai 30% (fica); a 1,3x cai ≈ 39% (volta a 1,0x)."""
    base = pd.Series(0.0005, index=DATAS)
    excesso = pd.Series(0.0, index=DATAS)
    base.iloc[300] = -0.30
    excesso.iloc[300] = -0.30
    a_1_3 = alavancagem.simular(base, CDI, excesso, SEM_CUSTO, CAPITAL)
    a_1_0 = alavancagem.simular(
        base, CDI, excesso, alavancagem.com(SEM_CUSTO, fator=1.0), CAPITAL
    )
    assert alavancagem.cai_para_1_0x(a_1_3)
    assert not alavancagem.cai_para_1_0x(a_1_0)
    assert alavancagem.versao_que_entra(aprovada_1_0=True, aprovada_1_3=False) == 1.0
    assert alavancagem.versao_que_entra(aprovada_1_0=True, aprovada_1_3=True) == 1.3
    assert alavancagem.versao_que_entra(aprovada_1_0=False, aprovada_1_3=False) is None


def test_cortar_o_futuro_nao_muda_o_passado_e_reexecucao_identica():
    parametros = alavancagem.Parametros(fator=1.3, instrumento="WIN")
    inteiro = alavancagem.simular(BASE, CDI, EXCESSO, parametros, CAPITAL)
    corte = DATAS[700]
    assert alavancagem.cortar_o_futuro_nao_muda_o_passado(
        BASE, CDI, EXCESSO, parametros, corte, CAPITAL
    )
    de_novo = alavancagem.simular(BASE, CDI, EXCESSO, parametros, CAPITAL)
    assert alavancagem.hash_do_resultado(inteiro) == alavancagem.hash_do_resultado(
        de_novo
    )


def test_estresse_dobra_os_custos_de_corretora_bolsa_e_spread():
    base = alavancagem.Parametros(fator=1.3, instrumento="WIN")
    estresse = base.em_estresse(2.0)
    assert estresse.spread_por_lado == 2 * base.spread_por_lado
    assert (
        estresse.custos.tarifa_futuro_por_contrato
        == 2 * base.custos.tarifa_futuro_por_contrato
    )
    normal = alavancagem.simular(BASE, CDI, EXCESSO, base, CAPITAL)
    dobrado = alavancagem.simular(BASE, CDI, EXCESSO, estresse, CAPITAL)
    assert dobrado.custos.sum() == pytest.approx(2 * normal.custos.sum(), rel=0.02)


def test_especificacao_vai_para_o_registro_em_tipos_simples():
    spec = alavancagem.Parametros(fator=1.3, instrumento="DI1").especificacao()
    assert spec["alavancagem"] == 1.3 and spec["instrumento"] == "DI1"
    assert spec["margem"] == alavancagem.MARGEM_DO_FUTURO["DI1"]
    assert spec["valor_do_contrato"] == alavancagem.VALOR_DO_CONTRATO["DI1"]
    assert isinstance(spec["custos"], dict)


# --- as pernas sintéticas -----------------------------------------------------------------------


def test_indice_prefixado_com_taxa_constante_rende_o_carry():
    taxa = pd.Series(0.10, index=DATAS)
    indice = dados_alavancagem.indice_prefixado(taxa, prazo_anos=2.0)
    assert indice.iloc[0] == 100.0
    assert np.allclose(indice.pct_change().dropna(), 1.1 ** (1 / 252) - 1)


def test_indice_prefixado_sobe_quando_a_taxa_cai():
    taxa = pd.Series(0.10, index=DATAS)
    taxa.iloc[10:] = 0.09
    indice = dados_alavancagem.indice_prefixado(taxa, prazo_anos=2.0)
    carry = 1.1 ** (1 / 252) - 1
    assert indice.pct_change().iloc[10] > carry + 0.015  # ≈ 2 anos × 1 ponto
    assert indice.pct_change().iloc[11] == pytest.approx(1.09 ** (1 / 252) - 1)


def test_excessos_sinteticos_descontam_o_cdi():
    bova11 = pd.Series(100 * np.cumprod(1 + BASE), index=DATAS)
    win = dados_alavancagem.excesso_do_win(bova11, CDI)
    assert win.index.equals(DATAS)
    assert win.iloc[0] == 0.0
    assert win.iloc[5] == pytest.approx(BASE.iloc[5] - 0.0004)
    curva = pd.DataFrame(
        {
            "data_base": list(DATAS[::2]),
            "curva": "nominal",
            "prazo_anos": 2.0,
            "taxa": 0.10,
        }
    )
    di1 = dados_alavancagem.excesso_do_di1(curva, CDI, DATAS)
    assert di1.index.equals(DATAS)
    assert di1.iloc[1] == pytest.approx(1.1 ** (1 / 252) - 1 - 0.0004)
    so_real = curva.assign(curva="real")
    with pytest.raises(ValueError, match="nominal"):
        dados_alavancagem.excesso_do_di1(so_real, CDI, DATAS)
