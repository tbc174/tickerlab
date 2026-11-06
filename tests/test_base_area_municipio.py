"""Área e produção de café por município: PAM e MapBiomas lado a lado (plano do café, PR 8, 8.4).

Os dublês são recortes reais de 5 municípios: a resposta do SIDRA (tabela 1613, área colhida e
quantidade produzida, arábica e canephora, 2025) e as linhas da planilha de cobertura da Coleção 11
do MapBiomas (classes Café, Floresta e Pastagem) para os mesmos códigos.
"""

import copy
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from base.commodities.area_municipio import (
    COLUNAS,
    COLUNAS_DA_PAM,
    COLUNAS_DO_MAPBIOMAS,
    juntar,
    ler_mapbiomas,
    ler_pam,
)

PASTA = Path(__file__).resolve().parent.parent / "dados_de_exemplo" / "commodities"
PAM = PASTA / "pam_cafe_area_e_producao_5_municipios.json"
MAPBIOMAS = PASTA / "mapbiomas_cafe_5_municipios.xlsx"
ANOS_DO_MAPBIOMAS = 2025 - 1985 + 1
PATOS_DE_MINAS, CACOAL, LINHARES, JUIZ_DE_FORA = (
    "3148004",
    "1100049",
    "3203205",
    "3136702",
)


def _resposta_do_sidra() -> list[dict[str, str]]:
    return json.loads(PAM.read_text(encoding="utf-8"))


def test_area_por_municipio_pam_e_mapbiomas_lado_a_lado():
    pam = ler_pam(_resposta_do_sidra())
    assert list(pam.columns) == list(COLUNAS_DA_PAM) and len(pam) == 5
    por_codigo = pam.set_index("codigo")
    patos = por_codigo.loc[PATOS_DE_MINAS]
    assert (patos["nome"], patos["uf"], patos["ano"]) == ("Patos de Minas", "MG", 2025)
    assert (patos["area_arabica_ha"], patos["producao_arabica_t"]) == (9175.0, 15253.0)
    linhares = por_codigo.loc[LINHARES]
    assert (linhares["area_conilon_ha"], linhares["area_total_ha"]) == (
        18400.0,
        18400.0,
    )
    assert (linhares["producao_conilon_t"], linhares["producao_total_t"]) == (
        63720.0,
        63720.0,
    )

    mapbiomas = ler_mapbiomas(MAPBIOMAS)
    assert list(mapbiomas.columns) == list(COLUNAS_DO_MAPBIOMAS)
    assert (mapbiomas["ano"].min(), mapbiomas["ano"].max()) == (1985, 2025)
    assert (
        len(mapbiomas) == 4 * ANOS_DO_MAPBIOMAS
    )  # Cacoal não tem linha da classe Café
    de_2025 = mapbiomas[mapbiomas["ano"] == 2025].set_index("codigo")[
        "area_mapbiomas_ha"
    ]
    assert de_2025[PATOS_DE_MINAS] == pytest.approx(
        7838.29, abs=0.01
    )  # soma dos dois biomas
    assert de_2025[LINHARES] == pytest.approx(5978.41, abs=0.01)
    assert CACOAL not in de_2025.index

    juntos = juntar(pam, mapbiomas)
    assert list(juntos.columns) == list(COLUNAS)
    assert len(juntos) == 4 * ANOS_DO_MAPBIOMAS + 1  # união: Cacoal só pela PAM
    ano = juntos[juntos["ano"] == 2025].set_index("codigo")
    assert ano.loc[PATOS_DE_MINAS, "area_total_ha"] == 9175.0
    assert ano.loc[PATOS_DE_MINAS, "area_mapbiomas_ha"] == pytest.approx(
        7838.29, abs=0.01
    )
    assert (
        pd.isna(ano.loc[CACOAL, "area_mapbiomas_ha"])
        and ano.loc[CACOAL, "area_total_ha"] == 4990.0
    )
    antigo = juntos.set_index(["codigo", "ano"]).loc[(PATOS_DE_MINAS, 1985)]
    assert (
        pd.isna(antigo["area_total_ha"]) and antigo["area_mapbiomas_ha"] > 0
    )  # PAM só de 2025
    assert ano.loc[PATOS_DE_MINAS, "referencia"] == pd.Timestamp("2025-12-31")
    assert ano.loc[PATOS_DE_MINAS, "disponivel_em"] == pd.Timestamp("2026-10-31")


def test_total_da_pam_so_quando_os_dois_tipos_tem_numero():
    """ "X" (sigilo) ou ".." (não se aplica) num tipo deixa o total vazio: não vale um total só de
    um tipo; "-" é zero de verdade no SIDRA."""
    linhas = copy.deepcopy(_resposta_do_sidra())
    for linha in linhas[1:]:
        if (
            linha["D1C"] == PATOS_DE_MINAS
            and linha["D2C"] == "216"
            and linha["D4C"] == "31620"
        ):
            linha["V"] = "X"
    patos = ler_pam(linhas).set_index("codigo").loc[PATOS_DE_MINAS]
    assert patos["area_arabica_ha"] == 9175.0
    assert pd.isna(patos["area_conilon_ha"]) and pd.isna(patos["area_total_ha"])
    assert patos["producao_total_t"] == 15253.0  # a produção não foi tocada


def test_mapbiomas_le_a_planilha_dentro_do_zip_e_so_a_classe_pedida(tmp_path):
    zipado = tmp_path / "MAPBIOMAS_BRAZIL-COL.11.zip"
    with zipfile.ZipFile(zipado, "w") as pacote:
        pacote.write(MAPBIOMAS, "MAPBIOMAS_BRAZIL-COL.11-BIOME_STATE_MUNICIPALITY.xlsx")
    do_zip = ler_mapbiomas(zipado)
    pd.testing.assert_frame_equal(do_zip, ler_mapbiomas(MAPBIOMAS))
    pd.testing.assert_frame_equal(do_zip, ler_mapbiomas(zipado.read_bytes()))
    floresta = ler_mapbiomas(MAPBIOMAS, classe=3)
    assert CACOAL in set(floresta["codigo"])
    assert floresta[floresta["ano"] == 2025].set_index("codigo")["area_mapbiomas_ha"][
        CACOAL
    ] == pytest.approx(135198.23, abs=0.01)


def test_sem_linhas_nao_vira_zero():
    vazia = ler_pam(_resposta_do_sidra()[:1])  # só o cabeçalho do SIDRA
    assert list(vazia.columns) == list(COLUNAS_DA_PAM) and vazia.empty
    juntos = juntar(vazia, ler_mapbiomas(MAPBIOMAS))
    assert len(juntos) == 4 * ANOS_DO_MAPBIOMAS
    assert juntos["area_total_ha"].isna().all() and juntos["nome"].isna().all()
