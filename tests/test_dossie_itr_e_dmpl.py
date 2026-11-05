"""Linha 664 (c): a revisão do auditor sobre o ITR e o patrimônio por componente (DMPL) na ficha.

Sem olhar o futuro: só vale o que já era público no dia; cortar o futuro não muda o passado.
"""

from datetime import date

import pandas as pd
import pytest

from base import dossie
from base.dicionario import TABELAS
from src.banco.coletas import LICENCAS

D = pd.Timestamp
HOJE = D("2026-11-05")


def _itr(
    referencia: str, entregue: str, *, versao: int = 1, opiniao: str = "sem_ressalva"
) -> dict:
    return {
        "cnpj": "00.000.000/0001-91",
        "referencia": date.fromisoformat(referencia),
        "versao": versao,
        "disponivel_em": date.fromisoformat(entregue),
        "opiniao": opiniao,
        "enfase": "nao",
        "continuidade_operacional": "nao_classificado",
    }


def _pareceres_do_itr() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _itr("2026-03-31", "2026-05-14"),
            _itr("2026-06-30", "2026-08-13", opiniao="com_ressalva"),
            _itr("2026-09-30", "2026-11-12"),  # ainda não era público em HOJE
        ]
    )


def test_a_revisao_do_itr_usa_o_trimestre_mais_novo_ja_entregue() -> None:
    itens, tabela = dossie.parecer_do_auditor(
        _pareceres_do_itr(),
        HOJE,
        "pareceres_itr",
        dossie.CAMPOS_DO_PARECER_DO_ITR,
        dossie.TRIMESTRES_DO_PARECER,
    )
    valores = {i["chave"]: i["valor"] for i in itens}
    assert valores == {
        "parecer_itr_opiniao": "com_ressalva",
        "parecer_itr_enfase": "nao",
    }
    assert {i["base"] for i in itens} == {
        "2026-06-30"
    }  # o não classificado não vira item
    assert {i["rastro"]["publicado_em"] for i in itens} == {"2026-08-13"}
    assert len(tabela) == 2


def test_toda_chave_do_itr_tem_origem_em_pareceres_itr() -> None:
    for chave, *_ in dossie.CAMPOS_DO_PARECER_DO_ITR:
        origem = dossie.ORIGEM_DOS_ITENS[chave]
        assert origem.tabela == "pareceres_itr"
        assert TABELAS[origem.tabela].familia_da_fonte in LICENCAS


def _celula(
    coluna,
    valor,
    referencia,
    divulgado,
    *,
    versao=1,
    grupo="con",
    ate=None,
    conta="5.07",
):
    return {
        "cnpj": "00.000.000/0001-91", "grupo": grupo, "conta": conta, "coluna": coluna,
        "valor": valor, "documento": "DFP", "referencia": D(referencia), "versao": versao,
        "ordem": "ultimo", "divulgado_em": D(divulgado), "ate": ate,
    }  # fmt: skip


def _dmpl() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _celula("capital_social", 100.0, "2024-12-31", "2025-03-01"),
            _celula("reservas_de_lucro", 40.0, "2024-12-31", "2025-03-01"),
            # a versão 2 do exercício tomou o lugar da 1, mas só vale a partir de 2025-09-01
            _celula(
                "capital_social", 90.0, "2025-12-31", "2026-03-01", ate=D("2026-09-01")
            ),
            _celula("capital_social", 95.0, "2025-12-31", "2026-09-01", versao=2),
            _celula(
                "sem_coluna", 5.0, "2025-12-31", "2026-03-01"
            ),  # nome que a base não soube dar
            _celula("capital_social", 7.0, "2025-12-31", "2026-03-01", grupo="ind"),
            _celula("capital_social", 1.0, "2025-12-31", "2026-03-01", conta="5.01"),
        ]
    )


def test_a_dmpl_mostra_o_saldo_final_como_era_no_dia() -> None:
    tabela = dossie._dmpl_por_exercicio(_dmpl(), HOJE)
    do_ano = tabela[tabela["referencia"] == D("2025-12-31")]
    assert list(do_ano["componente"]) == ["Capital social"]
    assert list(do_ano["valor"]) == [
        95.0
    ]  # consolidado, versão 2, sem a coluna sem nome
    assert set(do_ano["demonstracao"]) == {"Consolidada"}
    antes = dossie._dmpl_por_exercicio(_dmpl(), D("2026-06-01"))
    assert list(antes[antes["referencia"] == D("2025-12-31")]["valor"]) == [90.0]


def test_a_dmpl_cortar_o_futuro_nao_muda_o_passado() -> None:
    dia = D("2026-06-01")
    cortada = _dmpl()[lambda t: t["divulgado_em"] <= dia]
    # a linha trocada (`ate` no futuro) ainda valia no dia; cortar não pode mudar o que ela mostrava
    pd.testing.assert_frame_equal(
        dossie._dmpl_por_exercicio(cortada, dia),
        dossie._dmpl_por_exercicio(_dmpl(), dia),
    )


def test_a_dmpl_vazia_nao_quebra() -> None:
    assert dossie._dmpl_por_exercicio(pd.DataFrame(), HOJE).empty


@pytest.mark.parametrize("tabela", ["pareceres_itr", "dmpl_como_era"])
def test_as_tabelas_podem_ser_mostradas(tabela: str) -> None:
    assert dossie.pode_mostrar(tabela)


def test_a_secao_de_capital_traz_a_dmpl() -> None:
    secao = dossie.secao_capital_e_acionistas(
        pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), HOJE, dmpl=_dmpl()
    )
    assert secao is not None
    assert {
        linha["componente"] for linha in secao["tabelas"]["dmpl_por_exercicio"]
    } >= {"Capital social"}
