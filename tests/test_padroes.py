"""Padrões por setor "como estavam na data" (série 2 da base de ML, PR 4; ADR 0033): percentis de
cada indicador por grupo, calculados só com o que era público na data de corte e sem as empresas
com número em conferência."""

from datetime import date

import pandas as pd
import pytest

from src import demonstracoes as dm
from src import padroes as pa
from src import setores

DIA = pd.Timestamp


def _conta(
    cnpj, conta, valor, referencia=date(2024, 12, 31), versao=1, periodo=dm.EXERCICIO
):
    return {
        "cnpj": cnpj,
        "documento": "DFP",
        "referencia": referencia,
        "versao": versao,
        "periodo": periodo,
        "inicio": date(referencia.year, 1, 1) if periodo == dm.EXERCICIO else None,
        "fim": referencia,
        "conta": conta,
        "valor": valor,
    }


def _documento(cnpj, recebido, referencia=date(2024, 12, 31), versao=1):
    return {
        "cnpj": cnpj,
        "documento": "DFP",
        "referencia": referencia,
        "versao": versao,
        "recebido_em": DIA(recebido),
    }


def test_contas_como_estavam_usam_a_versao_entregue_ate_a_data():
    contas = pd.DataFrame(
        [
            _conta("A", "receita", 100.0, versao=1),
            _conta("A", "receita", 90.0, versao=2),
        ]
    )
    documentos = pd.DataFrame(
        [
            _documento("A", "2025-03-20", versao=1),
            _documento("A", "2025-06-10", versao=2),
        ]
    )
    em_abril = pa.contas_como_estavam(contas, documentos, DIA("2025-04-30"))
    em_julho = pa.contas_como_estavam(contas, documentos, DIA("2025-07-31"))
    assert em_abril["valor"].tolist() == [100.0]
    assert em_julho["valor"].tolist() == [90.0]


def test_padrao_em_D_so_usa_o_que_era_publico_em_D():
    contas = pd.DataFrame([_conta("A", "receita", 100.0), _conta("B", "receita", 50.0)])
    documentos = pd.DataFrame(
        [
            _documento("A", "2025-03-20"),
            _documento("B", "2025-05-15"),
        ]  # B entregou depois
    )
    em_abril = pa.contas_como_estavam(contas, documentos, DIA("2025-04-30"))
    assert set(em_abril["cnpj"]) == {"A"}


def _valores(grupo, indicador, numeros, primeira=0):
    return [
        {
            "cnpj": f"{grupo}{i + primeira}",
            "grupo": grupo,
            "indicador": indicador,
            "valor": v,
        }
        for i, v in enumerate(numeros)
    ]


def test_percentis_por_grupo_com_o_numero_de_empresas_e_o_mercado():
    valores = pd.DataFrame(
        _valores("energia", "margem_liquida", [i / 100 for i in range(1, 11)])
        + _valores("saude", "margem_liquida", [0.5] * 9)
        + _valores("financeiro", "margem_liquida", [9.0] * 9)
    )
    padroes = pa.calcular_padroes(valores).set_index(["grupo", "indicador"])
    energia = padroes.loc[("energia", "margem_liquida")]
    assert energia["empresas"] == 10
    assert energia["percentis"]["50"] == pytest.approx(0.055)
    mercado = padroes.loc[(setores.MERCADO, "margem_liquida")]
    assert (
        mercado["empresas"] == 19
    )  # energia + saúde; o financeiro fica fora do mercado


def test_valor_vazio_ou_infinito_nao_entra():
    valores = pd.DataFrame(
        _valores("energia", "roe", [0.1, None, float("inf"), 0.2] + [0.15] * 6)
    )
    padroes = pa.calcular_padroes(valores).set_index(["grupo", "indicador"])
    assert padroes.loc[("energia", "roe"), "empresas"] == 8


def test_valor_com_achado_aberto_fica_fora_do_padrao():
    valores = pd.DataFrame(_valores("energia", "roe", [0.1] * 8 + [99.0]))
    sem_conferencia = pa.calcular_padroes(valores, excluidas={"energia8"})
    linha = sem_conferencia.set_index(["grupo", "indicador"]).loc[("energia", "roe")]
    assert linha["empresas"] == 8 and linha["percentis"]["90"] == pytest.approx(0.1)


def test_indicadores_de_uma_empresa_pelas_funcoes_da_tela():
    contas = pd.DataFrame(
        [
            _conta("A", "receita", 1000.0),
            _conta("A", "ebit", 150.0),  # sem EBIT, a tela trata como financeira
            _conta("A", "lucro_liquido", 100.0),
            _conta("A", "patrimonio_liquido", 500.0, periodo=dm.POSICAO),
            _conta("A", "ativo_total", 2000.0, periodo=dm.POSICAO),
        ]
    )
    valores = pa.indicadores_da_empresa(contas.drop(columns="cnpj"), "Energia Elétrica")
    assert valores["margem_liquida"] == pytest.approx(0.1)
    assert valores["roe"] == pytest.approx(0.2)
    assert valores["dupont_giro"] == pytest.approx(0.5)
    assert set(valores) == set(pa.INDICADORES)


def test_todo_indicador_com_padrao_diz_se_maior_e_melhor():
    for chave, (nome, maior_e_melhor) in pa.INDICADORES.items():
        assert nome and isinstance(maior_e_melhor, bool), chave
