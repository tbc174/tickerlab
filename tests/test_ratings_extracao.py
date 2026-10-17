"""Extração do rating do texto dos documentos do IPE: agência, escala, nota, perspectiva, ação e data.

Os trechos imitam os documentos reais da amostra da prova (16/10/2026), encurtados."""

from datetime import date

import pytest

from base import ratings

FITCH_NACIONAL = (
    "RATING ACTION COMMENTARY Fitch Afirma Rating 'AA(bra)' da Rodobens; Perspectiva Estável "
    "Fitch Ratings - Rio de Janeiro - 07 Jul 2023: A Fitch Ratings afirmou o Rating Nacional de "
    "Longo Prazo 'AA(bra)', com Perspectiva Estável, da Rodobens S.A."
)
FITCH_REBAIXA = (
    "RATING ACTION COMMENTARY Fitch Rebaixa Rating da Oncoclínicas Para ‘RD(bra)’ Brazil "
    "Tue 07 Apr, 2026 - 17:03 ET Fitch Ratings - Rio de Janeiro - 07 Apr 2026: A Fitch Ratings "
    "rebaixou o Rating Nacional de Longo Prazo da Oncoclínicas para ‘RD(bra)’, de ‘C(bra)’."
)
FITCH_SF_EXP = (
    "RATING ACTION COMMENTARY Fitch Atribui Rating ‘AA(EXP)(bra)’ à Proposta de 3ª Emissão de "
    "Debêntures da Way 112 Thu 10 Jul, 2025 - 16:26 ET Fitch Ratings - São Paulo - 10 Jul 2025: "
    "A Fitch Ratings atribuiu Rating Nacional de Longo Prazo ‘AA(EXP)(bra)’, com Perspectiva Estável"
)
FITCH_CRI = (
    "FITCH AFIRMA RATING 'AAASF(BRA)' DA 185A SERIE DA 1A EMISSAO DE CRIS Fitch Ratings-Sao "
    "Paulo-15 May 2013: A Fitch Ratings afirmou, hoje, o Rating Nacional de Longo Prazo 'AAAsf(bra)'"
)
FITCH_GLOBAL = (
    "FITCH RATINGS UPGRADES MINERVA TO 'BB-'; OUTLOOK STABLE Fitch Ratings-New York-16 December "
    "2013: Fitch has upgraded the issuer default ratings (IDRs) of Minerva S.A. to 'BB-' from 'B+'."
)
SP_COMUNICADO = (
    "RANDON S.A. IMPLEMENTOS E PARTICIPAÇÕES CNPJ 89.086.144/0011-98 Comunicado ao Mercado A "
    "Randoncorp | [B3: RAPT3, RAPT4], comunica que, em 25 de outubro de 2024, a agência de "
    "classificação de risco Standard & Poor’s Global Ratings (“S&P”) elevou o rating corporativo "
    "da Companhia na Escala Nacional Brasil de brAA+ para brAAA, com perspectiva estável."
)
SP_PERSPECTIVA = (
    "Data de Publicação: 23 de novembro de 2011 Comunicado à Imprensa Perspectiva dos ratings da "
    "Suzano alterada de estável para negativa; Ratings 'BB+' reafirmados Analistas: Luísa Vilhena, "
    "luisa_vilhena@standardandpoors.com. A Standard & Poor's reafirmou o rating 'brAAA'."
)
MOODYS = (
    "Rating Action: Moody's atribui ratings definitivos Ba1 / Aaa.br às 1ª e 2ª séries da 14ª "
    "emissão de CRA emitidos pela Vert Securitizadora Global Credit Research - 11 Oct 2017"
)
GERDAU_B3 = (
    "GERDAU S.A. COMUNICADO AO MERCADO A GERDAU S.A. (B3: GGBR / NYSE: GGB) comunica que, em "
    "relatório divulgado nesta data, a Fitch Ratings elevou os Ratings de Longo Prazo em Moeda "
    "Estrangeira (IDRs) para “BBB”, antes “BBB-”, e afirmou os Ratings na Escala Nacional em "
    "“AAA(bra)”. Rio de Janeiro, 8 de junho de 2022."
)


def test_fitch_escala_nacional_afirmacao():
    r = ratings.extrair_rating(FITCH_NACIONAL)
    assert r is not None
    assert (r.agencia, r.escala, r.nota, r.perspectiva, r.acao) == (
        "fitch",
        "nacional",
        "AA",
        "estavel",
        "afirmacao",
    )
    assert r.data_acao == date(2023, 7, 7)


def test_rebaixamento_pega_a_nota_nova_e_guarda_a_antiga():
    r = ratings.extrair_rating(FITCH_REBAIXA)
    assert r is not None
    assert (r.nota, r.acao, r.data_acao) == ("RD", "rebaixamento", date(2026, 4, 7))
    assert "C" in r.outras_notas


def test_sufixos_sf_e_exp_saem_da_nota():
    exp = ratings.extrair_rating(FITCH_SF_EXP)
    cri = ratings.extrair_rating(FITCH_CRI)
    assert exp is not None and cri is not None
    assert (exp.nota, exp.acao, exp.data_acao) == (
        "AA",
        "atribuicao",
        date(2025, 7, 10),
    )
    assert (cri.nota, cri.acao, cri.data_acao) == (
        "AAA",
        "afirmacao",
        date(2013, 5, 15),
    )


def test_escala_global_quando_nao_ha_nacional():
    r = ratings.extrair_rating(FITCH_GLOBAL)
    assert r is not None
    assert (r.agencia, r.escala, r.nota, r.acao, r.perspectiva) == (
        "fitch",
        "global",
        "BB-",
        "elevacao",
        "estavel",
    )
    assert r.data_acao == date(2013, 12, 16)


def test_comunicado_da_companhia_sobre_a_sp():
    r = ratings.extrair_rating(SP_COMUNICADO)
    assert r is not None
    assert (r.agencia, r.escala, r.nota, r.acao, r.perspectiva) == (
        "sp",
        "nacional",
        "AAA",
        "elevacao",
        "estavel",
    )
    assert r.data_acao == date(2024, 10, 25)
    assert "AA+" in r.outras_notas


def test_perspectiva_alterada_vale_a_nova():
    r = ratings.extrair_rating(SP_PERSPECTIVA)
    assert r is not None
    assert (r.agencia, r.nota, r.perspectiva, r.acao) == (
        "sp",
        "AAA",
        "negativa",
        "afirmacao",
    )


def test_moodys_escala_nacional():
    r = ratings.extrair_rating(MOODYS)
    assert r is not None
    assert (r.agencia, r.escala, r.nota, r.nivel, r.acao) == (
        "moodys",
        "nacional",
        "Aaa",
        1,
        "atribuicao",
    )


def test_b3_da_bolsa_nao_e_nota():
    r = ratings.extrair_rating(GERDAU_B3)
    assert r is not None
    assert (r.agencia, r.escala, r.nota) == ("fitch", "nacional", "AAA")
    assert "B3" not in r.outras_notas


@pytest.mark.parametrize(
    "texto",
    [
        "",
        "   ",
        "/0/1/2/1/3/2/0/1/0/1/4 /5/6/7/8/i255/10",
        "tabela A1 e A3 sem agência",
    ],
)
def test_sem_nota_no_texto_nao_inventa(texto):
    assert ratings.extrair_rating(texto) is None


def test_nivel_compara_agencias():
    assert ratings.nivel("AAA") == ratings.nivel("Aaa") == 1
    assert ratings.nivel("AA-") == ratings.nivel("Aa3") == 4
    assert ratings.nivel("BB+") == ratings.nivel("Ba1")
    assert ratings.nivel("RD") > ratings.nivel("C")
    assert ratings.nivel("xyz") is None
