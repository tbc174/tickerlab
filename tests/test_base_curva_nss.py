"""Curva própria, versão 2: Nelson-Siegel-Svensson (NSS) ao lado da flat-forward (B-24).

Os dados são `dados_de_exemplo/tesouro/`: o formato do arquivo do Tesouro, com 7 LTN e 7 NTN-B Principal
de um dia (taxas ilustrativas, não cotações reais; ver o LEIA-ME da pasta). O critério do backlog: o
ajuste reproduz os vértices do Tesouro com erro abaixo de 1 bp. Isso vale quando os títulos do dia estão
perto de uma curva suave (`taxas_do_dia_amostra.csv`); com ruído de 2 bp entre vizinhos
(`taxas_do_dia_dispersas.csv`) a NSS não o absorve e o erro, medido, passa de 1 bp.
"""

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from base import curva

AMOSTRA = Path("dados_de_exemplo/tesouro/taxas_do_dia_amostra.csv")
PARAMETROS = {
    "beta0": 0.12,
    "beta1": -0.015,
    "beta2": -0.02,
    "beta3": 0.03,
    "tau1": 1.5,
    "tau2": 6.0,
}


DISPERSAS = Path("dados_de_exemplo/tesouro/taxas_do_dia_dispersas.csv")


def _taxas(arquivo: Path = AMOSTRA) -> pd.DataFrame:
    return curva.ler_tesouro_direto(arquivo.read_bytes())


def _do_titulo(titulo: str, arquivo: Path = AMOSTRA) -> pd.DataFrame:
    taxas = _taxas(arquivo)
    return taxas[taxas["titulo"] == titulo]


def _ajustar(prazos: np.ndarray, taxas: np.ndarray) -> dict:
    ajuste = curva.ajustar_nss(prazos, taxas)
    assert ajuste is not None
    return ajuste


def _por_formula(p: dict[str, float], prazo: float) -> float:
    """A fórmula de Svensson escrita por extenso, independente do código testado."""
    x1, x2 = prazo / p["tau1"], prazo / p["tau2"]
    carga1 = (1 - math.exp(-x1)) / x1
    return (
        p["beta0"]
        + p["beta1"] * carga1
        + p["beta2"] * (carga1 - math.exp(-x1))
        + p["beta3"] * ((1 - math.exp(-x2)) / x2 - math.exp(-x2))
    )


def test_formula_nss_bate_com_a_escrita_por_extenso_e_com_os_limites():
    for prazo in (0.25, 1, 2.5, 7, 30):
        assert curva.taxa_nss(PARAMETROS, prazo) == pytest.approx(
            math.expm1(_por_formula(PARAMETROS, prazo)), abs=1e-12
        )
    # limites da fórmula: no prazo zero vale beta0 + beta1; no infinito, beta0
    perto_de_zero = math.log1p(curva.taxa_nss(PARAMETROS, 1e-6))
    assert perto_de_zero == pytest.approx(
        PARAMETROS["beta0"] + PARAMETROS["beta1"], abs=1e-5
    )
    longe = math.log1p(curva.taxa_nss(PARAMETROS, 1e6))
    assert longe == pytest.approx(PARAMETROS["beta0"], abs=1e-4)


def test_recupera_uma_curva_nss_sem_ruido():
    prazos = np.array([0.3, 0.7, 1.2, 2.0, 3.0, 4.5, 6.0, 8.0, 12.0, 20.0])
    taxas = np.array([curva.taxa_nss(PARAMETROS, float(t)) for t in prazos])
    ajuste = _ajustar(prazos, taxas)
    assert ajuste["erro_max_bp"] < 0.05
    for prazo in (0.5, 2.5, 5.0, 10.0, 15.0):  # entre os vértices
        esperado = curva.taxa_nss(PARAMETROS, prazo)
        assert curva.taxa_nss(ajuste, prazo) == pytest.approx(esperado, abs=0.5e-4)


@pytest.mark.parametrize("titulo", ["Tesouro Prefixado", "Tesouro IPCA+"])
def test_reproduz_os_vertices_do_tesouro_com_erro_abaixo_de_1_bp(titulo):
    """LTN para a curva nominal e NTN-B Principal para a real, nos vértices observados."""
    dia = _do_titulo(titulo)
    prazos = dia["prazo_anos"].to_numpy(dtype=float)
    taxas = dia["taxa"].to_numpy(dtype=float)
    ajuste = _ajustar(prazos, taxas)
    assert ajuste["modelo"] == "nss"
    assert ajuste["titulos"] == 7
    erros_bp = [
        abs(curva.taxa_nss(ajuste, float(p)) - t) * 1e4
        for p, t in zip(prazos, taxas, strict=True)
    ]
    assert max(erros_bp) < 1.0
    assert ajuste["erro_max_bp"] == pytest.approx(max(erros_bp), abs=1e-9)


@pytest.mark.parametrize("titulo", ["Tesouro Prefixado", "Tesouro IPCA+"])
def test_com_ruido_de_2_bp_a_nss_nao_absorve_e_o_erro_aparece(titulo):
    """O critério de 1 bp depende do dia: a NSS é suave e deixa o ziguezague, mas diz quanto errou."""
    dia = _do_titulo(titulo, DISPERSAS)
    ajuste = _ajustar(dia["prazo_anos"].to_numpy(float), dia["taxa"].to_numpy(float))
    assert ajuste is not None
    assert 1.0 < ajuste["erro_max_bp"] < 3.0


def test_ajuste_e_deterministico():
    dia = _do_titulo("Tesouro Prefixado")
    args = (dia["prazo_anos"].to_numpy(dtype=float), dia["taxa"].to_numpy(dtype=float))
    assert curva.ajustar_nss(*args) == curva.ajustar_nss(*args)


def test_poucos_titulos_caem_para_nelson_siegel_e_com_menos_de_quatro_nao_ha_curva():
    prazos = np.array([1.0, 2.0, 3.0, 5.0, 8.0])
    taxas = np.array([0.120, 0.125, 0.128, 0.130, 0.131])
    ns = _ajustar(prazos, taxas)
    assert ns["modelo"] == "ns"
    assert ns["beta3"] == 0 and math.isnan(ns["tau2"])  # sem o segundo corcunda
    assert ns["erro_max_bp"] < 5
    assert curva.ajustar_nss(prazos[:3], taxas[:3]) is None
    assert math.isnan(curva.taxa_nss(ns, 0.0))  # prazo zero não existe


def test_curva_padrao_continua_flat_forward():
    taxas = _taxas()
    padrao = curva.montar_curvas(taxas)
    pd.testing.assert_frame_equal(
        padrao, curva.montar_curvas(taxas, metodo="flat_forward")
    )
    assert set(padrao["prazo_anos"]) <= set(curva.VERTICES_ANOS)
    assert (
        padrao[padrao["curva"] == "nominal"]["prazo_anos"].max() == 5
    )  # sem extrapolar
    with pytest.raises(ValueError, match="metodo"):
        curva.montar_curvas(taxas, metodo="spline")


def test_nss_estende_alem_do_titulo_mais_longo_e_diz_que_e_hipotese():
    """A NSS dá o vértice de 10 e 20 anos que a flat-forward recusa; `maior_prazo_anos` o denuncia."""
    curvas = curva.montar_curvas(_taxas(), metodo="nss")
    nominal = curvas[curvas["curva"] == "nominal"]
    assert {10, 20} <= set(nominal["prazo_anos"])
    extrapolados = nominal[nominal["prazo_anos"] > nominal["maior_prazo_anos"]]
    assert set(extrapolados["prazo_anos"]) >= {10, 20}
    assert {"nominal", "real", "implicita"} == set(curvas["curva"])
    assert (curvas["disponivel_em"] > curvas["data_base"]).all()
    implicita = curvas[curvas["curva"] == "implicita"].set_index("prazo_anos")["taxa"]
    nominal_5 = nominal.set_index("prazo_anos")["taxa"][5]
    real_5 = curvas[curvas["curva"] == "real"].set_index("prazo_anos")["taxa"][5]
    assert implicita[5] == pytest.approx((1 + nominal_5) / (1 + real_5) - 1)


def test_nss_sem_olhar_o_futuro():
    """A curva de um dia só usa as taxas do dia: acrescentar o dia seguinte não muda o dia 13."""
    texto = AMOSTRA.read_text()
    cabecalho, *linhas = texto.splitlines()
    amanha = [
        linha.replace("13/10/2026", "14/10/2026").replace(";12,", ";19,")
        for linha in linhas
    ]
    com_amanha = "\n".join([cabecalho, *linhas, *amanha]).encode("latin-1")
    sozinho = curva.montar_curvas(_taxas(), metodo="nss")
    junto = curva.montar_curvas(curva.ler_tesouro_direto(com_amanha), metodo="nss")
    dia_13 = junto[junto["data_base"] == "2026-10-13"].reset_index(drop=True)
    pd.testing.assert_frame_equal(sozinho, dia_13)
    assert (junto["data_base"] == "2026-10-14").any()


@pytest.mark.parametrize("arquivo", [AMOSTRA, DISPERSAS])
def test_extrapolacao_fica_comportada_nao_explode_alem_do_ultimo_titulo(arquivo):
    """Sem penalidade nos betas, a amostra ia a 24% aos 20 anos com o último título a 13%."""
    curvas = curva.montar_curvas(_taxas(arquivo), metodo="nss")
    for nome, grupo in curvas.groupby("curva"):
        taxas = grupo.set_index("prazo_anos")["taxa"]
        assert (taxas > 0).all()
        assert abs(taxas[20] - taxas[5]) < 0.01, (
            nome
        )  # menos de 1 ponto percentual em 15 anos
