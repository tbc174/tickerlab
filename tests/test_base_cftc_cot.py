"""Leitor comum do COT da CFTC (`base/commodities/cftc_cot.py`): o Bitcoin não muda de resultado."""

import io
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from base.commodities.cftc_cot import (
    COLUNAS_AGRO,
    CONTRATOS_AGRO,
    como_estava_em,
    ler_disaggregated,
)
from base.cripto.cftc import ler_tff

AMOSTRA_TFF = (
    Path(__file__).parent / "arquivos" / "cripto" / "cftc" / "FinFutYY_amostra.txt"
)


def _zip(texto: bytes) -> bytes:
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as arquivo:
        arquivo.writestr("arquivo.txt", texto)
    return memoria.getvalue()


def test_cripto_continua_igual():
    # resultado do leitor do Bitcoin, gravado antes de o leitor virar comum ao café
    esperado = pd.DataFrame(
        {
            "relatorio": [date(2026, 9, 29)] * 2 + [date(2026, 10, 6)] * 2,
            "contratos_em_aberto": [19596, 26320, 21432, 34582],
            "gestores_comprados": [5069, 2258, 5174, 2404],
            "gestores_vendidos": [1483, 67, 1642, 76],
            "alavancados_comprados": [4980, 9896, 5731, 13371],
            "alavancados_vendidos": [11836, 21256, 12583, 29798],
            "contrato": ["bitcoin", "micro_bitcoin"] * 2,
            "divulgado_em": pd.to_datetime(
                [datetime(2026, 10, 5, 19, 30, tzinfo=UTC)] * 2
                + [datetime(2026, 10, 12, 19, 30, tzinfo=UTC)] * 2
            ),
        }
    )

    obtido = ler_tff(_zip(AMOSTRA_TFF.read_bytes()))

    pd.testing.assert_frame_equal(obtido, esperado, check_dtype=False)


# --- Disaggregated: café e os outros agro (PR 5 do plano do café) ---

AMOSTRA_AGRO = (
    Path(__file__).parent.parent
    / "dados_de_exemplo"
    / "commodities"
    / "cot_disaggregated_pequeno.txt"
)


def _agro() -> pd.DataFrame:
    return ler_disaggregated(_zip(AMOSTRA_AGRO.read_bytes()))


def test_ler_cot_disaggregated_cafe():
    tabela = _agro().set_index(["relatorio", "contrato"])

    linha = tabela.loc[(pd.Timestamp("2026-10-06"), "cafe-arabica")]
    assert linha["open_interest"] == 162_806
    assert linha["producer_merchant_long"] == 41_575
    assert linha["producer_merchant_short"] == 61_950
    assert linha["swap_long"] == 25_576
    assert linha["swap_short"] == 22_713
    assert linha["managed_money_long"] == 37_043
    assert linha["managed_money_short"] == 18_007


def test_so_ficam_os_contratos_agro_da_lista_e_o_codigo_mantem_o_zero_da_frente():
    tabela = _agro()

    # a amostra tem café, açúcar e um trigo (fora da lista): 3 semanas × 2 contratos
    assert sorted(tabela["contrato"].unique()) == ["acucar", "cafe-arabica"]
    assert len(tabela) == 6


def test_contratos_agro_tem_os_codigos_conferidos_no_arquivo():
    # códigos lidos no arquivo fut_disagg_txt_2026.zip da CFTC em 18/10/2026
    assert {c: nome for c, (nome, _) in CONTRATOS_AGRO.items()} == {
        "083731": "cafe-arabica",
        "080732": "acucar",
        "005602": "soja",
        "002602": "milho",
        "057642": "boi-gordo",
        "033661": "algodao",
    }


def test_colunas_da_tabela_sao_as_do_contrato():
    assert list(_agro().columns) == list(COLUNAS_AGRO)


def test_corte_em_d_o_cot_da_terca_nao_existe_na_quarta():
    tabela = _agro()
    terca = pd.Timestamp(
        "2026-10-06"
    )  # relatório de terça; sai na segunda 12/10, 15h30 de NY

    assert (
        terca not in como_estava_em(tabela, date(2026, 10, 7))["relatorio"].values
    )  # quarta
    assert (
        terca not in como_estava_em(tabela, date(2026, 10, 9))["relatorio"].values
    )  # sexta
    assert (
        terca not in como_estava_em(tabela, date(2026, 10, 12))["relatorio"].values
    )  # dia da divulgação
    assert (
        terca in como_estava_em(tabela, date(2026, 10, 13))["relatorio"].values
    )  # terça seguinte


def test_corte_em_d_nao_muda_o_passado():
    tabela = _agro()

    em_d = como_estava_em(tabela, date(2026, 10, 7))
    antes = tabela[tabela["relatorio"] <= pd.Timestamp("2026-09-29")]

    assert sorted(em_d["relatorio"].unique()) == sorted(antes["relatorio"].unique())
    assert len(em_d) == len(antes)
