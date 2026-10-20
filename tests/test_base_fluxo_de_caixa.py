"""Conferência da DFC (série T1): o caixa do começo mais a variação dá o caixa do fim, e as atividades
somam a variação. Bater com o caixa do balanço é medida de qualidade, não regra: bancos e
seguradoras chamam de "caixa" coisas diferentes nos dois quadros (85,8% dos DFP consolidados de
2023 batem; medido em 19/10/2026)."""

import pandas as pd

from base.contas_cvm import ler_contas
from base.fluxo_de_caixa import TOLERANCIA, conferir_dfc
from tests.test_base_contas_cvm import ZIP_REAL

A = "11.111.111/0001-11"
FIM = pd.Timestamp("2023-12-31")
M = 1_000_000.0  # valores em milhões de reais, bem acima da tolerância


def _linha(demonstracao, conta, valor, ordem="ultimo", cnpj=A):
    return {
        "cnpj": cnpj,
        "empresa": "EMPRESA A",
        "documento": "DFP",
        "referencia": FIM,
        "versao": 1,
        "demonstracao": demonstracao,
        "grupo": "con",
        "ordem": ordem,
        "inicio": pd.NaT if demonstracao == "BPA" else pd.Timestamp("2023-01-01"),
        "fim": FIM,
        "conta": conta,
        "descricao": "",
        "conta_fixa": True,
        "valor": valor * M,
    }


def _dfc(inicial=100.0, final=160.0, operacional=90.0, cambio=None, caixa=160.0):
    linhas = [
        _linha("DFC_MI", "6.01", operacional),
        _linha("DFC_MI", "6.02", -20.0),
        _linha("DFC_MI", "6.03", -10.0),
        _linha("DFC_MI", "6.05", 60.0),
        _linha("DFC_MI", "6.05.01", inicial),
        _linha("DFC_MI", "6.05.02", final),
        _linha("DRE", "3.05", 999.0),  # outras demonstrações não atrapalham
    ]
    if cambio is not None:
        linhas.append(_linha("DFC_MI", "6.04", cambio))
    if caixa is not None:
        linhas.append(_linha("BPA", "1.01.01", caixa))
    return pd.DataFrame(linhas)


def _um(conferencia):
    assert len(conferencia) == 1
    return conferencia.iloc[0]


def test_dfc_que_fecha_e_bate_com_o_balanco():
    linha = _um(conferir_dfc(_dfc()))
    assert (linha["fecha"], linha["soma_fecha"], linha["bate_com_balanco"]) == (
        True,
        True,
        True,
    )
    assert (linha["saldo_inicial"], linha["saldo_final"], linha["variacao"]) == (
        100.0 * M,
        160.0 * M,
        60.0 * M,
    )
    assert linha["demonstracao"] == "DFC_MI"


def test_diferenca_de_arredondamento_ate_a_tolerancia_ainda_fecha():
    assert _um(conferir_dfc(_dfc(final=160.0 + TOLERANCIA / M)))["fecha"]
    assert not _um(conferir_dfc(_dfc(final=160.0 + 2 * TOLERANCIA / M)))["fecha"]


def test_atividades_que_nao_somam_a_variacao():
    linha = _um(conferir_dfc(_dfc(operacional=50.0)))
    assert linha["fecha"] and not linha["soma_fecha"]


def test_variacao_cambial_entra_na_soma():
    linha = _um(conferir_dfc(_dfc(operacional=80.0, cambio=10.0)))
    assert linha["soma_fecha"]


def test_caixa_do_balanco_diferente_nao_bate_e_sem_caixa_fica_vazio():
    assert not _um(conferir_dfc(_dfc(caixa=150.0)))["bate_com_balanco"]
    assert pd.isna(_um(conferir_dfc(_dfc(caixa=None)))["bate_com_balanco"])


def test_sem_dfc_devolve_tabela_vazia():
    assert conferir_dfc(_dfc().query("demonstracao != 'DFC_MI'")).empty


def test_zip_real_fecha_em_todas_e_bate_nas_empresas_que_nao_sao_banco():
    contas = ler_contas(ZIP_REAL.read_bytes(), "DFP").contas
    conferencia = conferir_dfc(contas).set_index(["cnpj", "ordem"])
    assert len(conferencia) == 8  # 4 empresas, 2 exercícios
    assert conferencia["fecha"].all() and conferencia["soma_fecha"].all()
    petrobras, klabin, bb = (
        "33.000.167/0001-01",
        "84.429.695/0001-11",
        "00.000.000/0001-91",
    )
    assert conferencia.loc[[petrobras, klabin], "bate_com_balanco"].all()
    assert not conferencia.loc[
        bb, "bate_com_balanco"
    ].any()  # banco: "caixa" é outra coisa
