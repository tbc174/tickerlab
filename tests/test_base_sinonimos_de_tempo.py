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
        mapa = sinonimos_de_tempo(tabela, nome)
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
    for nome, tabela in TABELAS.items():
        mapa = sinonimos_de_tempo(tabela, nome)
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
    for nome, tabela in TABELAS.items():
        for coluna, canonico in sinonimos_de_tempo(tabela, nome).items():
            if coluna in esperado:
                achados[coluna] = canonico
                assert canonico == esperado[coluna], coluna
    assert achados.keys() == esperado.keys()


def test_as_colunas_a_conferir_sao_so_as_listadas():
    """Coluna nova de sentido incerto não entra calada: ou ganha nome canônico ou entra na lista."""
    achadas = {
        coluna
        for nome, tabela in TABELAS.items()
        for coluna, canonico in sinonimos_de_tempo(tabela, nome).items()
        if canonico == A_CONFERIR
    }
    assert achadas == COLUNAS_A_CONFERIR


def test_nenhuma_coluna_foi_renomeada_e_o_contrato_traz_o_mapa():
    for nome, tabela in TABELAS.items():
        assert contrato.contrato_da_tabela(nome, tabela)["sinonimos_de_tempo"] == (
            sinonimos_de_tempo(tabela, nome)
        )


def test_o_catalogo_publicado_traz_o_mapa_de_toda_tabela_com_coluna_temporal():
    publicado = json.loads(CATALOGO.read_text(encoding="utf-8"))["tabelas"]
    for nome, coluna in _temporais():
        assert publicado[nome]["sinonimos_de_tempo"][coluna], f"{nome}.{coluna}"


# Linha 440: o sentido das 19 colunas que a linha 160 deixou `a_conferir`. Só o mapa de nomes: o corte
# do "sem olhar o futuro" é o `datas` da tabela e não muda aqui.
CONFERIDAS_NA_LINHA_440 = {
    "montado_em": "coletado_em",
    "calculado_em": "coletado_em",
    "fechado_em": "ate_publico_em",
    "gerado_em": "aconteceu_em",
    "atualizado_em": "aconteceu_em",
    "data": "aconteceu_em",
    "data_de_corte": "referencia",
    "data_da_previsao": "referencia",
    "prazo": "aconteceu_em",
    "primeira": "referencia",
    "ultima": "referencia",
    "primeiro_no_cda": "referencia",
    "ultimo_no_cda": "referencia",
    "ultimo_visto": "publico_em",
    "mes": "referencia",
    "base_de": "visto_em",
    "porte_publico_em": "coletado_em",
    "confidencial_ate": "ate",
    "data_vencimento": "ate",
}  # fmt: skip
EXCECOES_POR_TABELA = {
    ("amostra_painel", "data"): "referencia",
    ("cnpj_estabelecimentos_mudancas", "mes"): "visto_em",
    ("cnpj_qsa_mudancas", "mes"): "visto_em",
    ("cnpj_simples_mudancas", "mes"): "visto_em",
}
AINDA_A_CONFERIR = {
    "classificado_em", "criado_em", "data_edital", "data_homologacao", "informado_em",
}  # fmt: skip


def test_as_19_colunas_da_linha_440_tem_nome_canonico():
    achadas = set()
    for nome, tabela in TABELAS.items():
        for coluna, canonico in sinonimos_de_tempo(tabela, nome).items():
            if coluna in CONFERIDAS_NA_LINHA_440:
                achadas.add(coluna)
                esperado = EXCECOES_POR_TABELA.get(
                    (nome, coluna), CONFERIDAS_NA_LINHA_440[coluna]
                )
                assert canonico == esperado, f"{nome}.{coluna}"
    assert achadas == set(CONFERIDAS_NA_LINHA_440)


def test_so_cinco_colunas_seguem_a_conferir_e_sao_de_outras_linhas():
    assert COLUNAS_A_CONFERIR == AINDA_A_CONFERIR


def test_excecao_por_tabela_so_vale_para_a_tabela_dela():
    mes = {
        nome: mapa["mes"]
        for nome, t in TABELAS.items()
        if "mes" in (mapa := sinonimos_de_tempo(t, nome))
    }
    assert mes["aneel_cde"] == "referencia"
    assert mes["cnpj_simples_mudancas"] == "visto_em"


def test_o_mapa_de_nomes_nao_muda_o_corte_das_tabelas():
    """O `datas` (de onde sai o `publico_em` da consulta) é o que o dicionário diz, intocado pelo mapa."""
    cnpj = TABELAS["cnpj_simples_mudancas"]
    assert dict(cnpj.datas) == {"publico_em": "mes"}
    assert cnpj.granularidade_do_publico_em == "mes"
    assert dict(TABELAS["ma_regua"].datas)["publico_em"] == "conhecido_em_do_negocio"
