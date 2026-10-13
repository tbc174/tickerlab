"""Regras fixas do selo "dado em conferência" (ADR 0028, item 2; série 1, PR 1)."""

import pandas as pd

from base.contas_cvm import COLUNAS
from base.regras import r1_ativo_passivo, r2_subtotais, r11_mae_em_branco

CNPJ = "11.111.111/0001-11"
REFERENCIA = pd.Timestamp("2024-12-31")


def _conta(
    conta: str,
    valor: float,
    demonstracao: str = "BPA",
    grupo: str = "con",
    ordem: str = "ultimo",
    cnpj: str = CNPJ,
) -> dict:
    return {
        "cnpj": cnpj,
        "empresa": "EMPRESA TESTE S.A.",
        "documento": "DFP",
        "referencia": REFERENCIA,
        "versao": 1,
        "demonstracao": demonstracao,
        "grupo": grupo,
        "ordem": ordem,
        "inicio": pd.NaT,
        "fim": REFERENCIA,
        "conta": conta,
        "descricao": f"conta {conta}",
        "conta_fixa": True,
        "valor": valor,
    }


def _contas(*linhas: dict) -> pd.DataFrame:
    return pd.DataFrame(list(linhas), columns=list(COLUNAS))


# --- R1: ativo total diferente do passivo total --------------------------------------------------


def test_r1_dispara_quando_ativo_difere_do_passivo():
    contas = _contas(_conta("1", 100e6), _conta("2", 90e6, demonstracao="BPP"))

    achados = r1_ativo_passivo(contas)

    assert len(achados) == 1
    achado = achados[0]
    assert (achado.regra, achado.cnpj, achado.conta, achado.grupo) == (
        "R1",
        CNPJ,
        "1",
        "con",
    )
    assert (achado.valor, achado.valor_esperado) == (100e6, 90e6)
    assert achado.referencia == REFERENCIA
    assert "ativo total" in achado.porque.lower()


def test_r1_tolerancia_de_arredondamento():
    pequena = _contas(_conta("1", 100e6), _conta("2", 100e6 - 1000, demonstracao="BPP"))
    relativa = _contas(_conta("1", 1e9), _conta("2", 1e9 - 500_000, demonstracao="BPP"))

    assert r1_ativo_passivo(pequena) == []
    assert r1_ativo_passivo(relativa) == []  # 0,05%: abaixo de 0,1%


def test_r1_so_olha_o_periodo_do_proprio_documento():
    contas = _contas(
        _conta("1", 100e6, ordem="penultimo"),
        _conta("2", 50e6, demonstracao="BPP", ordem="penultimo"),
    )

    assert r1_ativo_passivo(contas) == []


def test_r1_cada_grupo_separado():
    contas = _contas(
        _conta("1", 100e6),
        _conta("2", 100e6, demonstracao="BPP"),
        _conta("1", 80e6, grupo="ind"),
        _conta("2", 70e6, demonstracao="BPP", grupo="ind"),
    )

    achados = r1_ativo_passivo(contas)

    assert [a.grupo for a in achados] == ["ind"]


# --- R2: subtotal que não fecha --------------------------------------------------------------------


def test_r2_soma_das_filhas_nao_fecha():
    contas = _contas(_conta("1", 100e6), _conta("1.01", 40e6), _conta("1.02", 50e6))

    achados = r2_subtotais(contas)

    assert len(achados) == 1
    achado = achados[0]
    assert (achado.regra, achado.conta, achado.valor, achado.valor_esperado) == (
        "R2",
        "1",
        100e6,
        90e6,
    )


def test_r2_filhas_que_fecham_nao_disparam():
    contas = _contas(_conta("1", 100e6), _conta("1.01", 40e6), _conta("1.02", 60e6))

    assert r2_subtotais(contas) == []


def test_r2_neta_nao_entra_na_soma_da_avo():
    contas = _contas(
        _conta("1", 100e6),
        _conta("1.01", 40e6),
        _conta("1.01.01", 40e6),
        _conta("1.02", 60e6),
    )

    assert r2_subtotais(contas) == []


def test_r2_conta_com_uma_filha_so_e_ignorada():
    contas = _contas(_conta("1.01", 40e6), _conta("1.01.01", 10e6))

    assert r2_subtotais(contas) == []


def test_r2_vale_so_para_o_balanco():
    contas = _contas(
        _conta("3.04", -100e6, demonstracao="DRE"),
        _conta("3.04.01", -10e6, demonstracao="DRE"),
        _conta("3.04.02", -10e6, demonstracao="DRE"),
    )

    assert r2_subtotais(contas) == []


def test_r2_filhas_zeradas_nao_disparam():
    """Preencher só a conta mãe e deixar as filhas zeradas é hábito comum (2.200 casos na DFP
    2022), não número errado."""
    contas = _contas(
        _conta("1.01", 100e6), _conta("1.01.01", 0.0), _conta("1.01.02", 0.0)
    )

    assert r2_subtotais(contas) == []


def test_r2_mae_em_branco_fica_para_a_r11():
    contas = _contas(
        _conta("2.01", 0.0), _conta("2.01.01", 5e9), _conta("2.01.02", 2.9e9)
    )

    assert r2_subtotais(contas) == []


# --- R11: conta mãe em branco com as filhas preenchidas --------------------------------------------


def test_r11_mae_em_branco_com_filhas_preenchidas():
    contas = _contas(
        _conta("2.01", 0.0), _conta("2.01.01", 5e9), _conta("2.01.02", 2.9e9)
    )

    achados = r11_mae_em_branco(contas)

    assert len(achados) == 1
    achado = achados[0]
    assert (achado.regra, achado.conta, achado.valor, achado.valor_esperado) == (
        "R11",
        "2.01",
        0.0,
        7.9e9,
    )
    assert "em branco" in achado.porque


def test_r11_nao_dispara_com_tudo_zerado_ou_mae_preenchida():
    zerado = _contas(
        _conta("2.01", 0.0), _conta("2.01.01", 0.0), _conta("2.01.02", 0.0)
    )
    preenchida = _contas(
        _conta("2.01", 1e6), _conta("2.01.01", 5e5), _conta("2.01.02", 5e5)
    )

    assert r11_mae_em_branco(zerado) == []
    assert r11_mae_em_branco(preenchida) == []
