"""As séries calculadas pelo código para os gráficos (emenda 1 do plano de 23/10/2026).

O modelo escolhe entre séries prontas; cada número delas sai de uma conta feita aqui, contra as contas
do histórico da ficha. Os valores esperados abaixo são contas feitas à mão sobre o histórico de três
anos de `_entrada()`.
"""

import copy
import json

import pytest

from src.analise_escrita import entrada as en
from src.analise_escrita import graficos as gr
from src.analise_escrita import porta1, series
from tests.ajudantes_da_analise import PAR_DA_CPFL

CPFL = json.loads((PAR_DA_CPFL / "entrada.json").read_text(encoding="utf-8"))

_CONTAS = {
    2023: {
        "receita": 1000.0, "resultado_bruto": 400.0, "ebit": 200.0, "lucro_liquido": 100.0,
        "lucro_controladores": 90.0, "patrimonio_liquido": 1000.0, "minoritarios": 100.0,
        "ativo_total": 2000.0, "depreciacao": 50.0, "divida_cp": 100.0, "divida_lp": 400.0,
        "caixa": 80.0, "aplicacoes": 20.0, "fco": 180.0, "capex": -120.0, "custo": -600.0,
        "contas_a_receber": 100.0, "estoques": 60.0, "fornecedores": 30.0,
        "ativo_circulante": 500.0, "passivo_circulante": 250.0, "despesas_com_vendas": -50.0,
        "despesas_administrativas": -80.0, "despesas_financeiras": -40.0,
        "dividendos_pagos": -45.0, "lpa_basico": 0.9,
    },
    2024: {
        "receita": 1200.0, "resultado_bruto": 420.0, "ebit": 180.0, "lucro_liquido": 60.0,
        "lucro_controladores": 50.0, "patrimonio_liquido": 1100.0, "minoritarios": 100.0,
        "ativo_total": 2400.0, "depreciacao": 60.0, "divida_cp": 200.0, "divida_lp": 500.0,
        "caixa": 50.0, "aplicacoes": 0.0, "fco": 150.0, "capex": -240.0, "custo": -780.0,
        "contas_a_receber": 150.0, "estoques": 78.0, "fornecedores": 39.0,
        "ativo_circulante": 480.0, "passivo_circulante": 320.0, "despesas_com_vendas": -60.0,
        "despesas_administrativas": -90.0, "despesas_financeiras": -70.0,
        "dividendos_pagos": -30.0, "lpa_basico": 0.5,
    },
    2025: {  # prejuízo e EBITDA zero: o que não tem conta fica em branco
        "receita": 900.0, "resultado_bruto": 90.0, "ebit": -60.0, "lucro_liquido": -30.0,
        "lucro_controladores": -30.0, "patrimonio_liquido": 1070.0, "minoritarios": 100.0,
        "ativo_total": 2300.0, "depreciacao": 60.0, "divida_cp": 200.0, "divida_lp": 550.0,
        "caixa": 40.0, "aplicacoes": 10.0, "fco": 60.0, "capex": -90.0, "custo": -810.0,
        "contas_a_receber": 120.0, "ativo_circulante": 400.0, "passivo_circulante": 0.0,
        "dividendos_pagos": 0.0, "lpa_basico": -0.3,
    },
}  # fmt: skip


def _entrada(anos=(2023, 2024, 2025)) -> dict:
    linhas = [
        {
            "secao": "historico",
            "id": f"historico.contas.{i}",
            "tipo": "linha",
            "tabela": "Contas ano a ano",
            "celulas": {"ano": ano, **_CONTAS[ano]},
            "so_pro": False,
        }
        for i, ano in enumerate(anos)
    ]
    return {
        "corte": "2026-10-17",
        "secoes": {"historico": "Histórico de até 10 anos"},
        "linhas": linhas,
    }


def _tabela(entrada: dict, chave: str) -> dict[int, dict]:
    """As células da tabela `series.<chave>` pelo ano."""
    prefixo = f"{series.SECAO}.{chave}."
    return {
        li["celulas"][series.EIXO]: li
        for li in series.linhas_das_series(entrada)
        if li["id"].startswith(prefixo)
    }


def _celulas(entrada: dict, chave: str) -> dict[int, dict]:
    return {ano: li["celulas"] for ano, li in _tabela(entrada, chave).items()}


def test_margens_contadas_a_mao():
    margens = _celulas(_entrada(), "margens")
    assert margens[2023] == {
        "Ano": 2023,
        "Margem bruta": "40,0%",
        "Margem EBIT": "20,0%",
        "Margem líquida": "10,0%",
    }
    assert margens[2024]["Margem bruta"] == "35,0%"  # 420 / 1200
    assert margens[2025]["Margem líquida"] == "-3,3%"  # -30 / 900


def test_retorno_usa_o_patrimonio_dos_controladores():
    retorno = _celulas(_entrada(), "retorno")
    assert retorno[2023]["ROE"] == "10,0%"  # 90 / (1000 - 100)
    assert retorno[2023]["ROA"] == "5,0%"  # 100 / 2000
    assert retorno[2024]["ROE"] == "5,0%"  # 50 / (1100 - 100)


def test_crescimento_comeca_no_segundo_ano():
    crescimento = _celulas(_entrada(), "crescimento")
    assert 2023 not in crescimento
    assert crescimento[2024]["Crescimento da receita"] == "20,0%"  # 1200 / 1000 - 1
    assert crescimento[2024]["Crescimento do lucro"] == "-40,0%"  # 60 / 100 - 1
    assert crescimento[2025]["Crescimento da receita"] == "-25,0%"  # 900 / 1200 - 1


def test_crescimento_do_lucro_some_quando_a_base_e_prejuizo_ou_falta_um_ano():
    tres_anos = _celulas(_entrada(), "crescimento")
    assert "Crescimento do lucro" in tres_anos[2024]
    com_buraco = _celulas(_entrada((2023, 2025)), "crescimento")
    assert com_buraco == {}  # 2023 → 2025 não é crescimento de um ano


def test_divida_caixa_e_alavancagem():
    entrada = _entrada()
    assert _celulas(entrada, "divida")[2023]["Dívida líquida"] == "R$ 400"
    alavancagem = _celulas(entrada, "alavancagem")
    assert alavancagem[2023]["Dívida líquida / EBITDA"] == "1,60×"  # 400 / (200 + 50)
    assert 2025 not in alavancagem  # EBITDA zero: sem conta
    caixa = _celulas(entrada, "caixa")[2024]
    assert caixa["Caixa operacional"] == "R$ 150"
    assert caixa["Investimento (capex)"] == "R$ 240"
    assert caixa["Caixa livre"] == "R$ -90"  # 150 - 240


def test_prazos_em_dias():
    prazos = _celulas(_entrada(), "prazos")[2023]
    assert prazos["Prazo de recebimento"] == "36 dias"  # 100 / 1000 × 365 = 36,5
    assert prazos["Prazo de estoque"] == "36 dias"  # 60 / 600 × 365 = 36,5
    assert prazos["Prazo de fornecedores"] == "18 dias"  # 30 / 600 × 365 = 18,25


def test_conta_que_falta_ou_divide_por_zero_fica_em_branco():
    entrada = _entrada()
    prazos_2025 = _celulas(entrada, "prazos")[2025]
    assert "Prazo de estoque" not in prazos_2025  # 2025 não tem estoques
    assert "Prazo de recebimento" in prazos_2025
    assert 2025 not in _celulas(entrada, "liquidez")  # passivo circulante zero
    assert 2025 not in _celulas(
        entrada, "conversao"
    )  # prejuízo: FCO sobre lucro não se lê


def test_tabela_sem_nenhum_valor_sai():
    entrada = _entrada()
    for linha in entrada["linhas"]:
        linha["celulas"].pop("estoques", None)
        linha["celulas"].pop("contas_a_receber", None)
        linha["celulas"].pop("fornecedores", None)
    assert _celulas(entrada, "prazos") == {}


def test_payout_e_dividendos():
    entrada = _entrada()
    assert _celulas(entrada, "dividendos")[2023]["Dividendos pagos"] == "R$ 45"
    payout = _celulas(entrada, "payout")
    assert payout[2023]["Payout"] == "50,0%"  # 45 / 90
    assert 2025 not in payout  # prejuízo


def test_cada_linha_cita_as_contas_de_onde_saiu():
    entrada = _entrada()
    ids = {li["id"] for li in entrada["linhas"]}
    for linha in series.linhas_das_series(entrada):
        assert linha["de"]
        assert set(linha["de"]) <= ids
    assert _tabela(entrada, "margens")[2024]["de"] == ["historico.contas.1"]
    assert _tabela(entrada, "crescimento")[2024]["de"] == [
        "historico.contas.0",
        "historico.contas.1",
    ]


def test_ids_e_tabelas_seguem_o_formato_da_ficha():
    linhas = series.linhas_das_series(_entrada())
    tabelas = gr.tabelas_da_entrada({"linhas": linhas})
    assert "series.margens" in tabelas
    for chave, das_linhas in tabelas.items():
        assert [li.id for li in das_linhas] == [
            f"{chave}.{i}" for i in range(len(das_linhas))
        ]


def test_series_sem_olhar_o_futuro():
    """Tirar o último ano não muda nenhuma linha dos anos de antes."""
    completas = {
        (li["tabela"], li["celulas"][series.EIXO]): li["celulas"]
        for li in series.linhas_das_series(_entrada())
    }
    cortadas = series.linhas_das_series(_entrada((2023, 2024)))
    assert cortadas
    for linha in cortadas:
        assert (
            completas[(linha["tabela"], linha["celulas"][series.EIXO])]
            == linha["celulas"]
        )


def test_ampliar_nao_mexe_na_entrada_nem_no_hash_do_texto():
    original = copy.deepcopy(CPFL)
    ampliada = series.ampliar(CPFL)
    assert original == CPFL
    assert en.hash_da_entrada(CPFL) == en.hash_da_entrada(original)
    assert series.SECAO in ampliada["secoes"]
    novas = [li for li in ampliada["linhas"] if li["secao"] == series.SECAO]
    assert novas
    assert ampliada["linhas"][: len(CPFL["linhas"])] == CPFL["linhas"]


def test_porta1_le_os_numeros_das_series_e_nao_os_ids_citados():
    ampliada = series.ampliar(CPFL)
    ficha = porta1.ler_ficha(ampliada)
    margens = ficha.linhas[
        "series.margens.1"
    ]  # 2025 da CPFL: lucro 5,74 bi / receita 44,4 bi
    assert any(abs(n.valor - 0.129) < 1e-9 for n in margens.numeros)
    assert 1.0 not in {
        n.valor for n in margens.numeros
    }  # o "1" de "historico.contas.1"


@pytest.mark.parametrize("chave", ["margens", "retorno", "receita_e_lucro", "caixa"])
def test_cpfl_tem_as_series_principais(chave):
    assert _celulas(CPFL, chave)
