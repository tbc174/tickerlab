"""PDF dos cenários da cascata (src/securitizacao/relatorio.py): gera, e traz versão, hash e limites."""

from datetime import datetime
from io import BytesIO

from pypdf import PdfReader

from src.relatorio_empresa_pdf import FUSO
from src.securitizacao.cascata import VERSAO_DO_CALCULO
from src.securitizacao.cenarios import (
    carteira_sintetica,
    hash_da_entrada,
    rodar_cenarios,
)
from src.securitizacao.relatorio import _reais, relatorio_dos_cenarios


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
