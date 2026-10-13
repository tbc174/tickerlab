"""Regras fixas do selo "dado em conferência" (ADR 0028, item 2; série 1, PR 1)."""

import pandas as pd

from base.contas_cvm import COLUNAS, LeituraDeContas
from base.regras import (
    r1_ativo_passivo,
    r2_subtotais,
    r3_escala,
    r4_impossivel,
    r5_reapresentado,
    r6_refeito_no_seguinte,
    r7_salto_fora_do_padrao,
    r8_atraso,
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
    inicio: pd.Timestamp | None = None,
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
        "inicio": pd.NaT if inicio is None else inicio,
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


# --- R6: número refeito pela empresa no balanço seguinte ------------------------------------------

DFP_2023 = pd.Timestamp("2023-12-31")
ENTREGA_DA_DFP_2023 = pd.Timestamp("2024-03-28")


def _lucro_de_2023(valor: float, referencia: pd.Timestamp, ordem: str) -> dict:
    """O lucro do ano de 2023: "último" na DFP 2023, "penúltimo" na DFP 2024."""
    return _conta(
        "3.11",
        valor,
        demonstracao="DRE",
        descricao="Lucro/Prejuízo Consolidado do Período",
        referencia=referencia,
        ordem=ordem,
        inicio=pd.Timestamp("2023-01-01"),
        fim=DFP_2023,
    )


def test_r6_compara_ultimo_de_um_ano_com_penultimo_do_seguinte():
    """Como na CLI Sul: lucro de R$ 24,2 mi refeito para prejuízo de R$ 11,0 mi."""
    do_ano = _contas(_lucro_de_2023(24.2e6, DFP_2023, "ultimo"))
    seguinte = _contas(_lucro_de_2023(-11.0e6, REFERENCIA, "penultimo"))

    achados = r6_refeito_no_seguinte(do_ano, seguinte, {CNPJ: ENTREGA_DA_DFP_2023})

    assert len(achados) == 1
    achado = achados[0]
    assert (achado.regra, achado.conta, achado.valor, achado.valor_esperado) == (
        "R6",
        "3.11",
        24.2e6,
        -11.0e6,
    )
    assert "de lucro para prejuízo" in achado.porque


def test_r6_data_do_achado_e_a_da_dfp_seguinte():
    """O número só passa a ser "refeito" quando a DFP seguinte fica pública: nada de olhar o futuro."""
    do_ano = _contas(_conta("1", 100e6, referencia=DFP_2023))
    seguinte = _contas(_conta("1", 90e6, ordem="penultimo", fim=DFP_2023))

    achado = r6_refeito_no_seguinte(do_ano, seguinte, {CNPJ: ENTREGA_DA_DFP_2023})[0]

    assert achado.valido_desde == ENTREGA_DA_DFP_2023
    assert (
        achado.referencia == DFP_2023
    )  # o achado é do documento que tinha o número original


def test_r6_ignora_diferenca_abaixo_de_0_1_pct():
    do_ano = _contas(_conta("1", 1e9, referencia=DFP_2023))
    seguinte = _contas(_conta("1", 1e9 + 500_000, ordem="penultimo", fim=DFP_2023))

    assert r6_refeito_no_seguinte(do_ano, seguinte, {CNPJ: ENTREGA_DA_DFP_2023}) == []


def test_r6_olha_so_as_contas_principais():
    """3,9% das contas mudam de um ano para o outro, quase tudo reclassificação pequena."""
    do_ano = _contas(_conta("1.01.02", 10e6, referencia=DFP_2023))
    seguinte = _contas(_conta("1.01.02", 15e6, ordem="penultimo", fim=DFP_2023))

    assert r6_refeito_no_seguinte(do_ano, seguinte, {CNPJ: ENTREGA_DA_DFP_2023}) == []


def test_r6_patrimonio_liquido_achado_pela_descricao():
    pl = {"demonstracao": "BPP", "descricao": "Patrimônio Líquido Consolidado"}
    do_ano = _contas(_conta("2.07", 500e6, referencia=DFP_2023) | pl)
    seguinte = _contas(_conta("2.07", 450e6, ordem="penultimo", fim=DFP_2023) | pl)

    achados = r6_refeito_no_seguinte(do_ano, seguinte, {CNPJ: ENTREGA_DA_DFP_2023})

    assert [a.conta for a in achados] == ["2.07"]


# --- R5: reapresentado com número diferente ------------------------------------------------------

ENTREGA_DA_V2 = pd.Timestamp("2025-03-30")


def _versao(valor: float, versao: int) -> dict:
    return _lucro(valor) | {"versao": versao}


def test_r5_nao_dispara_quando_so_a_versao_muda():
    """74% das reapresentações da DFP 2022 não mudaram nenhum número (prova do ENET)."""
    antiga = _contas(_receita(900e6) | {"versao": 1}, _versao(50e6, 1))
    nova = _contas(_receita(900e6) | {"versao": 2}, _versao(50e6, 2))

    assert r5_reapresentado(antiga, nova, "Inclusão de anexo", ENTREGA_DA_V2) == []


def test_r5_dispara_com_numero_diferente_e_traz_o_motivo():
    """Como na Allos: lucro de R$ 842,1 mi na versão 1 e R$ 222,1 mi na última."""
    antiga = _contas(_versao(842.1e6, 1))
    nova = _contas(_versao(222.1e6, 2))

    achados = r5_reapresentado(
        antiga, nova, "Ajuste na mensuração de investimentos", ENTREGA_DA_V2
    )

    assert len(achados) == 1
    achado = achados[0]
    assert (achado.regra, achado.valor, achado.valor_esperado) == (
        "R5",
        842.1e6,
        222.1e6,
    )
    assert achado.valido_desde == ENTREGA_DA_V2
    assert "Ajuste na mensuração de investimentos" in achado.porque


def test_r5_sem_motivo_diz_que_nao_foi_informado():
    achado = r5_reapresentado(
        _contas(_versao(10e6, 1)), _contas(_versao(12e6, 2)), "", None
    )[0]

    assert "motivo não informado" in achado.porque


# --- R7: salto fora do padrão sem evento que explique ---------------------------------------------

UM_ANO_ANTES = {"inicio": pd.Timestamp("2023-01-01"), "fim": DFP_2023}
DO_ANO = {"inicio": pd.Timestamp("2024-01-01"), "fim": REFERENCIA}


def _receitas(atual: float, anterior: float) -> pd.DataFrame:
    return _contas(
        _receita(atual) | DO_ANO,
        _receita(anterior) | UM_ANO_ANTES | {"ordem": "penultimo"},
    )


def _eventos(*linhas: tuple[str, str]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"cnpj": cnpj, "publicado_em": pd.Timestamp(dia)} for cnpj, dia in linhas],
        columns=["cnpj", "publicado_em"],
    )


def test_r7_salto_sem_evento_no_ipe():
    achados = r7_salto_fora_do_padrao(_receitas(600e6, 100e6), _eventos())

    assert [(a.regra, a.conta) for a in achados] == [("R7", "3.01")]
    assert "6,0 vezes" in achados[0].porque


def test_r7_com_fato_relevante_no_periodo_nao_dispara():
    eventos = _eventos((CNPJ, "2024-06-01"))

    assert r7_salto_fora_do_padrao(_receitas(600e6, 100e6), eventos) == []


def test_r7_evento_de_outra_empresa_ou_fora_do_periodo_nao_conta():
    eventos = _eventos(("99.999.999/0001-99", "2024-06-01"), (CNPJ, "2022-06-01"))

    assert len(r7_salto_fora_do_padrao(_receitas(600e6, 100e6), eventos)) == 1


def test_r7_crescimento_comum_nao_dispara():
    assert r7_salto_fora_do_padrao(_receitas(200e6, 100e6), _eventos()) == []


def test_r7_mil_vezes_fica_para_a_r3():
    assert r7_salto_fora_do_padrao(_receitas(100e9, 100e6), _eventos()) == []


# --- R8: balanço atrasado ---------------------------------------------------------------------------


def _esperadas() -> pd.DataFrame:
    return pd.DataFrame([{"cnpj": CNPJ, "empresa": "EMPRESA TESTE S.A."}])


def _entregas(recebido_em: str | None) -> pd.DataFrame:
    linhas = (
        []
        if recebido_em is None
        else [
            {
                "cnpj": CNPJ,
                "documento": "DFP",
                "referencia": REFERENCIA,
                "recebido_em": pd.Timestamp(recebido_em),
            }
        ]
    )
    return pd.DataFrame(
        linhas, columns=["cnpj", "documento", "referencia", "recebido_em"]
    )


def test_r8_prazo_vencido_sem_documento():
    """DFP de 2024: prazo em 31/03/2025 (segunda-feira); em 15/04 ainda não entregue."""
    achados = r8_atraso(
        _esperadas(), _entregas(None), "DFP", REFERENCIA, pd.Timestamp("2025-04-15")
    )

    assert len(achados) == 1
    achado = achados[0]
    assert (achado.regra, achado.valor) == ("R8", 15.0)
    assert achado.valido_desde == pd.Timestamp("2025-04-01")
    assert "não foi entregue" in achado.porque


def test_r8_entregue_com_atraso():
    achados = r8_atraso(
        _esperadas(),
        _entregas("2025-04-10"),
        "DFP",
        REFERENCIA,
        pd.Timestamp("2025-05-01"),
    )

    assert [(a.regra, a.valor) for a in achados] == [("R8", 10.0)]
    assert achados[0].valido_desde == pd.Timestamp("2025-04-10")


def test_r8_antes_do_prazo_ou_entregue_no_prazo_nao_dispara():
    antes = r8_atraso(
        _esperadas(), _entregas(None), "DFP", REFERENCIA, pd.Timestamp("2025-03-20")
    )
    no_prazo = r8_atraso(
        _esperadas(),
        _entregas("2025-03-28"),
        "DFP",
        REFERENCIA,
        pd.Timestamp("2025-05-01"),
    )

    assert antes == []
    assert no_prazo == []
