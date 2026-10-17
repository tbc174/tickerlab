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


LIBERUM = (
    "Eco Securitizadora 26, jun, 2018 CLASSIFICAÇÕES FE0051-2015 (CRA - Único - 74ª Série da 1ª "
    "Emissão) A-(fe) CP2(fe) COMITÊ - 19, jun, 2018 Confirmação dos Ratings A-(fe) de Crédito - "
    "Longo Prazo. Liberum Ratings."
)
MOODYS_LOCAL = (
    "1 Brasil 19 de setembro de 2024 CM Hospitalar S.A. RESUMO O perfil de crédito... Moody's Local "
    "Brasil. Rating Perspectiva CM Hospitalar S.A. Rating Corporativo (CFR) AA.br Negativa"
)
# os comunicados de várias companhias começam com contatos e analistas: o nome de quem entregou
# só aparece depois do começo do texto
CABECALHO = "Contatos e analistas da agência. " * 30
VARIAS_EMPRESAS = CABECALHO + (
    "Rating Action: Moody's altera perspectiva de companhias brasileiras para estável, de negativa "
    "17 Mar 2017. Ambev S.A.: debêntures afirmadas em Baa3 e em Aaa.br. Suzano Papel e Celulose "
    "S.A.: rating de emissor afirmado em Ba1 e Aa1.br na escala nacional."
)
SERENA = (
    "RATING ACTION COMMENTARY Fitch Remove Observação Negativa e Afirma Ratings do Grupo Serena; "
    "Perspectiva Estável 31 May 2024: A Fitch removeu a Observação Negativa e afirmou 'AA-(bra)'."
)
AUSTIN = (
    "Certificados de Recebíveis Imobiliários FORTE SECURITIZADORA – Relatório Analítico Rating "
    "brA(sf) Obrigações protegidas por elevadas margens de cobertura. Austin Rating."
)


def test_escala_fe_da_liberum():
    r = ratings.extrair_rating(LIBERUM)
    assert r is not None
    assert (r.agencia, r.escala, r.nota) == ("liberum", "nacional", "A-")


def test_letras_com_br_da_moodys_local():
    r = ratings.extrair_rating(MOODYS_LOCAL)
    assert r is not None
    assert (r.agencia, r.escala, r.nota, r.perspectiva) == (
        "moodys",
        "nacional",
        "AA",
        "negativa",
    )


def test_documento_de_varias_empresas_pega_a_nota_de_quem_entregou():
    r = ratings.extrair_rating(VARIAS_EMPRESAS, empresa="SUZANO PAPEL E CELULOSE S.A.")
    assert r is not None and r.nota == "Aa1"
    sem_empresa = ratings.extrair_rating(VARIAS_EMPRESAS)
    assert sem_empresa is not None and sem_empresa.nota == "Aaa"


def test_observacao_removida_nao_e_observacao():
    r = ratings.extrair_rating(SERENA)
    assert r is not None and r.perspectiva == "estavel"


def test_elevadas_margens_nao_e_elevacao():
    r = ratings.extrair_rating(AUSTIN)
    assert r is not None
    assert (r.agencia, r.nota, r.acao) == ("austin", "A", None)


def test_perspectiva_do_titulo_ganha_da_legenda_do_fim():
    texto = (
        "Fitch Afirma Rating 'AA(bra)' da Rodobens; Perspectiva Estável 07 Jul 2023: ... "
        "Rating Actions Rodobens S.A. Natl LT AA(bra) Affirmed RATINGS KEY OUTLOOK WATCH POSITIVE "
        "NEGATIVE EVOLVING STABLE"
    )
    r = ratings.extrair_rating(texto)
    assert r is not None and r.perspectiva == "estavel"


def test_data_no_formato_da_liberum():
    r = ratings.extrair_rating(LIBERUM)
    assert r is not None and r.data_acao == date(2018, 6, 26)


def test_tabela_de_varias_empresas_usa_a_mencao_mais_proxima():
    texto = CABECALHO + (
        "S&P Global Ratings revisou perspectivas: Brazil Realty S.A., MRS Logística S.A., Neoenergia "
        "S.A. Ultrafértil S.A. Ratings de Crédito Corporativo De Para Escala Nacional brAA/Estável/-- "
        "brAA/Positiva/-- MRS Logística S.A. Ratings de Crédito Corporativo De Para Escala global "
        "'BB-'/Estável/-- 'BB-'/Positiva/-- Neoenergia S.A. brAAA/Estável/--"
    )
    r = ratings.extrair_rating(texto, empresa="MRS LOGÍSTICA S/A")
    assert r is not None
    assert (r.escala, r.nota) == ("global", "BB-")


def test_nota_preliminar_da_austin_nao_conta():
    texto = (
        "Austin Rating. Histórico de atribuições: Mai/19: Indicação ‘brA-(sf)(p)’ Jun/19: "
        "Atribuição ‘brA(sf) Set/19: Confirmação ‘brA(sf)"
    )
    r = ratings.extrair_rating(texto)
    assert r is not None and r.nota == "A"


def test_acoes_em_varias_series_nao_viram_um_rating_so():
    texto = (
        "Fitch Realiza Ações de Rating em Seis Séries de CRIs da Brazilian Securities 19 Mai 2015: "
        "Série 2007-74: rating afirmado em 'A+sf(bra)'; Série 2009-130: rating afirmado em "
        "'Asf(bra)'; Série 2010-156: rating rebaixado para 'BBBsf(bra)'"
    )
    assert ratings.extrair_rating(texto) is None


def test_companhia_no_titulo_segue_a_regra_de_sempre():
    """Uma companhia só (o nome no título): a escala nacional ganha, mesmo com a global perto."""
    texto = (
        "FITCH UPGRADES MINERVA TO 'BB-' Fitch has upgraded the IDRs of Minerva S.A. to 'BB-' from "
        "'B+'. Fitch has also upgraded Minerva's National Scale rating to 'A-(bra)' from "
        "'BBB+(bra)'. The Rating Outlook is Stable."
    )
    r = ratings.extrair_rating(texto, empresa="MINERVA S/A")
    assert r is not None
    assert (r.escala, r.nota) == ("nacional", "A-")


def test_varias_companhias_sem_a_nota_de_quem_entregou_nao_chuta():
    texto = CABECALHO + (
        "S&P Global Ratings revisou perspectivas. Ultrafértil S.A. Escala Nacional brAA/Estável/-- "
        "MRS Logística S.A. Escala global BB-/Estável/-- Neoenergia S.A. brAAA/Estável/--"
    )
    assert ratings.extrair_rating(texto, empresa="MRS LOGÍSTICA S/A") is None


def test_nome_antigo_no_documento_segue_como_uma_companhia_so():
    """O IPE guarda o nome de hoje (Banco Voiter); o documento de 2012 diz Banco Indusval."""
    texto = (
        CABECALHO
        + "Fitch afirmou os Ratings do Banco Indusval S.A.: 'BBB(bra)', Perspectiva Estável"
    )
    r = ratings.extrair_rating(texto, empresa="BANCO VOITER S.A.")
    assert r is not None and r.nota == "BBB"


def test_simbolos_no_texto_nao_desalinham_o_nome_da_nota():
    """Tirar acentos e símbolos ("•", aspas curvas) não pode mudar as posições: em documento
    longo, a nota "perto do nome" virava a de outra companhia (Rio Paranapanema, S&P, jan/2018)."""
    texto = CABECALHO + (
        "S&P Global Ratings. Raízen Energia S.A. Escala Nacional Brasil brAAA/Estável/-- "
        + "• “Grupo” ’ " * 150
        + "• Rio Paranapanema Energia S.A (BB/Estável/--; brAA+/Estável/--). "
        "Telefônica Brasil S.A. brAAA em CreditWatch"
    )
    r = ratings.extrair_rating(texto, empresa="RIO PARANAPANEMA ENERGIA SA")
    assert r is not None and r.nota == "AA+"


def test_palavra_comum_no_nome_nao_faz_o_documento_ser_de_varias():
    texto = (
        "RATING ACTION COMMENTARY Fitch Afirma Rating ‘AAA(bra)’ do Mateus; Perspectiva Estável. "
        + CABECALHO
        + "Informações do Grupo Mateus S.A. ANÁLISE DE PARES: CBD, AA(bra)/Perspectiva Negativa"
    )
    r = ratings.extrair_rating(texto, empresa="GRUPO MATEUS S.A.")
    assert r is not None and r.nota == "AAA"


def test_tabela_de_para_da_sp_vale_a_coluna_para():
    texto = CABECALHO + (
        "S&P Global Ratings revisou ratings. RODOVIAS DAS COLINAS S.A. Ratings de Crédito de "
        "Emissor De Para Escala Nacional Brasil brA/Estável/-- brA+/Estável/-- OUTRA EMPRESA S.A."
    )
    r = ratings.extrair_rating(texto, empresa="RODOVIAS DAS COLINAS S.A.")
    assert r is not None and r.nota == "A+"
