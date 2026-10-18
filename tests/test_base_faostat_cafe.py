"""Tabela `faostat_cafe` (PR 14): café verde por país e ano do FAOSTAT, sem olhar o futuro."""

import io
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from base.commodities import faostat_cafe

CSV = (
    Path(__file__).parent.parent
    / "dados_de_exemplo"
    / "commodities"
    / "faostat_cafe_pequeno.csv"
)


def _zip(csv: bytes) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        arquivo.writestr("Production_Crops_Livestock_E_All_Data_(Normalized).csv", csv)
    return saida.getvalue()


@pytest.fixture
def tabela() -> pd.DataFrame:
    return faostat_cafe.ler(_zip(CSV.read_bytes()), date(2026, 10, 19))


def test_so_cafe_verde_dos_paises_com_colunas_da_base(tabela):
    assert list(tabela.columns) == list(faostat_cafe.COLUNAS)
    assert set(tabela["codigo_do_pais"]) == {
        "076",
        "704",
        "360",
    }  # sem "World", sem milho
    assert set(tabela["elemento"]) == {"producao", "area_colhida", "rendimento"}
    assert set(tabela["tipo"]) == {"total"}


def test_valor_vazio_nao_vira_zero(tabela):
    indonesia_2022 = tabela[
        (tabela["codigo_do_pais"] == "360") & (tabela["ano"] == 2022)
    ]
    assert indonesia_2022.empty


def test_rendimento_em_hg_por_ha_vira_kg_por_ha(tabela):
    linha = tabela[
        (tabela["codigo_do_pais"] == "076")
        & (tabela["elemento"] == "rendimento")
        & (tabela["ano"] == 2023)
    ].iloc[0]
    assert linha["valor"] == pytest.approx(1841.1)
    assert linha["unidade"] == "kg/ha"
    assert linha["sinalizador"] == "C"


def test_unidade_desconhecida_interrompe_a_leitura():
    estranho = CSV.read_bytes().replace(b",t,3406000", b",kt,3406000")
    with pytest.raises(ValueError, match="unidade"):
        faostat_cafe.ler(_zip(estranho), date(2026, 10, 19))


def test_zip_sem_csv_interrompe_a_leitura():
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        arquivo.writestr("leia-me.txt", "nada")
    with pytest.raises(ValueError, match="CSV"):
        faostat_cafe.ler(saida.getvalue(), date(2026, 10, 19))


def test_corte_em_d_nao_usa_a_baixada_do_futuro(tabela):
    revista = faostat_cafe.ler(
        _zip(CSV.read_bytes().replace(b"3406000", b"3500000")), date(2026, 11, 20)
    )
    junta = pd.concat([tabela, revista], ignore_index=True)

    def producao_do_brasil(dia: date) -> float:
        corte = faostat_cafe.como_estava_em(junta, dia)
        linha = corte[
            (corte["codigo_do_pais"] == "076")
            & (corte["elemento"] == "producao")
            & (corte["ano"] == 2023)
        ]
        return float(linha["valor"].iloc[0])

    assert producao_do_brasil(date(2026, 10, 31)) == 3406000
    assert producao_do_brasil(date(2026, 11, 30)) == 3500000
    assert faostat_cafe.como_estava_em(junta, date(2026, 10, 1)).empty
