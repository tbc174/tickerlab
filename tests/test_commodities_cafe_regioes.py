"""Regiões produtoras de café por município (plano do café, PR 8, tarefa 8.1).

O dublê `dados_de_exemplo/commodities/pam_cafe_area_5_municipios.json` é a resposta real do SIDRA
(tabela 1613, área colhida, PAM 2025) recortada para cinco municípios: Patos de Minas (arábica, Cerrado
Mineiro), Franca (Mogiana), Linhares (conilon, norte do ES), Cacoal (conilon, Rondônia) e Juiz de Fora
(3 ha: abaixo do mínimo, fica fora de qualquer região).
"""

import json
from pathlib import Path

import pytest

from src.commodities.cafe import regioes
from src.commodities.cafe.regioes import (
    ARABICA,
    AREA_MINIMA_HA,
    CONILON,
    DEFINICOES,
    REGIOES,
    Municipio,
    regiao_do_municipio,
)
from src.ibge_sidra import PAM_CAFE_ARABICA, ler_resposta

DUBLE_DA_PAM = (
    Path(__file__).resolve().parent.parent
    / "dados_de_exemplo"
    / "commodities"
    / "pam_cafe_area_5_municipios.json"
)
IDS_DO_PLANO = (
    "sul-de-minas", "cerrado-mineiro", "matas-de-minas", "chapada-de-minas", "mogiana",
    "alta-paulista", "norte-do-parana", "oeste-da-bahia", "planalto-da-bahia", "es-montanhas",
    "es-norte", "rondonia", "bahia-atlantico",
)  # fmt: skip
REGIOES_DE_CONILON = {"es-norte", "rondonia", "bahia-atlantico"}
# a PAM 2024 deu 1,9 milhão de hectares de café colhidos no Brasil; as regiões têm de cobrir quase tudo
AREA_NACIONAL_APROXIMADA_HA = 1_900_000
COBERTURA_MINIMA = 0.9


def _area_por_municipio() -> dict[str, dict[str, float]]:
    """{código: {"arabica": ha, "conilon": ha}} a partir do dublê, como o script lê o SIDRA."""
    areas: dict[str, dict[str, float]] = {}
    for valor in ler_resposta(json.loads(DUBLE_DA_PAM.read_text(encoding="utf-8"))):
        tipo = ARABICA if valor.categorias == (PAM_CAFE_ARABICA,) else CONILON
        areas.setdefault(valor.local, {ARABICA: 0.0, CONILON: 0.0})[tipo] = (
            valor.valor or 0.0
        )
    return areas


def test_regioes_cobrem_os_municipios_com_cafe_no_pam():
    esperado = {
        "3148004": ("cerrado-mineiro", ARABICA),  # Patos de Minas
        "3516200": ("mogiana", ARABICA),  # Franca
        "3203205": ("es-norte", CONILON),  # Linhares
        "1100049": ("rondonia", CONILON),  # Cacoal
    }
    for codigo, area in _area_por_municipio().items():
        regiao = regiao_do_municipio(codigo)
        if area[ARABICA] + area[CONILON] < AREA_MINIMA_HA:
            assert regiao is None, codigo  # Juiz de Fora: 3 ha
            continue
        assert regiao is not None, codigo
        assert (regiao.id, regiao.tipo_predominante) == esperado[codigo]
        municipio = next(m for m in regiao.municipios if m.codigo == codigo)
        assert (municipio.area_arabica_ha, municipio.area_conilon_ha) == (
            area[ARABICA],
            area[CONILON],
        )


def test_as_treze_regioes_do_plano_com_o_tipo_predominante():
    assert tuple(r.id for r in REGIOES) == IDS_DO_PLANO
    assert tuple(d.id for d in DEFINICOES) == IDS_DO_PLANO
    for regiao in REGIOES:
        assert regiao.municipios, regiao.id
        assert regiao.descricao and regiao.nome
        esperado = CONILON if regiao.id in REGIOES_DE_CONILON else ARABICA
        assert regiao.tipo_predominante == esperado, regiao.id


def test_cada_municipio_fica_numa_regiao_so_e_na_uf_dela():
    vistos: set[str] = set()
    for regiao in REGIOES:
        for municipio in regiao.municipios:
            assert municipio.codigo not in vistos, municipio
            vistos.add(municipio.codigo)
            assert len(municipio.codigo) == regioes.TAMANHO_DO_CODIGO
            assert municipio.uf in regiao.ufs
            assert municipio.area_ha >= AREA_MINIMA_HA, municipio
    assert regiao_do_municipio("3106200") is None  # Belo Horizonte: não planta café


def test_as_regioes_cobrem_quase_toda_a_area_de_cafe_do_pais():
    total = sum(regiao.area_ha for regiao in REGIOES)
    assert total >= COBERTURA_MINIMA * AREA_NACIONAL_APROXIMADA_HA
    assert total <= AREA_NACIONAL_APROXIMADA_HA * 1.1


@pytest.mark.parametrize("codigo", [3170701, "3170701", "317070", " 3170701 "])
def test_regiao_do_municipio_aceita_int_texto_e_seis_digitos(codigo):
    regiao = regiao_do_municipio(codigo)
    assert regiao is not None and regiao.id == "sul-de-minas"  # Varginha


def test_normalizar_codigo_calcula_o_digito_verificador():
    assert regioes.normalizar_codigo("355030") == "3550308"  # São Paulo
    assert regioes.normalizar_codigo(3106200) == "3106200"


def test_tipo_predominante_e_montar_regioes_com_dados_proprios():
    varginha = Municipio("3170701", "Varginha", "MG", 10_000.0, 0.0)
    linhares = Municipio("3203205", "Linhares", "ES", 100.0, 18_400.0)
    assert regioes.tipo_predominante([varginha, linhares]) == CONILON
    assert regioes.tipo_predominante([varginha]) == ARABICA
    assert regioes.tipo_predominante([]) == ARABICA

    montadas = regioes.montar_regioes(
        DEFINICOES[:1], {"sul-de-minas": [varginha], "ignorada": [linhares]}
    )
    assert len(montadas) == 1
    assert montadas[0].codigos == {"3170701"}
    assert montadas[0].area_ha == 10_000.0


def test_sem_o_csv_as_regioes_ficam_vazias(tmp_path):
    assert regioes.ler_municipios(tmp_path / "nao-existe.csv") == {}
