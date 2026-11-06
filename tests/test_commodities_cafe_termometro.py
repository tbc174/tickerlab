"""Termômetro da CONAB: quanto o 1º levantamento errou em relação ao 4º (em tela e API com a data citada)."""

import json
from dataclasses import asdict
from datetime import date

import pytest

from src.commodities.cafe.pontos import PontoDaSafra, citacao
from src.commodities.cafe.termometro import erro_do_primeiro_levantamento, vies_medio
from tests.ajudantes_do_cafe import tabela

PRODUCOES = {
    2020: {1: 110.0, 2: 105.0, 3: 100.0, 4: 100.0},
    2021: {1: 90.0, 2: 92.0, 3: 95.0, 4: 100.0},
    2022: {1: 50.0, 2: 52.0},  # safra em curso: sem 4º levantamento
}


def _pct(pontos):
    return {p.safra: p.valor for p in pontos if p.serie == "erro_1o_levantamento_pct"}


def test_erro_e_o_primeiro_menos_o_quarto_em_porcentagem_do_quarto():
    pontos = erro_do_primeiro_levantamento(tabela(PRODUCOES), "arabica")
    assert _pct(pontos) == {2020: pytest.approx(10.0), 2021: pytest.approx(-10.0)}


def test_erro_tambem_sai_em_mil_sacas():
    pontos = erro_do_primeiro_levantamento(tabela(PRODUCOES), "arabica")
    sacas = {
        p.safra: p.valor for p in pontos if p.serie == "erro_1o_levantamento_mil_sacas"
    }
    assert sacas == {2020: 10.0, 2021: -10.0}


def test_safra_sem_o_quarto_levantamento_nao_entra():
    assert 2022 not in _pct(erro_do_primeiro_levantamento(tabela(PRODUCOES), "arabica"))


def test_corte_em_d_nao_muda_o_passado():
    inteira = tabela(PRODUCOES)
    antes = erro_do_primeiro_levantamento(inteira, "arabica", ate=date(2021, 12, 3))
    depois = erro_do_primeiro_levantamento(inteira, "arabica", ate=date(2022, 12, 31))
    assert _pct(antes) == {2020: pytest.approx(10.0)}  # o 4º de 2021 saiu em 04/12
    assert _pct(depois)[2020] == _pct(antes)[2020]


def test_revisao_do_quarto_levantamento_so_vale_depois_de_divulgada():
    t = tabela({2020: {1: 110.0, 4: 100.0}})
    revisao = t.iloc[[1]].assign(
        producao_mil_sacas=88.0,
        divulgado_em=t["divulgado_em"].iloc[1].replace(year=2021),
    )
    import pandas as pd

    t = pd.concat([t, revisao], ignore_index=True)
    assert _pct(erro_do_primeiro_levantamento(t, "arabica", ate=date(2020, 12, 31)))[
        2020
    ] == (pytest.approx(10.0))
    assert _pct(erro_do_primeiro_levantamento(t, "arabica", ate=date(2021, 12, 31)))[
        2020
    ] == (pytest.approx(25.0))


def test_tipos_nao_se_misturam():
    arabica = tabela(PRODUCOES, tipo="arabica")
    conilon = tabela({2020: {1: 40.0, 4: 50.0}}, tipo="conilon")
    import pandas as pd

    junto = pd.concat([arabica, conilon], ignore_index=True)
    assert _pct(erro_do_primeiro_levantamento(junto, "conilon")) == {
        2020: pytest.approx(-20.0)
    }


def test_vies_medio_das_ultimas_dez_safras():
    producoes = {
        2000 + i: {1: 110.0 if i < 5 else 90.0, 4: 100.0} for i in range(12)
    }  # 2000-04: +10 %; 2005-11: -10 %
    pontos = vies_medio(tabela(producoes), "arabica")
    assert len(pontos) == 1
    ponto = pontos[0]
    assert ponto.safra == 2011 and ponto.serie == "vies_medio_10_safras_pct"
    # últimas 10 safras = 2002 a 2011: três com +10 % e sete com -10 %
    assert ponto.valor == pytest.approx((3 * 10 - 7 * 10) / 10)


def test_vies_com_menos_de_tres_safras_nao_devolve_numero():
    assert vies_medio(tabela({2020: {1: 110.0, 4: 100.0}}), "arabica") == []


def test_pontos_viram_json():
    pontos = erro_do_primeiro_levantamento(tabela(PRODUCOES), "arabica")
    assert all(isinstance(p, PontoDaSafra) for p in pontos)
    assert json.loads(json.dumps([asdict(p) for p in pontos]))[0]["tipo"] == "arabica"


def test_cada_ponto_cita_a_data_do_quarto_levantamento_que_usa():
    # ADR 0102: o número vai para tela e API com a CONAB e a data citadas; o erro só existe quando
    # o 4º levantamento sai, então é essa a data
    t = tabela(PRODUCOES)
    quarto_de_2021 = t[(t["safra"] == 2021) & (t["levantamento"] == 4)]["divulgado_em"]
    pontos = erro_do_primeiro_levantamento(t, "arabica")
    datas = {p.safra: p.divulgado_em for p in pontos}
    assert datas[2021] == quarto_de_2021.iloc[0].date().isoformat()
    assert citacao(pontos[-1]) == (
        "CONAB, Acompanhamento da Safra Brasileira de Café, levantamentos divulgados até "
        f"{quarto_de_2021.iloc[0]:%d/%m/%Y} (CC BY-ND 3.0)"
    )


def test_vies_medio_cita_a_data_da_ultima_safra_que_entra():
    producoes = {2000 + i: {1: 110.0, 4: 100.0} for i in range(5)}
    [ponto] = vies_medio(tabela(producoes), "arabica")
    assert ponto.divulgado_em == "2004-12-04"
    assert "até 04/12/2004" in citacao(ponto)


def test_ponto_sem_data_cita_so_a_fonte_e_a_licenca():
    ponto = PontoDaSafra(2020, "arabica", "BRASIL", "x", 1.0, "u")
    assert citacao(ponto) == (
        "CONAB, Acompanhamento da Safra Brasileira de Café (CC BY-ND 3.0)"
    )
