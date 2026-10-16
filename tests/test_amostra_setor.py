"""Bloco "fundos, setor e macro" da amostra integrada (PR 4): fundos com a ação, números da operação pela
B13 (com a ligação no tempo, não a `principal` de hoje) e juros, como se sabia em cada fim de mês; e o
corte da base em cada data."""

import pandas as pd
import pytest

from base.amostra import como_era, setor

D = pd.Timestamp
A, B = "11.111.111/0001-11", "22.222.222/0001-22"


def _entradas() -> dict[str, pd.DataFrame]:
    empresa_serie = pd.DataFrame(
        {
            "fonte": ["aneel-samp", "aneel-samp", "anatel-acessos"],
            "chave": ["99999999000199", "99999999000199", "88888888000188"],
            "cnpj_companhia": ["11111111000111", "22222222000122", "11111111000111"],
            "via": ["controlada", "controlada", "propria"],
            "participacao": [100.0, 100.0, 100.0],
            # a distribuidora foi da A até o FRE de 2019 e passou à B no FRE de 2020
            "desde": [D("2015-05-30"), D("2021-05-28"), D("2015-05-30")],
            "ultima_referencia": [D("2019-12-31"), D("2025-12-31"), D("2025-12-31")],
        }
    )
    operacao = pd.DataFrame(
        {
            "fonte": ["aneel-samp"] * 3 + ["anatel-acessos"] * 2,
            "chave": ["99999999000199"] * 3 + ["88888888000188"] * 2,
            "competencia": [
                D("2019-03-31"),
                D("2020-03-31"),
                D("2021-03-31"),
                D("2020-01-31"),
                D("2021-01-31"),
            ],
            "valor": [100.0, 110.0, 120.0, 7.0, 9.0],
            "publico_em": [
                D("2019-05-30"),
                D("2020-05-30"),
                D("2021-05-30"),
                D("2020-03-31"),
                D("2021-04-01"),
            ],
        }
    )
    fundos = pd.DataFrame(
        {
            "cnpj": [A, A, A],
            "tipo": ["comprado", "comprado", "vendido"],
            "competencia": [D("2020-01-31"), D("2020-02-29"), D("2020-02-29")],
            "fundos": [10, 12, 3],
            "valor": [1e6, 2e6, 5e5],
            "fundos_no_bloco_8": [1, 2, 0],
            "valor_no_bloco_8": [1e4, 2e4, 0.0],
            "disponivel_em": [D("2020-04-30"), D("2020-05-29"), D("2020-05-29")],
        }
    )
    juros = pd.DataFrame(
        {
            "data_base": [D("2020-05-28")] * 3 + [D("2020-06-30")] * 3,
            "curva": ["nominal", "nominal", "real"] * 2,
            "prazo_anos": [1.0, 5.0, 5.0] * 2,
            "taxa": [0.03, 0.06, 0.03, 0.025, 0.055, 0.028],
            "disponivel_em": [D("2020-05-29")] * 3 + [D("2020-07-01")] * 3,
        }
    )
    return {
        "fundos": fundos,
        "operacao": operacao,
        "ligacoes": setor.ligacoes_no_tempo(empresa_serie),
        "juros": juros,
    }


def _grade() -> pd.DataFrame:
    meses = como_era.fins_de_mes(D("2019-01-31"), D("2021-12-31"))
    return pd.DataFrame(
        [(c, m) for c in (A, B) for m in meses], columns=["cnpj", "data"]
    )


@pytest.fixture(scope="module")
def painel():
    return setor.montar(_entradas(), _grade())


def _em(painel, cnpj, data):
    return painel[(painel["cnpj"] == cnpj) & (painel["data"] == D(data))].iloc[0]


def test_fundos_do_mes_de_carteira_mais_novo_ja_publico(painel):
    assert pd.isna(_em(painel, A, "2020-03-31")["fundos_com_a_acao"])
    assert _em(painel, A, "2020-04-30")["fundos_com_a_acao"] == 10
    linha = _em(painel, A, "2020-05-31")
    assert (linha["fundos_com_a_acao"], linha["fundos_no_bloco_8"]) == (
        12,
        2,
    )  # só o comprado


def test_operacao_vai_para_o_dono_na_data(painel):
    linha = _em(painel, A, "2020-06-30")
    assert (linha["consumidores_samp"], linha["consumidores_samp_12m_antes"]) == (
        110.0,
        100.0,
    )
    assert linha["consumidores_samp_competencia"] == D("2020-03-31")
    # em 2021 a distribuidora já é da B (FRE de 2020 entregue em 28/05/2021) e a A não soma mais
    assert pd.isna(_em(painel, A, "2021-06-30")["consumidores_samp"])
    assert _em(painel, B, "2021-06-30")["consumidores_samp"] == 120.0
    assert pd.isna(
        _em(painel, B, "2020-06-30")["consumidores_samp"]
    )  # antes da ligação


def test_volume_so_depois_de_publicado(painel):
    assert pd.isna(
        _em(painel, A, "2020-02-29")["acessos_anatel"]
    )  # o de janeiro saiu em 31/03
    assert _em(painel, A, "2020-03-31")["acessos_anatel"] == 7.0
    assert _em(painel, A, "2021-04-30")["acessos_anatel_12m_antes"] == 7.0


def test_juros_do_dia_mais_novo_ja_publico(painel):
    assert pd.isna(_em(painel, A, "2020-04-30")["juros_nominal_1a"])
    linha = _em(painel, B, "2020-06-30")
    assert (linha["juros_nominal_1a"], linha["juros_real_5a"]) == (
        0.03,
        0.03,
    )  # a de 30/06 sai em 01/07
    assert _em(painel, A, "2020-07-31")["juros_nominal_5a"] == 0.055


@pytest.mark.parametrize(
    "data",
    [
        "2019-06-30",
        "2020-03-31",
        "2020-05-31",
        "2020-06-30",
        "2021-04-30",
        "2021-06-30",
    ],
)
def test_nenhum_bloco_olha_o_futuro(data):
    dia = D(data)
    inteira = setor.montar(_entradas(), _grade())
    cortada = setor.montar(como_era.cortar(_entradas(), setor.ENTRADAS, dia), _grade())
    pd.testing.assert_frame_equal(
        inteira[inteira["data"] == dia].reset_index(drop=True),
        cortada[cortada["data"] == dia].reset_index(drop=True),
        check_dtype=False,
    )
