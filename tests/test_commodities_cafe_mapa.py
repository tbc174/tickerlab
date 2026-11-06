"""Os dados do mapa do café e a malha simplificada (plano do café, PR 8, 8.4)."""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from base.commodities.area_municipio import ler_mapbiomas, ler_pam
from src.commodities.cafe.mapa import (
    LIMITE_DA_MALHA_BYTES,
    PONTOS_MINIMOS_DO_ANEL,
    douglas_peucker,
    montar_dados_do_mapa,
    simplificar_malha,
    tamanho_em_bytes,
)
from src.commodities.cafe.regioes import REGIOES

PASTA = Path(__file__).resolve().parent.parent / "dados_de_exemplo" / "commodities"
MALHA = PASTA / "malha_pequena.geojson"  # 78 municípios do ES, qualidade mínima do IBGE
PATOS_DE_MINAS, CACOAL, LINHARES, JUIZ_DE_FORA, FRANCA = (
    "3148004",
    "1100049",
    "3203205",
    "3136702",
    "3516200",
)
LIMITE_APERTADO = 20_000


@pytest.fixture(scope="module")
def pam() -> pd.DataFrame:
    return ler_pam(
        json.loads(
            (PASTA / "pam_cafe_area_e_producao_5_municipios.json").read_text("utf-8")
        )
    )


@pytest.fixture(scope="module")
def area() -> pd.DataFrame:
    return ler_mapbiomas(PASTA / "mapbiomas_cafe_5_municipios.xlsx")


@pytest.fixture
def clima() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("cerrado-mineiro", pd.Timestamp("2025-09-30"), "chirps", -20.0),
            ("mogiana", pd.Timestamp("2025-09-30"), "chirps", 5.0),
            ("mogiana", pd.Timestamp("2025-08-31"), "chirps", 50.0),
            ("es-norte", pd.Timestamp("2025-09-30"), "inmet", 9.0),
        ],
        columns=["regiao", "competencia", "fonte", "chuva_anomalia_mm"],
    )


def test_montar_dados_do_mapa_junta_pam_mapbiomas_regiao_e_clima_em_tipos_simples(
    pam, area, clima
):
    dados = montar_dados_do_mapa(pam, area, clima)
    assert (dados.ano, dados.tipo, dados.competencia) == (2025, "total", "2025-09")
    por_codigo = {m.codigo: m for m in dados.municipios}
    assert list(por_codigo) == sorted(por_codigo) and len(por_codigo) == 5
    patos = por_codigo[PATOS_DE_MINAS]
    assert (patos.nome, patos.uf, patos.regiao) == (
        "Patos de Minas",
        "MG",
        "cerrado-mineiro",
    )
    assert (patos.producao_t, patos.area_pam_ha) == (15253.0, 9175.0)
    assert patos.area_mapbiomas_ha == pytest.approx(7838.29, abs=0.01)
    assert patos.anomalia_de_chuva_mm == -20.0
    cacoal = por_codigo[CACOAL]
    assert cacoal.regiao == "rondonia" and cacoal.area_mapbiomas_ha is None
    assert cacoal.anomalia_de_chuva_mm is None  # região sem clima no mês
    assert por_codigo[JUIZ_DE_FORA].regiao is None  # fora das regiões produtoras
    assert (
        por_codigo[LINHARES].anomalia_de_chuva_mm is None
    )  # só INMET: o mapa usa o CHIRPS
    # tudo tipo simples: vira JSON e volta igual
    de_volta = json.loads(json.dumps(dados.em_dicionario()))
    assert de_volta["municipios"][0] == {
        "codigo": CACOAL,
        "nome": "Cacoal",
        "uf": "RO",
        "regiao": "rondonia",
        "producao_t": 17066.0,
        "area_pam_ha": 4990.0,
        "area_mapbiomas_ha": None,
        "anomalia_de_chuva_mm": None,
    }


def test_mapa_por_tipo_mes_e_ano_e_sem_clima(pam, area, clima):
    conilon = montar_dados_do_mapa(
        pam, area, clima, tipo="conilon", competencia=date(2025, 8, 31)
    )
    assert conilon.competencia == "2025-08"
    producao = {m.codigo: m.producao_t for m in conilon.municipios}
    assert (producao[LINHARES], producao[PATOS_DE_MINAS]) == (63720.0, 0.0)
    anomalia = {m.codigo: m.anomalia_de_chuva_mm for m in conilon.municipios}
    assert anomalia[FRANCA] == 50.0 and anomalia[PATOS_DE_MINAS] is None
    with pytest.raises(ValueError, match="tipo"):
        montar_dados_do_mapa(pam, area, clima, tipo="robusta")
    sem_clima = montar_dados_do_mapa(pam, area, clima.iloc[:0])
    assert sem_clima.competencia is None
    assert all(m.anomalia_de_chuva_mm is None for m in sem_clima.municipios)
    # ano sem PAM: só o MapBiomas; nome e UF vêm do cadastro das regiões (ou ficam vazios)
    de_2024 = montar_dados_do_mapa(pam, area, clima, ano=2024)
    por_codigo = {m.codigo: m for m in de_2024.municipios}
    assert set(por_codigo) == {PATOS_DE_MINAS, LINHARES, JUIZ_DE_FORA, FRANCA}
    linhares = por_codigo[LINHARES]
    assert (linhares.nome, linhares.uf, linhares.producao_t) == ("Linhares", "ES", None)
    assert linhares.area_pam_ha is None and linhares.area_mapbiomas_ha > 0  # type: ignore[operator]
    assert (por_codigo[JUIZ_DE_FORA].nome, por_codigo[JUIZ_DE_FORA].uf) == ("", "")
    with pytest.raises(ValueError, match="sem dados"):
        montar_dados_do_mapa(pam.iloc[:0], area.iloc[:0], clima)


def test_malha_simplificada_so_municipios_com_cafe_e_menor_que_2mb():
    """Risco 6 do plano: a malha que vai ao navegador tem só os municípios com café e cabe em 2 MB;
    quando não cabe, os contornos são afinados (Douglas–Peucker) sem perder município."""
    malha = json.loads(MALHA.read_text(encoding="utf-8"))
    antes = json.dumps(malha)
    com_cafe = {m.codigo for r in REGIOES if "ES" in r.ufs for m in r.municipios}
    simples = simplificar_malha(malha, com_cafe)
    codigos = [f["properties"]["codarea"] for f in simples["features"]]
    assert len(codigos) == 75 < len(malha["features"]) and set(codigos) <= com_cafe
    assert tamanho_em_bytes(simples) <= LIMITE_DA_MALHA_BYTES
    assert simples["features"][0]["properties"] == {
        "codarea": codigos[0]
    }  # só o código
    apertada = simplificar_malha(malha, com_cafe, limite_bytes=LIMITE_APERTADO)
    assert tamanho_em_bytes(apertada) <= LIMITE_APERTADO < tamanho_em_bytes(simples)
    assert len(apertada["features"]) == 75
    for feicao in apertada["features"]:
        for anel in feicao["geometry"]["coordinates"]:
            assert anel[0] == anel[-1] and len(anel) >= PONTOS_MINIMOS_DO_ANEL
    assert json.dumps(malha) == antes  # a malha de entrada não muda
    with pytest.raises(ValueError, match="não cabe"):
        simplificar_malha(malha, com_cafe, limite_bytes=500)


def test_douglas_peucker_tira_so_o_que_fica_perto_da_reta():
    linha = [[0.0, 0.0], [1.0, 0.01], [2.0, 0.0], [3.0, 1.0], [4.0, 0.0]]
    assert douglas_peucker(linha, 0.1) == [
        [0.0, 0.0],
        [2.0, 0.0],
        [3.0, 1.0],
        [4.0, 0.0],
    ]
    assert douglas_peucker(linha, 0) == linha
    assert douglas_peucker(linha, 10) == [[0.0, 0.0], [4.0, 0.0]]
