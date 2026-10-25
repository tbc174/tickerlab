"""Revisões do BC no cadastro do IF.data e no SCR.data: a revisão é linha nova da mesma chave e só vale
desde o dia em que foi vista (`visto_em`), como nos valores do IF.data (#554, `base/setoriais/revisoes.py`)."""

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from base import bcb_ifdata, bcb_scr
from base.setoriais import revisoes
from tests.test_base_bcb import _ifdata, _scr

CHAVE_DO_CADASTRO = list(bcb_ifdata.CHAVE_DO_CADASTRO)
CHAVE_DO_SCR = [*bcb_scr.COLUNAS_DE_TEXTO, "ocorrencia"]
DIA1, DIA2 = pd.Timestamp("2026-10-10"), pd.Timestamp("2026-11-20")


def _cadastro_revisado() -> tuple[pd.DataFrame, pd.DataFrame]:
    antes = bcb_ifdata.ler_cadastro(_ifdata("cadastro_202506.json"))
    depois = antes.copy()
    depois.loc[0, "instituicao"] = "NOME REVISADO"
    return antes, depois


def test_cadastro_revisado_vira_linha_nova_que_vale_so_desde_o_dia_visto():
    antes, depois = _cadastro_revisado()
    tabela = bcb_ifdata.cadastro_com_revisoes([(DIA1, antes), (DIA2, depois)])
    codigo = antes.loc[0, "cod_inst"]
    da_instituicao = tabela[tabela["cod_inst"] == codigo].sort_values("visto_em")
    assert da_instituicao["instituicao"].tolist() == [
        antes.loc[0, "instituicao"],
        "NOME REVISADO",
    ]
    prazo = bcb_ifdata.disponivel_em(antes).iloc[0]
    assert da_instituicao["disponivel_em"].tolist() == [prazo, max(prazo, DIA2)]
    # as outras instituições não mudaram: uma linha só
    assert len(tabela) == len(antes) + 1


def test_cadastro_como_era_antes_da_revisao_devolve_o_nome_antigo():
    antes, depois = _cadastro_revisado()
    tabela = bcb_ifdata.cadastro_com_revisoes([(DIA1, antes), (DIA2, depois)])
    dia_da_revisao = tabela["disponivel_em"].max()
    na_vespera = revisoes.como_era_em(
        tabela, dia_da_revisao - pd.Timedelta(days=1), CHAVE_DO_CADASTRO
    )
    assert "NOME REVISADO" not in set(na_vespera["instituicao"])
    no_dia = revisoes.como_era_em(tabela, dia_da_revisao, CHAVE_DO_CADASTRO)
    assert "NOME REVISADO" in set(no_dia["instituicao"])


def test_cadastro_mais_novo_deixa_uma_linha_por_instituicao():
    antes, depois = _cadastro_revisado()
    tabela = bcb_ifdata.cadastro_com_revisoes([(DIA1, antes), (DIA2, depois)])
    atual = bcb_ifdata.cadastro_mais_novo(tabela)
    assert not atual.duplicated(CHAVE_DO_CADASTRO).any()
    assert len(atual) == len(antes)
    assert "NOME REVISADO" in set(atual["instituicao"])


def test_cadastro_mais_novo_aceita_tabela_sem_revisoes():
    sem = bcb_ifdata.ler_cadastro(_ifdata("cadastro_202506.json"))
    assert len(bcb_ifdata.cadastro_mais_novo(sem)) == len(sem)


def test_cadastro_sem_o_dia_da_coleta_vale_desde_o_prazo():
    antes, _ = _cadastro_revisado()
    tabela = bcb_ifdata.cadastro_com_revisoes([(pd.NaT, antes)])
    assert tabela["visto_em"].isna().all()
    assert (tabela["disponivel_em"] == bcb_ifdata.disponivel_em(tabela)).all()


def _scr_revisado() -> tuple[pd.DataFrame, pd.DataFrame]:
    antes = bcb_scr.ler_ano(_scr("scrdata_2012.zip"))
    depois = antes.copy()
    depois.loc[0, "carteira_ativa"] = antes.loc[0, "carteira_ativa"] + 1.0
    return antes, depois


def test_scr_revisado_vira_linha_nova_que_vale_so_desde_o_dia_visto():
    antes, depois = _scr_revisado()
    tabela = bcb_scr.ano_com_revisoes([(DIA1, antes), (DIA2, depois)])
    assert len(tabela) == len(antes) + 1
    (nova,) = tabela[tabela["visto_em"] == DIA2].to_dict("records")
    velha = tabela[tabela["visto_em"] == DIA1].iloc[0]
    assert nova["carteira_ativa"] == antes.loc[0, "carteira_ativa"] + 1.0
    assert nova["disponivel_em"] == max(velha["disponivel_em"], DIA2) > DIA1


def test_scr_linhas_iguais_da_mesma_chave_continuam_todas():
    """O BC publica mais de uma linha por chave (a amostra tem 6 pares iguais) e a base soma todas."""
    antes, _ = _scr_revisado()
    assert antes.duplicated(list(bcb_scr.COLUNAS_DE_TEXTO)).any()
    tabela = bcb_scr.ano_com_revisoes([(DIA1, antes), (DIA2, antes.copy())])
    assert len(tabela) == len(antes)


def test_scr_igual_na_coleta_seguinte_nao_vira_linha_nova():
    antes, _ = _scr_revisado()
    tabela = bcb_scr.ano_com_revisoes([(DIA1, antes), (DIA2, antes.copy())])
    assert len(tabela) == len(antes)


@settings(deadline=None, max_examples=20)
@given(st.integers(0, 60), st.floats(1, 1e6))
def test_scr_cortar_o_futuro_nao_muda_o_passado(dias_ate_a_revisao, acrescimo):
    """Princípio do projeto: a foto de um dia anterior à revisão é a mesma com ou sem a revisão."""
    antes = _SCR_BASE
    depois = antes.copy()
    depois.loc[0, "carteira_ativa"] = antes.loc[0, "carteira_ativa"] + acrescimo
    dia_da_revisao = DIA1 + pd.Timedelta(days=200 + dias_ate_a_revisao)
    com = bcb_scr.ano_com_revisoes([(DIA1, antes), (dia_da_revisao, depois)])
    sem = bcb_scr.ano_com_revisoes([(DIA1, antes)])
    vespera = dia_da_revisao - pd.Timedelta(days=1)
    foto_com = revisoes.como_era_em(com, vespera, CHAVE_DO_SCR)
    foto_sem = revisoes.como_era_em(sem, vespera, CHAVE_DO_SCR)
    ordem = ["data_base", *CHAVE_DO_SCR[1:]]
    pd.testing.assert_frame_equal(
        foto_com.sort_values(ordem).reset_index(drop=True)[sem.columns],
        foto_sem.sort_values(ordem).reset_index(drop=True)[sem.columns],
        check_dtype=False,
        check_categorical=False,
    )


_SCR_BASE = bcb_scr.ler_ano(_scr("scrdata_2012.zip"))
