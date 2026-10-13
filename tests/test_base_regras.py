"""Regras fixas do selo "dado em conferência" (ADR 0028, item 2; série 1, PR 1)."""

import pandas as pd

from base.contas_cvm import COLUNAS, LeituraDeContas
from base.regras import (
    r1_ativo_passivo,
    r2_subtotais,
    r3_escala,
    r4_impossivel,
    r9_repetidas,
    r10_lucro_em_branco,
    r11_mae_em_branco,
)

CNPJ = "11.111.111/0001-11"
REFERENCIA = pd.Timestamp("2024-12-31")


def _conta(
    conta: str,
    valor: float,
    demonstracao: str = "BPA",
    grupo: str = "con",
    ordem: str = "ultimo",
    cnpj: str = CNPJ,
    referencia: pd.Timestamp = REFERENCIA,
    fim: pd.Timestamp | None = None,
    descricao: str | None = None,
) -> dict:
    return {
        "cnpj": cnpj,
        "empresa": "EMPRESA TESTE S.A.",
        "documento": "DFP",
        "referencia": referencia,
        "versao": 1,
        "demonstracao": demonstracao,
        "grupo": grupo,
        "ordem": ordem,
        "inicio": pd.NaT,
        "fim": referencia if fim is None else fim,
        "conta": conta,
        "descricao": descricao or f"conta {conta}",
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


# --- R3: escala suspeita (salto de ~1000 vezes contra o documento anterior) ------------------------

ANO_PASSADO = pd.Timestamp("2023-12-31")


def test_r3_mesmo_periodo_mil_vezes_menor_no_documento_novo():
    """Como na Alubar: o mesmo período vale mil vezes menos num documento que no outro."""
    anterior = _contas(_conta("1", 134.3e6, referencia=ANO_PASSADO))
    atual = _contas(_conta("1", 134.3e3, ordem="penultimo", fim=ANO_PASSADO))

    achados = r3_escala(atual, anterior)

    assert len(achados) == 1
    assert (achados[0].regra, achados[0].conta) == ("R3", "1")
    assert "mil vezes" in achados[0].porque


def test_r3_salto_de_mil_vezes_entre_periodos_seguidos():
    anterior = _contas(_conta("1", 100e6, referencia=ANO_PASSADO))
    atual = _contas(_conta("1", 100e9))

    assert [a.regra for a in r3_escala(atual, anterior)] == ["R3"]


def test_r3_crescimento_normal_nao_dispara():
    anterior = _contas(_conta("1", 100e6, referencia=ANO_PASSADO))
    atual = _contas(
        _conta("1", 130e6), _conta("1", 100e6, ordem="penultimo", fim=ANO_PASSADO)
    )

    assert r3_escala(atual, anterior) == []


def test_r3_sem_documento_anterior_nao_dispara():
    atual = _contas(_conta("1", 100e9))

    assert r3_escala(atual, _contas()) == []


# --- R4: valor impossível --------------------------------------------------------------------------


def test_r4_ativo_total_negativo():
    achados = r4_impossivel(_contas(_conta("1", -5e6)))

    assert [(a.regra, a.conta) for a in achados] == [("R4", "1")]


def test_r4_patrimonio_negativo_nao_e_impossivel():
    contas = _contas(_conta("1", 5e6), _conta("2.03", -8e6, demonstracao="BPP"))

    assert r4_impossivel(contas) == []


# --- R9: linhas repetidas no arquivo da CVM ------------------------------------------------------


def test_r9_um_achado_por_documento_com_repetidas():
    repetidas = pd.DataFrame(
        [
            {
                "cnpj": CNPJ,
                "referencia": REFERENCIA,
                "demonstracao": "DRE",
                "grupo": "con",
                "linhas": 3,
            }
        ]
    )
    leitura = LeituraDeContas(
        _contas(_conta("3.11", 1e6, demonstracao="DRE")), repetidas
    )

    achados = r9_repetidas(leitura)

    assert len(achados) == 1
    assert (achados[0].regra, achados[0].valor, achados[0].documento) == (
        "R9",
        3.0,
        "DFP",
    )
    assert "repetid" in achados[0].porque


# --- R10: lucro em branco com receita ------------------------------------------------------------


def _receita(valor: float) -> dict:
    return _conta(
        "3.01",
        valor,
        demonstracao="DRE",
        descricao="Receita de Venda de Bens e/ou Serviços",
    )


def _lucro(valor: float, conta: str = "3.11") -> dict:
    return _conta(
        conta,
        valor,
        demonstracao="DRE",
        descricao="Lucro/Prejuízo Consolidado do Período",
    )


def test_r10_lucro_zerado_com_receita():
    """Como no Banco Alfa: lucro do período zerado numa empresa com receita."""
    achados = r10_lucro_em_branco(_contas(_receita(900e6), _lucro(0.0)))

    assert [(a.regra, a.conta) for a in achados] == [("R10", "3.11")]


def test_r10_empresa_sem_receita_e_sem_lucro_nao_dispara():
    assert r10_lucro_em_branco(_contas(_receita(0.0), _lucro(0.0))) == []


def test_r10_acha_o_lucro_pela_descricao_e_nao_pelo_codigo():
    """Em parte das empresas a 3.11 é a reversão dos juros sobre capital e o lucro fica na 3.13."""
    reversao = _conta(
        "3.11",
        0.0,
        demonstracao="DRE",
        descricao="Reversão dos Juros sobre Capital Próprio",
    )
    com_lucro = _contas(_receita(900e6), reversao, _lucro(17e6, conta="3.13"))
    sem_lucro = _contas(_receita(900e6), reversao, _lucro(0.0, conta="3.13"))

    assert r10_lucro_em_branco(com_lucro) == []
    assert [a.conta for a in r10_lucro_em_branco(sem_lucro)] == ["3.13"]
