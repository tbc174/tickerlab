"""Amostra integrada (ADR 0058; plano `2026-10-16-amostra-integrada-v1.md`, PR 1): a regra "como era na
data" de todos os blocos e o universo. O teste central corta a base numa data (só o que já era público)
e confere que a linha do painel naquela data é a mesma do painel montado com a base inteira."""

import pandas as pd
import pytest

from base.amostra import como_era, universo

FIM = pd.Timestamp("2016-12-31")
D = pd.Timestamp


def _entradas() -> dict[str, pd.DataFrame]:
    """Três companhias: a A, ativa desde 2005; a B, que entrou em 2012 e foi cancelada em 2015; a C,
    registrada em 2013 e que só entregou a primeira ITR em 2014."""
    cadastro = pd.DataFrame(
        {
            "cnpj": ["A", "B", "C"],
            "registro": [D("2005-03-01"), D("2012-02-10"), D("2013-06-01")],
            "cancelamento": [pd.NaT, D("2015-07-20"), pd.NaT],
        }
    )
    entregas = pd.DataFrame(
        {
            "cnpj": ["A", "A", "B", "C"],
            "primeira_entrega": [
                D("2009-03-30"),
                D("2010-05-14"),
                D("2012-05-15"),
                D("2014-08-14"),
            ],
        }
    )
    tickers = pd.DataFrame(
        {
            "codigo": ["AAAA3", "AAAA4", "BBBB3", "CCCC3"],
            "cnpj": ["A", "A", "B", "C"],
            "primeiro_visto": [
                D("2010-05-31"),
                D("2011-06-10"),
                D("2013-05-20"),
                D("2016-03-01"),
            ],
            "valido_ate": [pd.NaT, D("2014-04-15"), pd.NaT, pd.NaT],
        }
    )
    return universo.preparar(cadastro, entregas, tickers)


@pytest.fixture(scope="module")
def painel():
    return universo.montar(_entradas(), FIM)


def _linha(tabela: pd.DataFrame, cnpj: str, data: str) -> pd.Series:
    return tabela[(tabela["cnpj"] == cnpj) & (tabela["data"] == D(data))].iloc[0]


# --- a regra "como era" -----------------------------------------------------------------------------
def test_ultimo_publico_pega_o_valor_mais_novo_ja_publico():
    grade = pd.DataFrame(
        {"cnpj": ["A"] * 3, "data": [D("2020-01-31"), D("2020-02-29"), D("2020-03-31")]}
    )
    tabela = pd.DataFrame(
        {
            "cnpj": ["A", "A"],
            "publico_em": [D("2020-02-10"), D("2020-03-31")],
            "valor": [1.0, 2.0],
        }
    )
    lido = como_era.ultimo_publico(
        grade, tabela, publico_em="publico_em", colunas=["valor"], prefixo="x"
    )
    assert (
        lido["valor"].tolist()[0] != lido["valor"].tolist()[0]
    )  # vazio: nada público em janeiro
    assert lido["valor"].tolist()[1:] == [1.0, 2.0]  # no próprio dia já vale
    assert lido["x_publico_em"].iloc[2] == D("2020-03-31")


def test_cortar_tira_o_que_nao_era_publico_e_o_fim_que_estava_no_futuro():
    cortadas = como_era.cortar(_entradas(), universo.ENTRADAS, D("2014-12-31"))
    assert set(cortadas["cadastro"]["cnpj"]) == {"A", "B", "C"}
    assert (
        cortadas["cadastro"]["cancelamento"].isna().all()
    )  # o cancelamento da B é de 2015
    assert set(cortadas["tickers"]["codigo"]) == {
        "AAAA3",
        "AAAA4",
        "BBBB3",
    }  # CCCC3 só em 2016
    assert cortadas["tickers"].set_index("codigo").loc["AAAA4", "valido_ate"] == D(
        "2014-04-15"
    )


# --- universo ---------------------------------------------------------------------------------------
def test_companhia_cancelada_continua_nos_meses_em_que_existia(painel):
    b = painel[painel["cnpj"] == "B"]
    assert b["data"].min() == D("2012-05-31")  # a primeira ITR saiu em 15/05/2012
    assert b["data"].max() == D("2015-06-30")  # cancelada em 20/07/2015
    assert len(b) == 38


def test_so_entra_depois_da_primeira_entrega(painel):
    assert painel.loc[painel["cnpj"] == "C", "data"].min() == D("2014-08-31")
    assert painel.loc[painel["cnpj"] == "A", "data"].min() == como_era.INICIO


def test_tickers_valem_entre_a_entrega_do_fca_e_o_fim(painel):
    assert pd.isna(_linha(painel, "A", "2010-04-30")["tickers_na_data"])
    assert _linha(painel, "A", "2012-01-31")["tickers_na_data"] == "AAAA3, AAAA4"
    assert (
        _linha(painel, "A", "2014-04-30")["tickers_na_data"] == "AAAA3"
    )  # AAAA4 saiu em 15/04
    assert not _linha(painel, "C", "2015-12-31")["com_ticker_na_data"]
    assert pd.isna(
        _linha(painel, "A", "2010-04-30")["com_ticker_na_data"]
    )  # antes do 1º código
    assert _linha(painel, "C", "2016-03-31")["com_ticker_na_data"]


# --- nenhum bloco olha o futuro ---------------------------------------------------------------------
BLOCOS = {"universo": (universo.ENTRADAS, universo.montar)}


@pytest.mark.parametrize("bloco", BLOCOS)
@pytest.mark.parametrize(
    "data",
    [
        "2010-01-31",
        "2012-05-31",
        "2013-06-30",
        "2014-04-30",
        "2015-06-30",
        "2015-07-31",
        "2016-12-31",
    ],
)
def test_nenhum_bloco_olha_o_futuro(bloco, data):
    """A linha de cada data, montada só com o que era público nela, é a mesma da base inteira."""
    definicoes, montar = BLOCOS[bloco]
    dia = D(data)
    inteira = montar(_entradas(), FIM)
    cortada = montar(como_era.cortar(_entradas(), definicoes, dia), dia)
    pd.testing.assert_frame_equal(
        inteira[inteira["data"] == dia].reset_index(drop=True),
        cortada[cortada["data"] == dia].reset_index(drop=True),
    )
