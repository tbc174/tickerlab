"""As seções do PR 3 (governança; crédito) lidas pelo app: as tabelas saem escritas, cada número com a
data, a fonte e a comparação (o contrato de `src/numero.py`), na ordem do molde A.
"""

import json
from pathlib import Path

import pytest

from base import dossie as dossie_da_base
from src import dossie
from src import relatorio_empresa as re_
from tests.test_dossie_governanca_e_credito import (
    CNPJ,
    _credito_completo,
    _governanca_completa,
)

NOVAS = ("governanca", "credito")


@pytest.fixture(scope="module")
def ficha(tmp_path_factory: pytest.TempPathFactory) -> dossie.Ficha:
    bruta = dossie_da_base.montar_ficha(
        CNPJ,
        "CPFL Energia",
        [_governanca_completa(), _credito_completo()],
        "2026-10-17T07:00:00-03:00",
    )
    caminho: Path = tmp_path_factory.mktemp("ficha") / f"{CNPJ}.json"
    caminho.write_text(json.dumps(bruta), encoding="utf-8")
    lida = dossie.ler_ficha(caminho)
    assert lida is not None
    return dossie.cortar(lida)


@pytest.fixture(scope="module")
def secoes(ficha: dossie.Ficha) -> dict[str, re_.Secao]:
    return {s.chave: s for s in dossie.secoes_da_ficha(ficha)}


def test_as_secoes_novas_chegam_ao_app_com_todas_as_tabelas(secoes) -> None:
    assert set(secoes) == set(NOVAS)
    assert set(secoes["governanca"].tabelas) == {
        "governanca_por_ano",
        "comites",
        "remuneracao_por_exercicio",
        "remuneracao_por_orgao",
        "remuneracao_da_diretoria_por_exercicio",
    }
    assert set(secoes["credito"].tabelas) == {
        "ratings",
        "ratings_janelas",
        "acoes_de_rating",
        "assembleias_janelas",
        "assembleias_por_tema",
        "assembleias_recentes",
        "assembleias_de_aperto",
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
        ("governanca", "conselho_membros", "8 no FRE de 2025"),
        ("governanca", "conselho_independentes", "2 no FRE de 2025"),
        ("governanca", "comites", "1 no FRE de 2025"),
        ("governanca", "mulheres_no_conselho", "2 no FRE de 2025"),
        ("governanca", "remuneracao_da_administracao", "R$ 45,0 mi em 2024"),
        ("credito", "ratings_rebaixamentos_12m", "0 nos 12 meses até 17/10/2025"),
        (
            "credito",
            "assembleias_de_debenturistas_12m",
            "1 nos 12 meses até 17/10/2025",
        ),
    ],
)
def test_numeros_novos_comparam_com_o_que_a_ficha_traz(
    secoes, secao: str, item: str, contra: str
) -> None:
    do_item = next(i for i in secoes[secao].itens if i.chave == item)
    assert do_item.comparacao is not None, item
    assert contra in do_item.comparacao.texto


def test_ratings_saem_com_a_agencia_a_acao_e_o_link(secoes, ficha) -> None:
    linhas = secoes["credito"].tabelas["ratings"]
    assert [
        (r["Agência"], r["Nota"], r["Ação"], r["Publicado em"]) for r in linhas
    ] == [
        ("Moody's", "Ba2", "Retirada", "11/05/2026"),
        ("Fitch", "AA-(bra)", "Rebaixamento", "03/03/2026"),
        ("S&P", "brAAA", "Afirmação", "02/06/2025"),
    ]
    assert linhas[1]["Perspectiva"] == "Negativa"
    assert dossie.links_da_tabela(ficha, "credito", "ratings")[1] == "https://cvm/p2"


def test_remuneracao_por_orgao_sai_em_reais(secoes) -> None:
    linhas = {
        r["Órgão"]: r for r in secoes["governanca"].tabelas["remuneracao_por_orgao"]
    }
    assert linhas["Diretoria Estatutária"]["Total"] == "R$ 40,0 mi"
    assert linhas["Diretoria Estatutária"]["Maior individual"] == "R$ 12,0 mi"
    assert linhas["Conselho Fiscal"]["Maior individual"] == "—"


def test_secoes_novas_vem_na_ordem_do_molde_a() -> None:
    ordem = re_.ORDEM_DAS_SECOES
    assert ordem.index("credito") == ordem.index("endividamento") + 1
    assert ordem.index("governanca") == ordem.index("auditor_e_controladas") + 1
    assert len(ordem) == len(set(ordem))
