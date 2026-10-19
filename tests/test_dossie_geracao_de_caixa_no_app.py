"""A geração de caixa (série T1) lida pelo app: a tabela por exercício sai escrita, cada número com a data,
a fonte e a comparação com o exercício anterior (o contrato de `src/numero.py`), logo depois do caixa.
"""

import json
from pathlib import Path

import pytest

from base import dossie as dossie_da_base
from src import dossie
from src import relatorio_empresa as re_
from tests.test_dossie_geracao_de_caixa import HOJE, _como_era

CNPJ = "02429144000193"


@pytest.fixture(scope="module")
def secao(tmp_path_factory: pytest.TempPathFactory) -> re_.Secao:
    bruta = dossie_da_base.montar_ficha(
        CNPJ,
        "CPFL Energia",
        [dossie_da_base.secao_geracao_de_caixa(_como_era(), HOJE)],
        "2026-10-17T07:00:00-03:00",
    )
    caminho: Path = tmp_path_factory.mktemp("ficha") / f"{CNPJ}.json"
    caminho.write_text(json.dumps(bruta), encoding="utf-8")
    lida = dossie.ler_ficha(caminho)
    assert lida is not None
    (unica,) = dossie.secoes_da_ficha(dossie.cortar(lida))
    return unica


def test_tabela_por_exercicio_sai_escrita(secao: re_.Secao) -> None:
    assert "caixa_por_exercicio" in dossie.TITULOS_DAS_TABELAS
    ano_2025, ano_2024 = secao.tabelas["caixa_por_exercicio"]
    assert ano_2025["Exercício"] == "2025"
    assert ano_2025["EBITDA"] == "R$ 2,5 bi"
    assert ano_2025["Margem EBITDA"] == "25,0%"
    assert ano_2025["FCF"] == "R$ 1,3 bi"
    assert ano_2024["EBITDA"] == "R$ 2,0 bi"


def test_todo_numero_tem_data_fonte_e_comparacao(secao: re_.Secao) -> None:
    assert {item.chave for item in secao.itens} == {"ebitda", "capex", "fcf"}
    for item in secao.itens:
        assert item.numero.o_que_falta() == [], item.chave
        assert item.fonte in dossie.FONTES_DOS_ITENS.values(), item.chave


@pytest.mark.parametrize(
    ("item", "contra"),
    [
        ("ebitda", "R$ 2,0 bi em 2024"),
        ("capex", "R$ 700,0 mi em 2024"),
        ("fcf", "R$ 1,1 bi em 2024"),
    ],
)
def test_compara_com_o_exercicio_anterior(
    secao: re_.Secao, item: str, contra: str
) -> None:
    do_item = next(i for i in secao.itens if i.chave == item)
    assert do_item.comparacao is not None
    assert contra in do_item.comparacao.texto


def test_geracao_de_caixa_vem_logo_depois_do_caixa() -> None:
    ordem = re_.ORDEM_DAS_SECOES
    assert ordem.index("geracao_de_caixa") == ordem.index("caixa") + 1
    assert len(ordem) == len(set(ordem))
