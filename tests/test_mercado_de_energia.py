"""PLD, curtailment e capacidade das elétricas no relatório do setor (linha 664, item a).

Os três são de um mercado, não de uma companhia. Os testes montam as tabelas como a base as entrega
("como era no dia"), resumem com `base/mercado_de_energia.py`, gravam a noite e leem o relatório.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from base import dossie as dossie_da_base
from base import mercado_de_energia as mercado
from src import dossie
from src import relatorio_setor as rs
from tests.test_relatorio_setor import (
    CPFL,
    HOJE,
    OUTRA,
    _consumidores,
    _entradas,
    _ligacoes,
    gravar_noite,
)

D = pd.Timestamp
DIA = D("2026-10-20")


def _pld() -> pd.DataFrame:
    meses = ["2026-07-01", "2026-08-01", "2026-09-01", "2026-10-01"]
    linhas = [
        {
            "granularidade": "mes",
            "submercado": sub,
            "referencia": D(mes),
            "pld": preco,
            "disponivel_em": D(mes) + pd.offsets.MonthBegin(1) + pd.Timedelta(days=2),
        }
        for mes in meses
        for sub, preco in (("SUDESTE", 150.0), ("SUL", 140.0))
    ]
    return pd.DataFrame(linhas)


def _horas() -> pd.DataFrame:
    horas = pd.date_range("2026-09-01", "2026-10-18 23:00", freq="h")
    return pd.DataFrame(
        {"instante": horas, "tipo": "eolica", "nao_realizada_mwmed": 2.0}
    )


def _capacidade() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "tipo_de_usina": ["Hidrelétrica", "Hidrelétrica", "Eólica", "Eólica"],
            "potencia_efetiva_mw": [100.0, 50.0, 30.0, 20.0],
            "entrada_em_operacao": [
                D("2000-01-01"),
                D("2000-01-01"),
                D("2020-01-01"),
                D("2027-01-01"),
            ],
            "entrada_em_teste": [pd.NaT] * 4,
            "desativada_em": [pd.NaT, D("2026-01-01"), pd.NaT, pd.NaT],
        }
    )


def test_pld_so_traz_mes_fechado_e_ja_publico() -> None:
    tabela = mercado.pld_mensal(_pld(), DIA)
    # outubro não fechou em 20/10; setembro fechou e foi público em 02/10
    assert tabela["referencia"].max() == D("2026-09-01")
    assert set(tabela["submercado"]) == {"SUDESTE", "SUL"}


def test_curtailment_soma_as_horas_do_mes_fechado() -> None:
    tabela = mercado.curtailment_mensal(_horas(), DIA)
    setembro = tabela[tabela["mes"] == D("2026-09-01")].iloc[0]
    assert setembro["mwh"] == 30 * 24 * 2.0
    assert D("2026-10-01") not in set(tabela["mes"])


def test_capacidade_so_conta_unidade_em_operacao_no_dia() -> None:
    tabela = mercado.capacidade_por_tipo(_capacidade(), DIA).set_index("tipo_de_usina")
    assert tabela.loc["Hidrelétrica", "potencia_mw"] == 100.0  # a outra foi desativada
    assert tabela.loc["Eólica", "potencia_mw"] == 30.0  # a de 2027 ainda não existe


def test_sem_olhar_o_futuro_o_resumo_de_ontem_nao_muda_com_dado_de_amanha() -> None:
    """Cortar o futuro não muda o passado: o resumo do dia 05/10 é o mesmo sem as horas depois dele."""
    dia = D("2026-10-05")
    horas, pld = _horas(), _pld()
    cortada = horas[horas["instante"] < dia]
    assert mercado.curtailment_mensal(cortada, dia).equals(
        mercado.curtailment_mensal(horas, dia)
    )
    assert mercado.pld_mensal(pld, dia).equals(
        mercado.pld_mensal(pld[pld["disponivel_em"] <= dia], dia)
    )


def test_vazio_nao_quebra() -> None:
    vazio = pd.DataFrame()
    assert mercado.pld_mensal(vazio, DIA).empty
    assert mercado.curtailment_mensal(vazio, DIA).empty
    assert mercado.capacidade_por_tipo(vazio, DIA).empty


def _secao_com_mercado() -> dict:
    setor = rs.setor_do_relatorio("eletricas")
    membros = dossie_da_base.membros_do_setor(
        setor,
        pd.DataFrame(
            {
                "cnpj": [CPFL, OUTRA],
                "empresa": ["CPFL ENERGIA S.A.", "OUTRA ENERGIA S.A."],
            }
        ),
        _ligacoes(),
    )
    secao = dossie_da_base.secao_setor(
        setor,
        membros,
        {"aneel_consumidores": _consumidores()},
        _ligacoes(),
        {},
        {
            "pld_mensal": mercado.pld_mensal(_pld(), DIA),
            "curtailment_mensal": mercado.curtailment_mensal(_horas(), DIA),
            "capacidade_por_tipo": mercado.capacidade_por_tipo(_capacidade(), DIA),
        },
    )
    assert secao is not None
    return json.loads(json.dumps(secao, allow_nan=False))


@pytest.fixture
def noite_com_mercado(tmp_path: Path) -> dossie.SecaoDoSetor:
    noite = dossie.secao_do_setor(
        "eletricas", gravar_noite(tmp_path, _secao_com_mercado())
    )
    assert noite is not None
    return noite


def test_relatorio_mostra_o_mercado_de_energia(noite_com_mercado) -> None:
    relatorio = rs.montar_relatorio_do_setor(_entradas(noite_com_mercado), "pro", HOJE)
    secao = next(s for s in relatorio.secoes if s.chave == "mercado_de_energia")
    assert not secao.trancada
    assert set(secao.tabelas) == set(rs.TABELAS_DO_MERCADO_DE_ENERGIA)
    assert {i.chave for i in secao.itens} == {
        "pld_mensal",
        "curtailment_mensal",
        "capacidade_instalada",
    } or secao.itens
    assert secao.tabelas["pld_mensal"][0]["Submercado"] == "Sudeste"
    assert next(i for i in secao.itens if i.chave == "pld_mensal").valor
    assert any("CCEE" in f or "ONS" in f for f in secao.paragrafos)
    # PLD, curtailment e capacidade saem de "o que não temos"; o CMO fica
    faltas = {f.kpi for f in relatorio.nao_temos}
    assert {"CMO"} <= faltas and not faltas & {
        "PLD",
        "Curtailment",
        "Capacidade instalada",
    }


def test_mercado_de_energia_fica_trancado_sem_o_plano(noite_com_mercado) -> None:
    relatorio = rs.montar_relatorio_do_setor(
        _entradas(noite_com_mercado), "gratuito", HOJE
    )
    secao = next(s for s in relatorio.secoes if s.chave == "mercado_de_energia")
    assert secao.trancada and not secao.tabelas


def test_so_as_eletricas_levam_o_mercado_de_energia() -> None:
    setor = next(
        s for s in dossie_da_base.SETORES_DO_LANCAMENTO if s.chave == "telecom"
    )
    assert (
        dossie_da_base._do_mercado_de_energia(
            setor, {"pld_mensal": mercado.pld_mensal(_pld(), DIA)}
        )
        == {}
    )


class _LeitorDeMentira:
    """Entrega as três tabelas do mercado como a porta entregaria (sem o DuckDB)."""

    def ler(self, tabela, colunas, filtros=None, como_era_em=None):
        return _pld() if tabela == "ccee_pld" else _capacidade()

    def somar(self, tabela, agrupar_por, coluna, filtros, como_era_em=None):
        return _horas()


def test_a_noite_monta_as_tres_tabelas_do_mercado() -> None:
    from scripts import gerar_dossies

    feito = gerar_dossies._mercado_de_energia(_LeitorDeMentira(), DIA)
    assert set(feito) == {"pld_mensal", "curtailment_mensal", "capacidade_por_tipo"}
    assert not feito["pld_mensal"].empty and not feito["capacidade_por_tipo"].empty
