"""Exportações de café por NCM, UF e destino, recortadas do Comex Stat (café, PR 6; ADR 0094).

`tests/arquivos/commodities/comex_exp_cafe_pequeno.csv`: 18 linhas reais do EXP_2025 do Comex
(Minas Gerais e Espírito Santo, Estados Unidos e Bélgica, outubro e novembro, NCMs do café) mais duas
de outros produtos, que o recorte tem de largar.
"""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from base.commodities import comex_cafe

PASTA = Path(__file__).parent / "arquivos" / "commodities"
COLETADO_EM = date(2026, 1, 20)


@pytest.fixture(scope="module")
def cafe() -> pd.DataFrame:
    return comex_cafe.ler(
        (PASTA / "comex_exp_cafe_pequeno.csv").read_bytes(),
        (PASTA / "comex_pais_pequeno.csv").read_bytes(),
        COLETADO_EM,
    )


def test_recorte_por_ncm_do_cafe(cafe):
    assert list(cafe.columns) == list(comex_cafe.COLUNAS)
    assert set(cafe["ncm"]) == set(comex_cafe.NCMS_DO_CAFE)
    assert comex_cafe.NCMS_DO_CAFE == ("09011110", "09011190", "09012100", "21011110")
    assert len(cafe) == 18  # as 2 linhas de outros produtos ficaram de fora


def test_sacas_sao_o_peso_liquido_por_60(cafe):
    assert (cafe["sacas"] == cafe["kg_liquido"] / 60).all()
    linha = cafe[(cafe["ncm"] == "09011110") & (cafe["uf_origem"] == "MG")].iloc[0]
    assert linha["sacas"] == pytest.approx(linha["kg_liquido"] / 60)
    assert cafe["vl_fob_usd"].dtype.kind == "f"


def test_es_e_proxy_de_conilon_fica_marcado(cafe):
    # a NCM não separa arábica de conilon: nada de adivinhar; o ES é só uma pista (ADR 0094)
    assert set(cafe["tipo"]) == {"total"}
    assert (cafe["proxy_conilon"] == (cafe["uf_origem"] == "ES")).all()
    assert cafe["proxy_conilon"].any() and not cafe["proxy_conilon"].all()


def test_competencia_e_fim_do_mes_e_o_destino_tem_nome(cafe):
    assert set(cafe["competencia"]) >= {pd.Timestamp("2025-10-31")}
    assert cafe["pais_destino"].notna().all()
    assert {"Estados Unidos", "Bélgica"} <= set(cafe["pais_destino"])
    assert (cafe["divulgado_em"] == pd.Timestamp(COLETADO_EM)).all()


def test_soma_as_linhas_de_vias_e_unidades_diferentes():
    bruto = pd.DataFrame(
        {
            "CO_ANO": ["2025", "2025"],
            "CO_MES": ["10", "10"],
            "CO_NCM": ["09011110", "09011110"],
            "CO_PAIS": ["249", "249"],
            "SG_UF_NCM": ["MG", "MG"],
            "CO_VIA": ["01", "04"],
            "KG_LIQUIDO": ["600", "1200"],
            "VL_FOB": ["1000", "2000"],
        }
    )
    recorte = comex_cafe.recortar_cafe(bruto)
    assert len(recorte) == 1
    assert recorte.iloc[0]["sacas"] == 30 and recorte.iloc[0]["vl_fob_usd"] == 3000


def test_corte_em_d(cafe):
    """Sem olhar o futuro (ADR 0024): cortar o futuro não muda o passado."""
    revisada = cafe.copy()
    revisada["kg_liquido"] = revisada["kg_liquido"] * 2
    revisada["sacas"] = revisada["kg_liquido"] / 60
    revisada["divulgado_em"] = pd.Timestamp("2026-02-20")
    tabela = pd.concat([cafe, revisada], ignore_index=True)

    antes = comex_cafe.como_estava_em(tabela, date(2026, 2, 1))
    assert len(antes) == len(cafe)
    pd.testing.assert_frame_equal(
        antes.sort_values(comex_cafe.CHAVE).reset_index(drop=True),
        cafe.sort_values(comex_cafe.CHAVE).reset_index(drop=True),
        check_dtype=False,
    )
    depois = comex_cafe.como_estava_em(tabela, date(2026, 3, 1))
    assert depois["kg_liquido"].sum() == 2 * cafe["kg_liquido"].sum()
    # antes da primeira coleta não havia nada
    assert comex_cafe.como_estava_em(tabela, date(2026, 1, 1)).empty
