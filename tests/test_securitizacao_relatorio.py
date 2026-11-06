"""PDF dos cenários da cascata (src/securitizacao/relatorio.py): gera, e traz versão, hash e limites."""

import dataclasses
from datetime import datetime
from io import BytesIO

from pypdf import PdfReader

from src.relatorio_empresa_pdf import FUSO
from src.securitizacao.cascata import VERSAO_DO_CALCULO, Regras
from src.securitizacao.cenarios import (
    REGRAS_DA_0_2_0_LIGADAS,
    carteira_sintetica,
    hash_da_entrada,
    rodar_cenarios,
)
from src.securitizacao.relatorio import (
    _cdr,
    _reais,
    descrever_regras,
    relatorio_dos_cenarios,
)


def _texto_do_pdf() -> str:
    carteira, estrutura = carteira_sintetica()
    pdf = relatorio_dos_cenarios(
        carteira,
        estrutura,
        rodar_cenarios(carteira, estrutura),
        gerado_em=datetime(2026, 10, 20, 12, 0, tzinfo=FUSO),
    )
    assert pdf.startswith(b"%PDF")
    return "\n".join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)


def test_pdf_traz_versao_do_motor_e_hash_da_carteira():
    carteira, estrutura = carteira_sintetica()
    texto = "".join(_texto_do_pdf().split())  # o hash pode quebrar de linha
    assert "".join(VERSAO_DO_CALCULO.split()) in texto
    assert hash_da_entrada(carteira, estrutura) in texto


def test_pdf_traz_estrutura_cenarios_reconciliacao_e_limites():
    texto = _texto_do_pdf()
    for esperado in (
        "Estrutura da operação",
        "Cenários lado a lado",
        "Reconciliação do caixa",
        "Limites e cuidados",
        "inadimplência ×2",
        "carteira sintética",
    ):
        assert esperado in texto


def test_reais_no_formato_brasileiro():
    assert _reais(123_456_789) == "1.234.567,89"
    assert _reais(-5) == "-0,05"


def test_limites_falam_da_versao_atual_e_o_pdf_mostra_as_regras():
    texto = _texto_do_pdf()
    assert "0.1.0" not in texto
    assert "Regras da cascata" in texto
    assert "juros não pagos acumulam: não" in texto


def test_regras_ligadas_aparecem_no_pdf():
    carteira, estrutura = carteira_sintetica()
    estrutura = dataclasses.replace(
        estrutura,
        regras=Regras(
            juros_acumulam=True,
            principal="pro_rata",
            gatilho_de_perda=0.05,
            meta_de_sobrecolateralizacao=0.2,
        ),
    )
    texto = descrever_regras(estrutura.regras)
    assert "juros não pagos acumulam: sim" in texto
    assert (
        "principal pro rata até a perda acumulada passar de 5,0% do pool original"
        in texto
    )
    assert "turbo até a sobrecolateralização de 20,0% do pool" in texto
    pdf = relatorio_dos_cenarios(
        carteira, estrutura, rodar_cenarios(carteira, estrutura)
    )
    assert pdf.startswith(b"%PDF")


def test_pro_rata_sem_gatilho_e_dito_assim():
    assert "principal pro rata, sem gatilho" in descrever_regras(
        Regras(principal="pro_rata")
    )


def test_pdf_traz_vida_media_e_cdr_de_equilibrio_de_cada_classe():
    texto = _texto_do_pdf()
    assert "Vida média e CDR de equilíbrio" in texto
    for classe in ("senior", "mezanino", "subordinada"):
        assert f"Vida média (anos): {classe}" in texto
    assert "CDR de equilíbrio" in texto
    assert "bissecção" in texto  # o método está dito nos limites


def test_pdf_roda_os_cenarios_com_as_regras_da_0_2_0_ligadas():
    texto = _texto_do_pdf()
    assert "Com as regras da 0.2.0 ligadas" in texto
    assert descrever_regras(REGRAS_DA_0_2_0_LIGADAS) in " ".join(texto.split())
    assert "Limites e cuidados" in texto


def test_sem_regras_comparadas_o_pdf_nao_repete_os_cenarios():
    carteira, estrutura = carteira_sintetica()
    pdf = relatorio_dos_cenarios(
        carteira,
        estrutura,
        rodar_cenarios(carteira, estrutura),
        regras_comparadas=None,
    )
    texto = "\n".join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)
    assert "Com as regras da 0.2.0 ligadas" not in texto
    assert "Limites e cuidados" in texto


def test_cdr_de_equilibrio_no_formato_brasileiro_e_os_extremos_por_extenso():
    assert _cdr(0.19830322265625) == "19,83%"
    assert _cdr(None) == "perde com CDR 0"
    assert _cdr(1.0) == "não perde"
    assert _cdr(0.0) == "menos de 0,01%"  # a virada fica abaixo da tolerância


def test_taxas_dos_cenarios_com_virgula_decimal():
    texto = _texto_do_pdf()
    assert "6,0%" in texto and "12,0%" in texto
    assert "6.0%" not in texto
