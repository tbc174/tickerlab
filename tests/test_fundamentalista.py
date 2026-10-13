"""Cálculos fundamentalistas do relatório completo de empresa (série 2 da base de ML, PR 2; ADR 0032,
item 1): DuPont, ciclo de caixa, caixa livre, capex contra depreciação, cobertura de juros e o
histórico de 10 anos. Números sintéticos fáceis de conferir à mão, e a WEG real para o DuPont fechar
com o ROE que a tela Fundamentos já mostra."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src import demonstracoes as dm
from src import fundamentalista as fa
from src import fundamentos as fu
from src.banco.demonstracoes import DadosDaEmpresa

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "fundamentos"
WEG = "84.429.695/0001-11"


def _linhas(ano: int, fluxos: dict, saldos: dict) -> list[dict]:
    referencia = date(ano, 12, 31)
    comum = {
        "documento": "DFP",
        "referencia": referencia,
        "versao": 1,
        "fim": referencia,
    }
    linhas = [
        {
            **comum,
            "periodo": dm.EXERCICIO,
            "inicio": date(ano, 1, 1),
            "conta": c,
            "valor": v,
        }
        for c, v in fluxos.items()
    ]
    linhas += [
        {**comum, "periodo": dm.POSICAO, "inicio": None, "conta": c, "valor": v}
        for c, v in saldos.items()
    ]
    return linhas


FLUXOS = {
    "receita": 3650.0,
    "custo": -1825.0,
    "ebit": 500.0,
    "lucro_liquido": 300.0,
    "despesas_financeiras": -100.0,
    "fco": 600.0,
    "capex": -250.0,
    "depreciacao": 125.0,
}
SALDOS = {
    "ativo_total": 3000.0,
    "patrimonio_liquido": 1500.0,
    "contas_a_receber": 300.0,
    "estoques": 200.0,
    "fornecedores": 100.0,
}


def _empresa(
    anos=(2024, 2025), fluxos=FLUXOS, saldos=SALDOS, setor="Máquinas"
) -> DadosDaEmpresa:
    linhas = [l for ano in anos for l in _linhas(ano, fluxos, saldos)]
    return DadosDaEmpresa(
        contas=pd.DataFrame(linhas), documentos=pd.DataFrame(), setor=setor
    )


def test_dupont_fecha_com_o_roe():
    resultado = fa.calcular(_empresa())
    margem, giro, alavancagem = (
        resultado["dupont_margem"].valor,
        resultado["dupont_giro"].valor,
        resultado["dupont_alavancagem"].valor,
    )
    assert margem == pytest.approx(300 / 3650)
    assert giro == pytest.approx(3650 / 3000)
    assert alavancagem == pytest.approx(3000 / 1500)
    assert margem * giro * alavancagem == pytest.approx(300 / 1500)
    assert resultado["dupont_roe"].valor == pytest.approx(0.2)


def test_dupont_da_weg_bate_com_o_roe_da_tela():
    contas, documentos = dm.ler_demonstracoes(
        (PASTA / "dfp_cia_aberta_2025.zip").read_bytes(), "DFP"
    )
    dados = DadosDaEmpresa(
        contas=contas[contas["cnpj"] == WEG].drop(columns="cnpj"),
        documentos=documentos[documentos["cnpj"] == WEG],
        setor="Máquinas, Equipamentos, Veículos e Peças",
    )
    roe_da_tela = fu.calcular(dados, None)["roe"].valor
    assert fa.calcular(dados)["dupont_roe"].valor == pytest.approx(roe_da_tela)


def test_ciclo_de_caixa_em_dias_com_saldo_medio():
    resultado = fa.calcular(_empresa())
    assert resultado["pmr"].valor == pytest.approx(300 / 3650 * 365)  # 30 dias
    assert resultado["pme"].valor == pytest.approx(200 / 1825 * 365)  # 40 dias
    assert resultado["pmp"].valor == pytest.approx(100 / 1825 * 365)  # 20 dias
    assert resultado["ciclo_de_caixa"].valor == pytest.approx(30 + 40 - 20)
    assert "saldo médio" in resultado["pmr"].base  # de hoje e de um ano antes


def test_ciclo_sem_o_ano_anterior_usa_o_saldo_do_fim_e_diz():
    resultado = fa.calcular(_empresa(anos=(2025,)))
    assert resultado["pmr"].valor == pytest.approx(30.0)
    assert "fim" in resultado["pmr"].base


def test_caixa_livre_e_capex_contra_depreciacao():
    resultado = fa.calcular(_empresa())
    assert resultado["caixa_livre"].valor == pytest.approx(600 - 250)
    assert resultado["capex_sobre_depreciacao"].valor == pytest.approx(250 / 125)


def test_cobertura_de_juros_e_sem_despesa_financeira_nao_se_aplica():
    assert fa.calcular(_empresa())["cobertura_de_juros"].valor == pytest.approx(5.0)
    sem_divida = {k: v for k, v in FLUXOS.items() if k != "despesas_financeiras"}
    cobertura = fa.calcular(_empresa(fluxos=sem_divida))["cobertura_de_juros"]
    assert cobertura.valor is None and "despesa financeira" in cobertura.motivo


def test_banco_nao_tem_ciclo_nem_caixa_livre():
    resultado = fa.calcular(_empresa(setor="Bancos"))
    for chave in (
        "ciclo_de_caixa",
        "caixa_livre",
        "cobertura_de_juros",
        "dupont_margem",
    ):
        assert resultado[chave].valor is None
        assert resultado[chave].motivo == fu.NAO_SE_APLICA_A_FINANCEIRAS


def test_historico_de_10_anos_com_falta_vertical_horizontal_e_consistencia():
    anos = (2015, 2016, 2018, 2019)  # 2017 faltando
    historico = fa.calcular(_empresa(anos=anos)).historico
    assert list(historico.contas.index) == [2015, 2016, 2017, 2018, 2019]
    assert (
        historico.contas.loc[2017].isna().all()
    )  # falta aparece como falta, não como zero
    assert historico.vertical.loc[2019, "lucro_liquido"] == pytest.approx(300 / 3650)
    assert historico.vertical.loc[2019, "estoques"] == pytest.approx(200 / 3000)
    assert historico.horizontal.loc[2016, "receita"] == pytest.approx(0.0)
    assert pd.isna(
        historico.horizontal.loc[2018, "receita"]
    )  # sem 2017, não há variação
    assert historico.consistencia["anos_com_lucro"] == 4
    assert historico.consistencia["anos_com_dado"] == 4


def test_historico_fica_nos_ultimos_10_anos():
    historico = fa.calcular(_empresa(anos=tuple(range(2010, 2026)))).historico
    assert list(historico.contas.index) == list(range(2016, 2026))
