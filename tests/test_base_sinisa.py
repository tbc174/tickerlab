"""SINISA (Ministério das Cidades): leitura da planilha de indicadores, valores, atribuição e `disponivel_em`."""

import io
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook

from base import sinisa

AMOSTRA = (
    Path(__file__).parent.parent
    / "dados_de_exemplo"
    / "sinisa"
    / "agua_indicadores_base_municipal_amostra.xlsx"
)

PREAMBULO = [
    "MINISTÉRIO DAS CIDADES  /  SECRETARIA NACIONAL DE SANEAMENTO AMBIENTAL",
    "SISTEMA NACIONAL DE INFORMAÇÕES EM SANEAMENTO BÁSICO - SINISA",
    "Módulo Abastecimento de Água",
    "Indicadores de Água",
    "Ano de referência 2024",
    "Data de publicação: 18/12/2025",
]
SIGLAS = [
    "cod_IBGE",
    "Macrorregião",
    "Município",
    "UF",
    "Capital",
    "RM/RIDE",
    "CAD0002",
    "CAD0003",
    "CAD0005",
    "CAD0006",
    "IAG0001",
    "IAG0004",
]
DESCRICOES = ["Codigo do IBGE", "Macrorregião", "Município", "UF", "Capital", "RM/RIDE", "Natureza Jurídica", "Abrangência", "Nome do Prestador", "Sigla", "Atendimento total com rede de água", "Atendimento dos domicílios totais"]  # fmt: skip
UNIDADES = [None] * 10 + ["Percentual", "Percentual"]


def _planilha(
    linhas,
    retificacao="Data de retificação: 25/05/2026",
    preambulo=PREAMBULO,
    siglas=SIGLAS,
):
    pasta = Workbook()
    aba = pasta.worksheets[0]
    for texto in [*preambulo, *([retificacao] if retificacao else [])]:
        aba.append([None, None, texto])
    aba.append([])
    aba.append(["Dados Gerais"])
    aba.append(DESCRICOES)
    aba.append(UNIDADES)
    aba.append(siglas)
    for linha in linhas:
        aba.append(linha)
    saida = io.BytesIO()
    pasta.save(saida)
    return saida.getvalue()


def _linha(ibge, nome, prestador, sigla, total, domicilios):
    return [
        ibge,
        "Norte",
        nome,
        "RO",
        None,
        None,
        "Autarquia",
        "Local",
        prestador,
        sigla,
        total,
        domicilios,
    ]


LINHAS = [
    _linha(1100015, "Alta Floresta D Oeste", "Serviço Autônomo de Água e Esgoto", "SAAE", "60,35", "Não calculado (condições não atendidas)"),
    _linha(1100023, "Ariquemes", "Águas de Ariquemes Saneamento Ltda", "AA", 86.7, 55.52),
    _linha(1100023, "Ariquemes", "Outro prestador", "OP", None, "Não calculado (divisão por zero)"),
]  # fmt: skip


def test_amostra_real_do_sinisa_vira_tabela_longa_com_atribuicao():
    tabela = sinisa.ler_indicadores(AMOSTRA.read_bytes())
    assert len(tabela) == 3 * tabela["indicador"].nunique()
    assert set(tabela["ano_referencia"]) == {2024}
    assert (tabela["atribuicao"] == sinisa.ATRIBUICAO).all()
    assert "SINISA" in sinisa.ATRIBUICAO and "CC BY-ND" in sinisa.ATRIBUICAO
    primeira = sinisa.por_municipio(tabela, "IAG0001").iloc[0]
    assert primeira["cod_ibge"] == "1100015"
    assert primeira["valor"] == pytest.approx(60.35)
    assert primeira["unidade"] == "Percentual"


def test_chave_e_valores_nao_sao_alterados():
    tabela = sinisa.ler_indicadores(_planilha(LINHAS))
    assert not tabela.duplicated(sinisa.CHAVE).any()
    assert len(tabela) == 3 * 2
    saae = tabela[
        (tabela["cod_ibge"] == "1100015") & (tabela["indicador"] == "IAG0001")
    ].iloc[0]
    assert saae["valor"] == 60.35  # texto com vírgula, sem arredondar
    assert saae["prestador"] == "Serviço Autônomo de Água e Esgoto"
    assert saae["descricao"] == "Atendimento total com rede de água"
    assert set(tabela["cod_ibge"]) == {"1100015", "1100023"}


def test_nao_calculado_vira_vazio_com_o_motivo():
    tabela = sinisa.ler_indicadores(_planilha(LINHAS))
    linha = tabela[
        (tabela["cod_ibge"] == "1100015") & (tabela["indicador"] == "IAG0004")
    ].iloc[0]
    assert pd.isna(linha["valor"])
    assert linha["motivo_nao_calculado"] == "condições não atendidas"
    vazia = tabela[
        (tabela["prestador"] == "Outro prestador") & (tabela["indicador"] == "IAG0001")
    ].iloc[0]
    assert pd.isna(vazia["valor"]) and pd.isna(vazia["motivo_nao_calculado"])


def test_disponivel_em_e_a_retificacao_nunca_antes_da_publicacao():
    retificada = sinisa.ler_indicadores(_planilha(LINHAS))
    assert (retificada["disponivel_em"] == pd.Timestamp("2026-05-25")).all()
    assert (retificada["publicado_em"] == pd.Timestamp("2025-12-18")).all()
    sem = sinisa.ler_indicadores(_planilha(LINHAS, retificacao=None))
    assert (sem["disponivel_em"] == pd.Timestamp("2025-12-18")).all()
    assert sem["retificado_em"].isna().all()


def test_valor_e_motivo_aceita_numero_e_texto():
    assert sinisa.valor_e_motivo(12) == (12.0, None)
    assert sinisa.valor_e_motivo("1.234,5") == (1234.5, None)
    assert sinisa.valor_e_motivo("7.5") == (7.5, None)
    assert sinisa.valor_e_motivo(None) == (None, None)
    assert sinisa.valor_e_motivo("Não calculado (sem dado)") == (None, "sem dado")
    with pytest.raises(ValueError, match="não é número"):
        sinisa.valor_e_motivo("abc")


def test_formato_inesperado_levanta_erro():
    with pytest.raises(ValueError, match="preâmbulo"):
        sinisa.ler_indicadores(_planilha(LINHAS, preambulo=PREAMBULO[:4]))
    sem_cod = ["x", *SIGLAS[1:]]
    with pytest.raises(ValueError, match="siglas"):
        sinisa.ler_indicadores(_planilha(LINHAS, siglas=sem_cod))
    sem_indicador = [*SIGLAS[:10], "XYZ", "ABC"]
    with pytest.raises(ValueError, match="indicador"):
        sinisa.ler_indicadores(_planilha(LINHAS, siglas=sem_indicador))
    repetida = [LINHAS[1], LINHAS[1]]
    with pytest.raises(ValueError, match="repetido"):
        sinisa.ler_indicadores(_planilha(repetida))
