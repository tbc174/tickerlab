"""Clima mensal por região cafeeira (plano do café, PR 8, tarefa 8.2): `base/commodities/clima_regiao.py`.

Dublês em `tests/arquivos/commodities/`:

- `inmet_3_estacoes_2024.zip`: três estações do Sul de Minas no formato novo do BDMEP, junho e julho
  de 2024, fabricadas e determinísticas: Tmín do dia = 10 + dia % 5, Tmáx = 22 + dia % 4, 2 mm de
  chuva nos dias 10, 20 e 30 de junho (6 mm no mês) e nada em julho. VARGINHA (A509) completa, com
  Tmín de -1 °C em 3 e 4 de julho; MACHADO (A531) sem 6 horas em 15/06 (o dia sai, o mês fica) e com
  -1 °C em 17/07; SAO SEBASTIAO DO PARAISO (A515) só até 10/07 (julho fica com 2 estações).
- `INMET_S_RS_A801_PORTO ALEGRE_dezembro-2000.CSV`: recorte real do formato antigo (Porto Alegre,
  dezembro de 2000), de uma estação fora de qualquer região cafeeira.
"""

import gzip
import io
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from base.commodities import clima_regiao as clima
from base.commodities.clima_regiao import (
    COLUNAS,
    FONTE_CHIRPS,
    FONTE_INMET,
    Grade,
    agregar,
    atribuir_regiao,
    chirps_por_regiao,
    com_normal,
    ler_chirps,
    ler_estacao,
    ler_inmet,
    mascara_do_municipio,
    mascaras_da_malha,
)
from src.commodities.cafe.regioes import ARABICA, CONILON, Municipio, Regiao

PASTA = Path(__file__).resolve().parent / "arquivos" / "commodities"
ZIP_DO_INMET = PASTA / "inmet_3_estacoes_2024.zip"
CSV_ANTIGO = PASTA / "INMET_S_RS_A801_PORTO ALEGRE_dezembro-2000.CSV"
MALHA_DO_ES = (
    Path(__file__).resolve().parent.parent
    / "dados_de_exemplo"
    / "commodities"
    / "malha_pequena.geojson"
)
JUNHO, JULHO = pd.Timestamp("2024-06-30"), pd.Timestamp("2024-07-31")
# médias do dublê: dia % 5 vale 0..4 seis vezes em 30 dias (média 2); dia % 4 soma 45 em 30 dias
TMIN_DE_JUNHO, TMAX_DE_JUNHO = 12.0, 22 + 45 / 30
TMIN_DE_MACHADO = (30 * 12.0 - 10.0) / 29  # sem o dia 15 (15 % 5 = 0 → Tmín 10)
TMAX_DE_MACHADO = 22 + (45 - 3) / 29  # 15 % 4 = 3


@pytest.fixture(scope="module")
def diario():
    return atribuir_regiao(ler_inmet(ZIP_DO_INMET.read_bytes()))


def _regiao(id_, municipios, tipo=ARABICA):
    return Regiao(id_, id_, ("MG",), tipo, tuple(municipios))


# --- INMET ----------------------------------------------------------------------------------------
def test_le_o_formato_antigo_do_inmet_e_a_estacao_fora_das_regioes_sai():
    porto_alegre = ler_estacao(CSV_ANTIGO.read_bytes())
    assert list(porto_alegre.columns) == list(clima.COLUNAS_DIARIAS)
    assert set(porto_alegre["estacao"]) == {"A801"}
    assert set(porto_alegre["uf"]) == {"RS"}
    assert porto_alegre["latitude"].iloc[0] == pytest.approx(-30.05, abs=0.01)
    assert len(porto_alegre) == 31  # dezembro
    assert (porto_alegre["horas_validas"] <= 24).all()
    assert (porto_alegre["tmax_c"] >= porto_alegre["tmin_c"]).all()
    assert atribuir_regiao(porto_alegre).empty


def test_le_o_zip_do_inmet_e_liga_a_estacao_a_regiao_pelo_nome_e_uf(diario):
    assert set(diario["regiao"]) == {"sul-de-minas"}
    assert set(diario["estacao"]) == {"A509", "A531", "A515"}
    varginha = diario[diario["estacao"] == "A509"].set_index("dia")
    assert len(varginha) == 30 + 31
    assert varginha.loc["2024-06-10", "chuva_mm"] == pytest.approx(2.0)
    assert varginha.loc["2024-07-03", "tmin_c"] == pytest.approx(-1.0)
    assert varginha.loc["2024-06-07", "tmax_c"] == pytest.approx(22 + 7 % 4)
    machado_15 = diario[(diario["estacao"] == "A531") & (diario["dia"] == "2024-06-15")]
    assert machado_15["horas_validas"].item() == 18  # perdeu 6 horas


def test_agregar_mes_por_regiao(diario):
    mensal = agregar(diario)
    assert list(mensal.columns) == list(COLUNAS)
    junho = mensal[mensal["competencia"] == JUNHO].iloc[0]
    assert (junho["regiao"], junho["fonte"], junho["n_estacoes"]) == (
        "sul-de-minas",
        FONTE_INMET,
        3,
    )
    assert junho["chuva_mm"] == pytest.approx(
        6.0
    )  # acumulada: 2 mm nos dias 10, 20 e 30
    assert junho["tmin_media_c"] == pytest.approx(
        (TMIN_DE_JUNHO + TMIN_DE_MACHADO + TMIN_DE_JUNHO) / 3
    )
    assert junho["tmax_media_c"] == pytest.approx(
        (TMAX_DE_JUNHO + TMAX_DE_MACHADO + TMAX_DE_JUNHO) / 3
    )
    assert junho["dias_tmin_abaixo_de_2c"] == 0
    assert junho["disponivel_em"] == JUNHO + pd.Timedelta(days=45)


def test_regiao_com_menos_de_3_estacoes_vira_none(diario):
    mensal = agregar(diario).set_index("competencia")
    julho = mensal.loc[JULHO]
    assert julho["n_estacoes"] == 2  # a A515 parou no dia 10
    for coluna in (
        "chuva_mm",
        "tmin_media_c",
        "dias_tmin_abaixo_de_2c",
        "tmax_media_c",
    ):
        assert pd.isna(julho[coluna]), coluna  # vazio, nunca zero


def _diario_sintetico(estacao: str, dias: int, mes: str = "2024-06") -> pd.DataFrame:
    datas = pd.date_range(f"{mes}-01", periods=dias, freq="D")
    return pd.DataFrame(
        {
            "estacao": estacao,
            "nome": "VARGINHA",
            "uf": "MG",
            "latitude": -21.5,
            "longitude": -45.4,
            "dia": datas,
            "chuva_mm": 1.0,
            "tmin_c": 1.0,  # todo dia abaixo de 2 °C
            "tmax_c": 20.0,
            "horas_validas": 24,
            "regiao": "sul-de-minas",
        }
    )


def test_estacao_com_menos_de_80_por_cento_dos_dias_sai():
    completa = _diario_sintetico("A1", 30)
    no_limite = _diario_sintetico("A2", 24)  # 24/30 = 80%: fica
    abaixo = _diario_sintetico("A3", 23)  # 23/30: sai
    outra = _diario_sintetico("A4", 30)
    mensal = agregar(pd.concat([completa, no_limite, abaixo, outra]))
    junho = mensal.iloc[0]
    assert junho["n_estacoes"] == 3
    assert junho["chuva_mm"] == pytest.approx((30 + 24 + 30) / 3)
    assert junho["dias_tmin_abaixo_de_2c"] == pytest.approx((30 + 24 + 30) / 3)
    # dia com poucas horas não conta como dia válido
    com_buraco = _diario_sintetico("A5", 30)
    com_buraco.loc[:6, "horas_validas"] = (
        19  # 7 dias com 19 horas → 23 dias válidos: sai
    )
    mensal = agregar(pd.concat([completa, outra, com_buraco]))
    assert mensal.iloc[0]["n_estacoes"] == 2


def test_agregar_ignora_regiao_desconhecida_e_diario_vazio():
    fora = _diario_sintetico("A1", 30).assign(regiao="lua")
    assert agregar(fora).empty
    assert list(
        agregar(pd.DataFrame(columns=list(clima.COLUNAS_DIARIAS))).columns
    ) == list(COLUNAS)


# --- normal e anomalia ----------------------------------------------------------------------------
def _mensal(
    regiao: str, anos: range, mes: int, chuva, fonte=FONTE_INMET
) -> pd.DataFrame:
    linhas = [
        {
            "regiao": regiao,
            "competencia": pd.Timestamp(ano, mes, 1) + pd.offsets.MonthEnd(0),
            "fonte": fonte,
            "chuva_mm": chuva(ano),
            "tmin_media_c": 10.0,
            "tmax_media_c": 25.0,
            "n_estacoes": 3,
        }
        for ano in anos
    ]
    return pd.DataFrame(linhas)


def test_normal_1991_2020_e_anomalia():
    # chuva de janeiro cresce 1 mm por ano: a normal 1991–2020 é a média (2005,5 → 115,5 mm)
    historia = _mensal(
        "sul-de-minas", range(1985, 2025), 1, lambda ano: 100.0 + (ano - 1991)
    )
    fevereiro = _mensal("sul-de-minas", range(2024, 2025), 2, lambda ano: 50.0)
    completa = com_normal(pd.concat([historia, fevereiro]))
    assert list(completa.columns) == list(COLUNAS)
    tabela = completa.set_index("competencia")
    janeiro_2024 = tabela.loc["2024-01-31"]
    assert janeiro_2024["chuva_normal_mm"] == pytest.approx(100 + (2005.5 - 1991))
    assert janeiro_2024["anos_na_normal"] == 30  # 1985–1990 e 2021–2024 ficam de fora
    assert janeiro_2024["chuva_anomalia_mm"] == pytest.approx(133.0 - 114.5)
    assert janeiro_2024["tmin_normal_c"] == pytest.approx(10.0)
    assert janeiro_2024["tmin_anomalia_c"] == pytest.approx(0.0)
    assert janeiro_2024["tmax_anomalia_c"] == pytest.approx(0.0)
    # o ano dentro do período também ganha a anomalia contra a mesma normal
    assert tabela.loc["1991-01-31", "chuva_anomalia_mm"] == pytest.approx(100 - 114.5)
    # fevereiro só tem um ano: sem normal, sem anomalia, e nunca zero
    fev = tabela.loc["2024-02-29"]
    assert pd.isna(fev["chuva_normal_mm"]) and pd.isna(fev["chuva_anomalia_mm"])
    assert pd.isna(fev["anos_na_normal"])


def test_normal_e_por_fonte_e_precisa_de_10_anos():
    inmet = _mensal("sul-de-minas", range(2000, 2021), 7, lambda ano: 10.0)
    chirps = _mensal(
        "sul-de-minas", range(1991, 2021), 7, lambda ano: 30.0, FONTE_CHIRPS
    )
    poucos = _mensal("es-norte", range(2012, 2021), 7, lambda ano: 99.0)  # 9 anos
    tabela = com_normal(pd.concat([inmet, chirps, poucos]))
    por_fonte = tabela.groupby(["regiao", "fonte"])["chuva_normal_mm"].first()
    assert por_fonte[("sul-de-minas", FONTE_INMET)] == pytest.approx(10.0)
    assert por_fonte[("sul-de-minas", FONTE_CHIRPS)] == pytest.approx(30.0)
    assert (
        tabela.groupby(["regiao", "fonte"])["anos_na_normal"].first()[
            ("sul-de-minas", FONTE_INMET)
        ]
        == 21
    )
    assert pd.isna(por_fonte[("es-norte", FONTE_INMET)])
    assert com_normal(pd.DataFrame(columns=list(COLUNAS))).empty


# --- CHIRPS ---------------------------------------------------------------------------------------
GRADE_PEQUENA = Grade(lon_oeste=-50.0, lat_norte=-20.0, passo=0.5, colunas=4, linhas=4)


def _quadrado(lon0, lat0, lon1, lat1):
    return {
        "type": "Polygon",
        "coordinates": [
            [[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]
        ],
    }


def _tif(matriz: np.ndarray) -> bytes:
    from PIL import Image

    saida = io.BytesIO()
    Image.fromarray(matriz.astype(np.float32), mode="F").save(saida, format="TIFF")
    return saida.getvalue()


def test_mascara_do_municipio_pega_os_pixels_com_centro_dentro():
    # os 2×2 pixels do canto noroeste: lon -50..-49, lat -21..-20
    mascara = mascara_do_municipio(_quadrado(-50.0, -21.0, -49.0, -20.0), GRADE_PEQUENA)
    assert sorted(zip(mascara.linhas, mascara.colunas, strict=True)) == [
        (0, 0), (0, 1), (1, 0), (1, 1),
    ]  # fmt: skip
    # com um buraco no pixel (0, 0)
    com_buraco = {
        "type": "Polygon",
        "coordinates": [
            _quadrado(-50.0, -21.0, -49.0, -20.0)["coordinates"][0],
            _quadrado(-49.9, -20.4, -49.6, -20.1)["coordinates"][0],
        ],
    }
    mascara = mascara_do_municipio(com_buraco, GRADE_PEQUENA)
    assert (0, 0) not in set(zip(mascara.linhas, mascara.colunas, strict=True))
    # município menor que um pixel: o pixel do centro da caixa dele
    pequeno = mascara_do_municipio(_quadrado(-48.4, -21.4, -48.3, -21.3), GRADE_PEQUENA)
    assert (pequeno.linhas.tolist(), pequeno.colunas.tolist()) == ([2], [3])
    # multipolígono soma as partes
    duas_partes = {
        "type": "MultiPolygon",
        "coordinates": [
            _quadrado(-50.0, -21.0, -49.5, -20.0)["coordinates"],
            _quadrado(-48.5, -22.0, -48.0, -21.5)["coordinates"],
        ],
    }
    mascara = mascara_do_municipio(duas_partes, GRADE_PEQUENA)
    assert len(mascara.linhas) == 3
    with pytest.raises(ValueError, match="Geometria"):
        mascara_do_municipio({"type": "Point", "coordinates": [0, 0]}, GRADE_PEQUENA)


def test_ler_chirps_tira_a_media_dos_pixels_e_ignora_o_sem_dado():
    matriz = np.arange(16, dtype=np.float32).reshape(4, 4)
    matriz[0, 0] = clima.SEM_DADO_DO_CHIRPS
    mascaras = {
        "1": mascara_do_municipio(_quadrado(-50.0, -21.0, -49.0, -20.0), GRADE_PEQUENA),
        "2": mascara_do_municipio(_quadrado(-49.0, -22.0, -48.0, -21.0), GRADE_PEQUENA),
    }
    chuva = ler_chirps(_tif(matriz), mascaras).set_index("codigo")["chuva_mm"]
    assert chuva["1"] == pytest.approx((1 + 4 + 5) / 3)  # o pixel (0, 0) era -9999
    assert chuva["2"] == pytest.approx((10 + 11 + 14 + 15) / 4)
    # o `.tif.gz` do portal abre do mesmo jeito
    comprimido = gzip.compress(_tif(matriz))
    assert ler_chirps(comprimido, mascaras)["chuva_mm"].tolist() == chuva.tolist()
    # município só com pixels sem dado fica vazio
    tudo_vazio = np.full((4, 4), clima.SEM_DADO_DO_CHIRPS, dtype=np.float32)
    assert ler_chirps(_tif(tudo_vazio), mascaras)["chuva_mm"].isna().all()


def test_chirps_por_regiao_pondera_pela_area_de_cafe():
    patrocinio = Municipio("3152501", "Patrocínio", "MG", 30_000.0, 0.0)
    monte_carmelo = Municipio("3143302", "Monte Carmelo", "MG", 10_000.0, 0.0)
    sem_area = Municipio("3100000", "Sem café", "MG", 0.0, 0.0)
    linhares = Municipio("3203205", "Linhares", "ES", 0.0, 18_400.0)
    regioes = (
        _regiao("cerrado-mineiro", [patrocinio, monte_carmelo, sem_area]),
        _regiao("es-norte", [linhares], CONILON),
    )
    por_municipio = pd.DataFrame(
        {"codigo": ["3152501", "3143302", "3100000"], "chuva_mm": [100.0, 60.0, 999.0]}
    )
    mensal = chirps_por_regiao(por_municipio, date(2024, 1, 15), regioes).set_index(
        "regiao"
    )
    assert list(mensal.reset_index().columns) == list(COLUNAS)
    cerrado = mensal.loc["cerrado-mineiro"]
    assert cerrado["chuva_mm"] == pytest.approx((100 * 30_000 + 60 * 10_000) / 40_000)
    assert cerrado["fonte"] == FONTE_CHIRPS
    assert cerrado["competencia"] == pd.Timestamp("2024-01-31")
    assert cerrado["disponivel_em"] == pd.Timestamp("2024-01-31") + pd.Timedelta(
        days=60
    )
    assert pd.isna(cerrado["tmin_media_c"]) and pd.isna(cerrado["n_estacoes"])
    assert pd.isna(mensal.loc["es-norte", "chuva_mm"])  # sem município com dado


def test_mascaras_da_malha_do_ibge_cobrem_os_municipios_pedidos():
    malha = json.loads(MALHA_DO_ES.read_text(encoding="utf-8"))
    todas = mascaras_da_malha(malha)
    assert len(todas) == len(malha["features"]) == 78  # o ES inteiro
    so_linhares = mascaras_da_malha(malha, codigos=["3203205", "0000000"])
    assert set(so_linhares) == {"3203205"}
    linhares = so_linhares["3203205"]
    assert len(linhares.linhas) > 50  # ~3.500 km² em pixels de ~30 km²
    lon, lat = clima.GRADE_CHIRPS.centro(linhares.linhas, linhares.colunas)
    assert -40.5 < lon.mean() < -39.5 and -19.6 < lat.mean() < -18.9
    assert all(
        len(m.linhas) >= 1 for m in todas.values()
    )  # nenhum município fica sem pixel


def test_grade_do_chirps_e_a_do_produto_global():
    grade = clima.GRADE_CHIRPS
    assert (grade.colunas, grade.linhas, grade.passo) == (7200, 2000, 0.05)
    assert grade.coluna(-180.0) == 0 and grade.coluna(179.99) == 7199
    assert grade.linha(50.0) == 0 and grade.linha(-49.99) == 1999
