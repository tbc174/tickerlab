"""Leitor do resumo do relatório mensal do Cecafé (café, PR 6); a coleta saiu em 22/10/2026 (ADR 0102, Emenda 1).

`cecafe_relatorio_pequeno.pdf` é um dublê (9 linhas) com números do relatório de setembro/2026.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from base.commodities import cecafe

PASTA = Path(__file__).parent / "arquivos" / "commodities"
AGORA = datetime(2026, 10, 18, 22, tzinfo=UTC)


def test_ler_pdf_cecafe_arabica_conilon_soluvel():
    resumo = cecafe.ler_resumo((PASTA / "cecafe_relatorio_pequeno.pdf").read_bytes())
    assert (resumo.ano, resumo.mes) == (2026, 9)
    assert resumo.sacas_por_tipo == {
        "arabica": 2766290,
        "canefora": 813904,
        "soluvel": 304899,
        "torrado": 8654,
    }
    assert resumo.sacas_por_destino == {"E.U.A.": 625192, "Alemanha": 482236}


def test_pdf_que_nao_e_o_relatorio_da_erro_claro():
    with pytest.raises(cecafe.RelatorioIlegivel):
        cecafe.ler_resumo(b"%PDF-1.4 nao e um pdf de verdade")
