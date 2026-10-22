"""As seções do PR 2 (qualidade do lucro; capital e acionistas) lidas pelo app: as tabelas saem escritas,
cada número com a data, a fonte e a comparação (o contrato de `src/numero.py`), na ordem do molde A.
"""

import json
from pathlib import Path

import pytest

from base import dossie as dossie_da_base
from src import dossie
from src import relatorio_empresa as re_
from tests.test_dossie_lucro_e_capital import (
    CNPJ,
    _capital,
    _como_era,
    _eventos_de_capital,
    _negociacoes,
    _painel,
    _qualidade,
    _releases,
    _trocas,
)

NOVAS = ("qualidade_do_lucro", "capital_e_acionistas")


@pytest.fixture(scope="module")
def secoes(tmp_path_factory: pytest.TempPathFactory) -> dict[str, re_.Secao]:
    bruta = dossie_da_base.montar_ficha(
        CNPJ,
        "CPFL Energia",
        [
            _qualidade(como_era=_como_era(), releases=_releases(), trocas=_trocas()),
            _capital(
                negociacoes=_negociacoes(),
                eventos=_eventos_de_capital(),
                painel=_painel(),
            ),
        ],
        "2026-10-17T07:00:00-03:00",
    )
    caminho: Path = tmp_path_factory.mktemp("ficha") / f"{CNPJ}.json"
    caminho.write_text(json.dumps(bruta), encoding="utf-8")
    ficha = dossie.ler_ficha(caminho)
    assert ficha is not None
    return {s.chave: s for s in dossie.secoes_da_ficha(dossie.cortar(ficha))}


def test_as_secoes_novas_chegam_ao_app_com_todas_as_tabelas(secoes) -> None:
    assert set(secoes) == set(NOVAS)
    assert set(secoes["qualidade_do_lucro"].tabelas) == {
        "reapresentacoes",
        "releases_diferentes",
        "releases_por_classe",
    }
    assert set(secoes["capital_e_acionistas"].tabelas) == {
        "insiders_por_cargo",
        "insiders_janelas",
        "eventos_de_capital",
        "fundos_janelas",
    }


def test_cada_tabela_nova_tem_titulo_proprio(secoes) -> None:
    for chave in NOVAS:
        for tabela in secoes[chave].tabelas:
            assert tabela in dossie.TITULOS_DAS_TABELAS, tabela


def test_todo_numero_novo_tem_data_fonte_e_comparacao(secoes) -> None:
    for chave in NOVAS:
        for item in secoes[chave].itens:
            assert item.numero.o_que_falta() == [], f"{chave}.{item.chave}"
            assert item.fonte in dossie.FONTES_DOS_ITENS.values(), item.chave


@pytest.mark.parametrize(
    ("secao", "item", "contra"),
    [
        ("qualidade_do_lucro", "exercicios_reapresentados", "de 2 exercícios"),
        ("qualidade_do_lucro", "releases_diferentes", "de 4 valores"),
        ("capital_e_acionistas", "insiders_vendas_12m", "R$ 4,0 mi"),
        ("capital_e_acionistas", "compras_dos_fundos_12m", "R$ 23,0 mi"),
    ],
)
def test_numeros_novos_comparam_com_o_que_a_ficha_traz(
    secoes, secao: str, item: str, contra: str
) -> None:
    do_item = next(i for i in secoes[secao].itens if i.chave == item)
    assert do_item.comparacao is not None, item
    assert contra in do_item.comparacao.texto


def test_reapresentacao_sai_escrita_em_reais_e_com_as_datas(secoes) -> None:
    [linha] = secoes["qualidade_do_lucro"].tabelas["reapresentacoes"]
    assert linha["Exercício"] == "2023"
    assert linha["Primeiro valor"] == "R$ 100,0 mi"
    assert linha["Refeito em"] == "12/03/2025"
    assert linha["Diferença"] == "-20,0%"


def test_secoes_novas_vem_na_ordem_do_molde_a() -> None:
    ordem = re_.ORDEM_DAS_SECOES
    assert (
        ordem.index("qualidade_do_lucro") == ordem.index("caixa") + 2
    )  # depois da geração de caixa
    assert (
        "qualidade" not in ordem
    )  # uma seção só: os selos moram na da qualidade do lucro
    assert ordem.index("capital_e_acionistas") == ordem.index("ofertas_e_fundos") + 1
