"""Mapa de sinônimos de tempo no contrato (ADR 0108, D6, item 4; linha 160 da fila)."""

import json

from base import contrato
from base.dicionario import TABELAS
from base.tempo import (
    A_CONFERIR,
    CANONICOS,
    COLUNAS_A_CONFERIR,
    coluna_e_temporal,
    sinonimos_de_tempo,
)

CATALOGO = contrato.PASTA / "catalogo.json"


def _temporais():
    return [
        (nome, coluna)
        for nome, t in TABELAS.items()
        for coluna in t.colunas
        if coluna_e_temporal(t, coluna)
    ]


def test_toda_coluna_temporal_aponta_para_um_nome_canonico_ou_a_conferir():
    for nome, tabela in TABELAS.items():
        mapa = sinonimos_de_tempo(tabela)
        for coluna in tabela.colunas:
            if coluna_e_temporal(tabela, coluna):
                assert mapa.get(coluna) in CANONICOS | {A_CONFERIR}, f"{nome}.{coluna}"
        assert set(mapa) <= set(tabela.colunas), nome


def test_os_nomes_canonicos_sao_os_da_d6():
    assert {
        "aconteceu_em", "ate", "referencia", "publico_em", "ate_publico_em",
        "visto_em", "coletado_em",
    } == CANONICOS  # fmt: skip


def test_o_nome_canonico_e_mapeado_para_ele_mesmo():
    for tabela in TABELAS.values():
        mapa = sinonimos_de_tempo(tabela)
        for coluna in tabela.colunas:
            if coluna in CANONICOS:
                assert mapa[coluna] == coluna


def test_os_sinonimos_citados_na_d6_apontam_para_o_nome_da_d6():
    esperado = {
        "valido_desde": "aconteceu_em", "efetiva_em": "aconteceu_em", "desde": "aconteceu_em",
        "valido_ate": "ate",
        "disponivel_em": "publico_em", "divulgado_em": "publico_em",
        "conhecido_em": "publico_em", "publicado_em": "publico_em",
        "origem_coletada_em": "coletado_em",
    }  # fmt: skip
    achados = {}
    for tabela in TABELAS.values():
        for coluna, canonico in sinonimos_de_tempo(tabela).items():
            if coluna in esperado:
                achados[coluna] = canonico
                assert canonico == esperado[coluna], coluna
    assert achados.keys() == esperado.keys()


def test_as_colunas_a_conferir_sao_so_as_listadas():
    """Coluna nova de sentido incerto não entra calada: ou ganha nome canônico ou entra na lista."""
    achadas = {
        coluna
        for tabela in TABELAS.values()
        for coluna, canonico in sinonimos_de_tempo(tabela).items()
        if canonico == A_CONFERIR
    }
    assert achadas == COLUNAS_A_CONFERIR


def test_nenhuma_coluna_foi_renomeada_e_o_contrato_traz_o_mapa():
    for nome, tabela in TABELAS.items():
        assert contrato.contrato_da_tabela(nome, tabela)["sinonimos_de_tempo"] == (
            sinonimos_de_tempo(tabela)
        )


def test_o_catalogo_publicado_traz_o_mapa_de_toda_tabela_com_coluna_temporal():
    publicado = json.loads(CATALOGO.read_text(encoding="utf-8"))["tabelas"]
    for nome, coluna in _temporais():
        assert publicado[nome]["sinonimos_de_tempo"][coluna], f"{nome}.{coluna}"
