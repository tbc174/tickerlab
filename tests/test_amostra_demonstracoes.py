"""Bloco "demonstrações" da amostra integrada (PR 2): o balanço e o resultado como eram em cada fim de mês
(o período mais novo já público, na versão mais nova já entregue), com o corte da base em cada data."""

import pandas as pd
import pytest

from base.amostra import como_era, demonstracoes

D = pd.Timestamp


def _linha(cnpj, grupo, dem, conta, descricao, inicio, fim, valor, doc, ref, versao, divulgado, ate=None,
           ordem="ultimo"):  # fmt: skip
    return {
        "cnpj": cnpj, "empresa": cnpj, "grupo": grupo, "demonstracao": dem, "conta": conta,
        "descricao": descricao, "inicio": D(inicio) if inicio else pd.NaT, "fim": D(fim),
        "valor": valor, "documento": doc, "referencia": D(ref), "versao": versao, "ordem": ordem,
        "origem": "dados_abertos", "divulgado_em": D(divulgado), "ate": D(ate) if ate else pd.NaT,
    }  # fmt: skip


def _base() -> pd.DataFrame:
    linhas = []
    for grupo, fator in (("con", 1.0), ("ind", 0.5)):

        def a(*args, grupo=grupo, **kw):
            linhas.append(_linha("A", grupo, *args, **kw))

        # ITR do 1º trimestre de 2013
        a(
            "BPA",
            "1",
            "Ativo Total",
            None,
            "2013-03-31",
            100 * fator,
            "ITR",
            "2013-03-31",
            1,
            "2013-04-24",
        )
        a(
            "BPP",
            "2.01.04",
            "Empréstimos e Financiamentos",
            None,
            "2013-03-31",
            7,
            "ITR",
            "2013-03-31",
            1,
            "2013-04-24",
        )
        a(
            "BPP",
            "2.02.01",
            "Empréstimos e Financiamentos",
            None,
            "2013-03-31",
            3,
            "ITR",
            "2013-03-31",
            1,
            "2013-04-24",
        )
        a(
            "DRE",
            "3.01",
            "Receita de Venda de Bens e/ou Serviços",
            "2013-01-01",
            "2013-03-31",
            10,
            "ITR",
            "2013-03-31",
            1,
            "2013-04-24",
        )
        # ITR do 2º trimestre: o trimestre (abr-jun) e o acumulado (jan-jun)
        a(
            "BPA",
            "1",
            "Ativo Total",
            None,
            "2013-06-30",
            110 * fator,
            "ITR",
            "2013-06-30",
            1,
            "2013-07-31",
        )
        a(
            "DRE",
            "3.01",
            "Receita de Venda de Bens e/ou Serviços",
            "2013-04-01",
            "2013-06-30",
            15,
            "ITR",
            "2013-06-30",
            1,
            "2013-07-31",
        )
        a(
            "DRE",
            "3.01",
            "Receita de Venda de Bens e/ou Serviços",
            "2013-01-01",
            "2013-06-30",
            25,
            "ITR",
            "2013-06-30",
            1,
            "2013-07-31",
        )
        # DFP de 2013 e a reapresentação entregue em maio de 2014
        a(
            "BPA",
            "1",
            "Ativo Total",
            None,
            "2013-12-31",
            130 * fator,
            "DFP",
            "2013-12-31",
            1,
            "2014-02-26",
        )
        a(
            "DRE",
            "3.01",
            "Receita de Venda de Bens e/ou Serviços",
            "2013-01-01",
            "2013-12-31",
            60,
            "DFP",
            "2013-12-31",
            1,
            "2014-02-26",
            ate="2014-05-10",
        )
        a(
            "DRE",
            "3.01",
            "Receita de Venda de Bens e/ou Serviços",
            "2013-01-01",
            "2013-12-31",
            58,
            "DFP",
            "2013-12-31",
            2,
            "2014-05-10",
        )
        a(
            "DRE",
            "3.05",
            "Resultado Antes do Resultado Financeiro e dos Tributos",
            "2013-01-01",
            "2013-12-31",
            9,
            "DFP",
            "2013-12-31",
            1,
            "2014-02-26",
        )
    # um banco (B): a conta 3.05 é outra coisa e não vira EBIT
    linhas.append(
        _linha(
            "B",
            "con",
            "DRE",
            "3.01",
            "Receitas da Intermediação Financeira",
            "2013-01-01",
            "2013-12-31",
            500,
            "DFP",
            "2013-12-31",
            1,
            "2014-03-20",
        )
    )
    linhas.append(
        _linha(
            "B",
            "con",
            "DRE",
            "3.05",
            "Resultado Antes dos Tributos sobre o Lucro",
            "2013-01-01",
            "2013-12-31",
            80,
            "DFP",
            "2013-12-31",
            1,
            "2014-03-20",
        )
    )
    linhas.append(
        _linha(
            "B",
            "con",
            "BPA",
            "1",
            "Ativo Total",
            None,
            "2013-12-31",
            9000,
            "DFP",
            "2013-12-31",
            1,
            "2014-03-20",
        )
    )
    # C só publica o individual
    linhas.append(
        _linha(
            "C",
            "ind",
            "BPA",
            "1",
            "Ativo Total",
            None,
            "2013-12-31",
            40,
            "DFP",
            "2013-12-31",
            1,
            "2014-03-28",
        )
    )
    return pd.DataFrame(linhas)


def _grade() -> pd.DataFrame:
    meses = como_era.fins_de_mes(D("2013-01-31"), D("2014-12-31"))
    return pd.DataFrame(
        [(c, m) for c in "ABC" for m in meses], columns=["cnpj", "data"]
    )


@pytest.fixture(scope="module")
def painel():
    return demonstracoes.montar({"demonstracoes": _base()}, _grade())


def _em(painel, cnpj, data):
    return painel[(painel["cnpj"] == cnpj) & (painel["data"] == D(data))].iloc[0]


def test_balanco_e_o_do_periodo_mais_novo_ja_publico(painel):
    assert pd.isna(_em(painel, "A", "2013-03-31")["ativo_total"])  # a ITR saiu em 24/04
    linha = _em(painel, "A", "2013-05-31")
    assert (linha["ativo_total"], linha["balanco_fim"], linha["balanco_grupo"]) == (
        100,
        D("2013-03-31"),
        "con",
    )
    assert linha["divida_bruta"] == 10  # curto + longo prazo
    assert linha["balanco_publico_em"] == D("2013-04-24")
    assert _em(painel, "A", "2013-08-31")["ativo_total"] == 110


def test_resultado_acumulado_e_o_do_ano_nao_o_do_trimestre(painel):
    linha = _em(painel, "A", "2013-08-31")
    assert linha["receita_acumulado"] == 25
    assert (linha["acumulado_inicio"], linha["acumulado_fim"]) == (
        D("2013-01-01"),
        D("2013-06-30"),
    )
    assert pd.isna(linha["receita_anual"])  # nenhuma DFP pública ainda


def test_reapresentacao_so_vale_depois_de_entregue(painel):
    assert _em(painel, "A", "2014-03-31")["receita_anual"] == 60
    linha = _em(painel, "A", "2014-05-31")
    assert linha["receita_anual"] == 58
    assert linha["anual_publico_em"] == D("2014-05-10")


def test_consolidado_antes_do_individual(painel):
    assert _em(painel, "A", "2014-03-31")["ativo_total"] == 130  # não o individual (65)
    linha = _em(painel, "C", "2014-04-30")
    assert (linha["ativo_total"], linha["balanco_grupo"]) == (40, "ind")


def test_conta_de_banco_que_nao_e_ebit_fica_vazia(painel):
    linha = _em(painel, "B", "2014-04-30")
    assert linha["receita_anual"] == 500
    assert pd.isna(linha["ebit_anual"])


@pytest.mark.parametrize(
    "data",
    [
        "2013-04-30",
        "2013-07-31",
        "2014-02-28",
        "2014-03-31",
        "2014-05-31",
        "2014-12-31",
    ],
)
def test_nenhum_bloco_olha_o_futuro(data):
    dia = D(data)
    inteira = demonstracoes.montar({"demonstracoes": _base()}, _grade())
    cortada = demonstracoes.montar(
        como_era.cortar({"demonstracoes": _base()}, demonstracoes.ENTRADAS, dia),
        _grade(),
    )
    pd.testing.assert_frame_equal(
        inteira[inteira["data"] == dia].reset_index(drop=True),
        cortada[cortada["data"] == dia].reset_index(drop=True),
        check_dtype=False,
    )
