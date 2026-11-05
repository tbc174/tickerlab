"""A DFC e a DVA inteiras no anexo de anos da ficha (linha 197 da fila).

A noite já lê da T1 as linhas da DFP (DFC e DVA, de todas as versões) para a geração de caixa; daqui
sai também uma tabela com cada conta de cada exercício, como era pública no dia da ficha. O app a
junta ao anexo de até 10 anos (contas nas linhas, anos nas colunas) e a tira da seção de caixa.
"""

import json
from pathlib import Path

import pandas as pd

from base import dossie as dossie_da_base
from src import dossie
from src import relatorio_empresa as re_
from tests.test_dossie_geracao_de_caixa import (
    CAIXA,
    COMPRA,
    DA,
    HOJE,
    MILHAO,
    _como_era,
    _linha,
)

NOVA_CONTA = ("DFC_MI", "6.01.01", "Lucro Líquido Ajustado")
OUTRO_CNPJ = "02429144000193"


def _tabela(como_era: pd.DataFrame | None = None) -> list[dict]:
    secao = dossie_da_base.secao_geracao_de_caixa(
        _como_era() if como_era is None else como_era, HOJE
    )
    assert secao is not None
    return secao["tabelas"]["dfc_dva_por_exercicio"]


def _valor(linhas: list[dict], conta: str, exercicio: int) -> float | None:
    (achada,) = [
        linha
        for linha in linhas
        if linha["conta"] == conta and linha["exercicio"] == exercicio
    ]
    return achada["valor"]


def test_a_tabela_traz_so_a_dfc_e_a_dva_com_o_nome_de_cada_conta() -> None:
    linhas = _tabela()
    assert {linha["demonstracao"] for linha in linhas} == {"DFC_MI", "DVA"}
    assert {linha["conta"] for linha in linhas} == {"6.01", "6.02.01", "7.04.01"}
    assert {linha["descricao"] for linha in linhas if linha["conta"] == "6.01"} == {
        CAIXA[2]
    }
    assert _valor(linhas, "6.01", 2025) == 2_200 * MILHAO
    assert (
        _valor(linhas, "7.04.01", 2024) == -400 * MILHAO
    )  # o sinal da DVA como a CVM publica


def test_vale_a_versao_publica_no_dia_e_a_reapresentacao_entra_a_partir_do_dia_dela() -> (
    None
):
    como_era = pd.concat(
        [
            _como_era(),
            pd.DataFrame(
                [
                    _linha(
                        2024, CAIXA, 1_900, "2026-03-20"
                    ),  # reapresenta 2024 antes da ficha
                    _linha(
                        2025, CAIXA, 9_999, "2027-03-19"
                    ),  # só depois da ficha: fora
                ]
            ),
        ]
    )
    linhas = _tabela(como_era)
    assert _valor(linhas, "6.01", 2024) == 1_900 * MILHAO
    assert _valor(linhas, "6.01", 2025) == 2_200 * MILHAO
    assert 2026 not in {linha["exercicio"] for linha in linhas}


def test_cortar_o_futuro_nao_muda_o_passado() -> None:
    como_era = _como_era()
    passado = como_era[como_era["divulgado_em"] <= HOJE]
    assert _tabela(passado) == _tabela(como_era)


def test_o_individual_so_entra_quando_nao_ha_consolidado() -> None:
    individual = pd.DataFrame([_linha(2025, NOVA_CONTA, 7, "2026-03-20", grupo="ind")])
    com_consolidado = _tabela(pd.concat([_como_era(), individual]))
    assert "6.01.01" not in {linha["conta"] for linha in com_consolidado}
    so_individual = _como_era().assign(grupo="ind")
    assert _tabela(
        pd.concat([so_individual, individual])
    )  # sem consolidado, vale o individual


def test_conta_em_branco_nao_vira_zero() -> None:
    em_branco = pd.DataFrame([_linha(2025, NOVA_CONTA, 0, "2026-03-20")]).assign(
        valor=float("nan")
    )
    linhas = _tabela(pd.concat([_como_era(), em_branco]))
    assert "6.01.01" not in {linha["conta"] for linha in linhas}


def test_so_os_ultimos_dez_exercicios() -> None:
    antigos = pd.DataFrame(
        [_linha(ano, NOVA_CONTA, 5, f"{ano + 1}-03-20") for ano in range(2005, 2026)]
    )
    exercicios = {
        linha["exercicio"] for linha in _tabela(pd.concat([_como_era(), antigos]))
    }
    assert exercicios == set(range(2016, 2026))


# --- o app: a tabela da noite vira linhas do anexo de anos ------------------------------------------


def _ficha_lida(tmp_path: Path) -> list[re_.Secao]:
    bruta = dossie_da_base.montar_ficha(
        OUTRO_CNPJ,
        "CPFL Energia",
        [dossie_da_base.secao_geracao_de_caixa(_como_era(), HOJE)],
        "2026-10-17T07:00:00-03:00",
    )
    caminho = tmp_path / f"{OUTRO_CNPJ}.json"
    caminho.write_text(json.dumps(bruta), encoding="utf-8")
    lida = dossie.ler_ficha(caminho)
    assert lida is not None
    return dossie.secoes_da_ficha(dossie.cortar(lida))


def test_as_linhas_do_anexo_trazem_a_conta_com_o_codigo_a_unidade_e_um_ano_por_coluna(
    tmp_path: Path,
) -> None:
    (secao,) = _ficha_lida(tmp_path)
    linhas = secao.tabelas[dossie.ANEXO_DFC_DVA]
    por_conta = {linha["conta"]: linha for linha in linhas}
    caixa = por_conta[f"DFC 6.01 · {CAIXA[2]}"]
    assert caixa["unidade"] == "R$"
    assert caixa["2024"] == 1_800 * MILHAO and caixa["2025"] == 2_200 * MILHAO
    assert f"DVA 7.04.01 · {DA[2]}" in por_conta
    assert f"DFC 6.02.01 · {COMPRA[2]}" in por_conta
    # a DFC antes da DVA, e cada demonstração na ordem do código
    codigos = [linha["conta"].split(" · ")[0] for linha in linhas]
    assert codigos == sorted(codigos, key=lambda c: (c.split()[0] != "DFC", c))


def test_a_tabela_longa_nao_vai_para_a_pagina(tmp_path: Path) -> None:
    (secao,) = _ficha_lida(tmp_path)
    assert "dfc_dva_por_exercicio" not in secao.tabelas


def _historico(anos: list[int]) -> re_.Secao:
    linhas = [{"conta": "Receita", "unidade": "R$", **{str(a): 1.0 for a in anos}}]
    return re_.Secao(
        "historico", "Histórico", tabelas={re_.ANEXO_DE_ANOS: linhas, "contas": []}
    )


def test_o_anexo_de_anos_ganha_as_linhas_da_dfc_e_da_dva_nos_mesmos_anos(
    tmp_path: Path,
) -> None:
    (caixa,) = _ficha_lida(tmp_path)
    secoes = re_.com_a_dfc_e_a_dva([_historico([2024, 2025]), caixa])
    anexo = next(s for s in secoes if s.chave == "historico").tabelas[re_.ANEXO_DE_ANOS]
    assert anexo[0]["conta"] == "Receita"
    assert any(linha["conta"].startswith("DFC 6.01") for linha in anexo)
    assert all(
        list(linha) == list(anexo[0]) for linha in anexo
    )  # o PDF lê as colunas da 1ª linha
    sem_tabela = next(s for s in secoes if s.chave == "geracao_de_caixa")
    assert dossie.ANEXO_DFC_DVA not in sem_tabela.tabelas


def test_ano_fora_dos_dez_do_anexo_nao_entra_e_ano_sem_a_conta_fica_vazio(
    tmp_path: Path,
) -> None:
    (caixa,) = _ficha_lida(tmp_path)
    secoes = re_.com_a_dfc_e_a_dva([_historico([2025, 2026]), caixa])
    anexo = next(s for s in secoes if s.chave == "historico").tabelas[re_.ANEXO_DE_ANOS]
    linha = next(x for x in anexo if x["conta"].startswith("DFC 6.01"))
    assert "2024" not in linha
    assert linha["2025"] == 2_200 * MILHAO and linha["2026"] is None


def test_sem_historico_ou_sem_a_tabela_nada_muda(tmp_path: Path) -> None:
    (caixa,) = _ficha_lida(tmp_path)
    so_a_dre = re_.Secao("geracao_de_caixa", "Geração de caixa")
    assert (
        re_.com_a_dfc_e_a_dva([_historico([2025]), so_a_dre])[0].tabelas[
            re_.ANEXO_DE_ANOS
        ]
        == _historico([2025]).tabelas[re_.ANEXO_DE_ANOS]
    )
    assert re_.com_a_dfc_e_a_dva([caixa])  # sem seção de histórico: segue como estava
