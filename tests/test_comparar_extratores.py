"""Comparação dos extratores de PDF contra o gabarito (marco 3 do plano de 05/11/2026, ADR 0124).

A régua é o gabarito conferido à mão: um extrator "recupera" um fato quando o número aparece impresso numa
das páginas que o gabarito cita. Mede-se, não se aprova: nenhuma confiança declarada vira fato.
"""

import importlib.util

import pandas as pd
import pytest
from fpdf import FPDF

from scripts import comparar_extratores as comparar

SHA = "a" * 64


def _pdf(*linhas: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=14)
    for linha in linhas:
        pdf.cell(0, 12, linha, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


PDF = _pdf(
    "Divida total (em R$ mil): 41.250",
    "Spread: IPCA + 3,63% a.a.",
    "Vencimento: 11/2030",
)
GABARITO = pd.DataFrame(
    {
        "documento_sha256": [SHA] * 3,
        "medida": ["divida_total", "spread_sobre_ipca_aa", "vencimento"],
        "valor": ["41250000.00", "3.63", "2030-11"],
        "unidade": ["BRL", "pp_aa", "data"],
        "pagina_pdf": ["1", "1", "1"],
    }
)


def test_formas_impressas_do_valor():
    assert {"41.250.000,00", "41.250"} <= set(
        comparar.formas_impressas("41250000.00", "BRL")
    )
    # não é exato em mil: só a forma em reais
    assert comparar.formas_impressas("70110365.27", "BRL") == ["70.110.365,27"]
    assert comparar.formas_impressas("3.63", "pp_aa") == ["3,63"]
    assert comparar.formas_impressas("2030-11", "data") == ["11/2030"]
    assert comparar.formas_impressas("2027-01-15", "data") == ["15/01/2027"]


def test_paginas_do_gabarito():
    assert comparar.paginas("27-28") == [27, 28]
    assert comparar.paginas("882") == [882]


def test_numero_dentro_de_outro_nao_conta():
    assert comparar.aparece(["41.250"], "total 41.250 mil")
    assert not comparar.aparece(["41.250"], "total 141.250 mil")
    assert not comparar.aparece(["41.250"], "total 41.250.000,00")
    assert not comparar.aparece(["3,63"], "taxa 13,635")


def test_mede_recuperacao_por_campo():
    def cego(pdf: bytes, pagina: int) -> str:  # perde o vencimento
        return comparar.extrair_por_texto(pdf, pagina).replace("11/2030", "")

    extratores = {
        "texto": comparar.extrair_por_texto,
        "posicao": comparar.extrair_por_posicao,
        "cego": cego,
    }
    tabela = comparar.comparar(GABARITO, {SHA: PDF}, extratores)
    assert len(tabela) == 9  # 3 fatos x 3 extratores
    resumo = comparar.recuperacao(tabela)
    assert resumo["texto"] == pytest.approx(1.0)
    assert resumo["posicao"] == pytest.approx(1.0)
    assert resumo["cego"] == pytest.approx(2 / 3)
    por_campo = comparar.recuperacao(tabela, por="medida")
    assert por_campo.loc["vencimento", "cego"] == 0
    assert por_campo.loc["divida_total", "cego"] == 1


def test_fato_sem_original_fica_de_fora_e_e_contado():
    outro = GABARITO.assign(documento_sha256="b" * 64)
    tabela = comparar.comparar(
        pd.concat([GABARITO, outro]), {SHA: PDF}, {"texto": comparar.extrair_por_texto}
    )
    assert len(tabela) == 3
    assert comparar.sem_original(pd.concat([GABARITO, outro]), {SHA: PDF}) == {"b" * 64}


def test_relato_mostra_a_recuperacao_e_os_que_faltaram():
    tabela = comparar.comparar(
        GABARITO, {SHA: PDF}, {"texto": comparar.extrair_por_texto}
    )
    texto = comparar.relato(tabela, faltam={"b" * 64}, data="2026-11-05")
    assert "100%" in texto
    assert "texto" in texto
    assert "b" * 64 in texto
    assert "não aprova" in texto


@pytest.mark.skipif(not importlib.util.find_spec("rapidocr"), reason="sem o rapidocr")
def test_ocr_le_a_pagina_desenhada():
    lido = comparar.extrair_por_ocr(PDF, 1)
    assert comparar.aparece(["41.250"], lido)


def test_fato_em_duas_paginas_vale_se_aparece_em_qualquer_uma():
    pdf = FPDF()
    pdf.set_font("Helvetica", size=14)
    for linha in (
        "Divida total (em R$ mil): 41.250",
        "Notas explicativas, continuacao",
    ):
        pdf.add_page()
        pdf.cell(0, 12, linha)
    gabarito = GABARITO.iloc[:1].assign(pagina_pdf="1-2")
    tabela = comparar.comparar(
        gabarito, {SHA: bytes(pdf.output())}, {"texto": comparar.extrair_por_texto}
    )
    assert tabela["achou"].tolist() == [True]
