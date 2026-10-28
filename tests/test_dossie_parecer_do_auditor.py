"""O parecer do auditor na ficha (linha 158, 28/10/2026): o relatório da DFP mais nova já entregue, com o
rastro, sem olhar o futuro. Só o dado: a seção `auditor_e_controladas` ainda não o mostra (os textos que o
usuário lê esperam o "pode" do Tiago)."""

from datetime import date

import pandas as pd

from base import dossie
from base.dicionario import TABELAS
from src.banco.coletas import LICENCAS

D = pd.Timestamp
SIM, NAO, NC = "sim", "nao", "nao_classificado"


def _parecer(
    ano: int,
    entregue: str,
    *,
    versao: int = 1,
    opiniao: str = "sem_ressalva",
    enfase: str = NAO,
    continuidade: str = NAO,
) -> dict:
    return {
        "cnpj": "00.000.000/0001-91",
        "referencia": date(ano, 12, 31),
        "versao": versao,
        "disponivel_em": date.fromisoformat(entregue),
        "opiniao": opiniao,
        "enfase": enfase,
        "continuidade_operacional": continuidade,
    }


def _tabela(*linhas: dict) -> pd.DataFrame:
    return pd.DataFrame(list(linhas))


def _valores(itens: list[dict]) -> dict:
    return {i["chave"]: i["valor"] for i in itens}


def test_usa_o_parecer_da_dfp_mais_nova_ja_entregue() -> None:
    pareceres = _tabela(
        _parecer(2023, "2024-03-20"),
        _parecer(2024, "2025-03-18", opiniao="com_ressalva", enfase=SIM),
    )
    itens, tabela = dossie.parecer_do_auditor(pareceres, D("2025-06-01"))
    assert _valores(itens) == {
        "parecer_opiniao": "com_ressalva",
        "parecer_enfase": SIM,
        "parecer_continuidade": NAO,
    }
    assert {i["base"] for i in itens} == {"2024-12-31"}
    assert list(tabela["referencia"]) == [date(2024, 12, 31), date(2023, 12, 31)]


def test_o_rastro_diz_o_dia_em_que_o_relatorio_ficou_publico() -> None:
    itens, _ = dossie.parecer_do_auditor(
        _tabela(_parecer(2024, "2025-03-18")), D("2025-06-01")
    )
    for item in itens:
        assert item["rastro"]["publicado_em"] == "2025-03-18"
        assert item["rastro"]["fonte_id"] == TABELAS["pareceres_dfp"].familia_da_fonte
        assert item["rastro"]["formula"].strip()


def test_toda_chave_do_parecer_tem_origem_na_tabela_certa() -> None:
    for chave, _, _ in dossie.CAMPOS_DO_PARECER:
        origem = dossie.ORIGEM_DOS_ITENS[chave]
        assert origem.tabela == "pareceres_dfp"
        assert TABELAS[origem.tabela].familia_da_fonte in LICENCAS


def test_parecer_entregue_depois_do_dia_nao_existe_para_a_ficha() -> None:
    """Sem olhar o futuro: a DFP de 2024 só vale a partir de 18/03/2025."""
    pareceres = _tabela(
        _parecer(2023, "2024-03-20", opiniao="sem_ressalva"),
        _parecer(2024, "2025-03-18", opiniao="adversa"),
    )
    itens, tabela = dossie.parecer_do_auditor(pareceres, D("2025-03-17"))
    assert _valores(itens)["parecer_opiniao"] == "sem_ressalva"
    assert list(tabela["referencia"]) == [date(2023, 12, 31)]
    antes_de_tudo, tabela_vazia = dossie.parecer_do_auditor(pareceres, D("2024-03-19"))
    assert antes_de_tudo == []
    assert tabela_vazia.empty


def test_cortar_o_futuro_nao_muda_o_passado() -> None:
    completo = _tabela(
        _parecer(2022, "2023-03-10"),
        _parecer(2023, "2024-03-20", enfase=SIM),
        _parecer(2024, "2025-03-18", continuidade=SIM),
    )
    dia = D("2024-06-30")
    cortado = completo[pd.to_datetime(completo["disponivel_em"]) <= dia]
    do_completo = dossie.parecer_do_auditor(completo, dia)
    do_cortado = dossie.parecer_do_auditor(cortado, dia)
    assert do_completo[0] == do_cortado[0]
    pd.testing.assert_frame_equal(do_completo[1], do_cortado[1])


def test_reapresentacao_so_vale_a_partir_do_dia_em_que_foi_entregue() -> None:
    pareceres = _tabela(
        _parecer(2024, "2025-03-18", versao=1, opiniao="sem_ressalva"),
        _parecer(2024, "2025-09-02", versao=2, opiniao="com_ressalva"),
    )
    antes, _ = dossie.parecer_do_auditor(pareceres, D("2025-09-01"))
    depois, tabela = dossie.parecer_do_auditor(pareceres, D("2025-09-02"))
    assert _valores(antes)["parecer_opiniao"] == "sem_ressalva"
    assert antes[0]["rastro"]["publicado_em"] == "2025-03-18"
    assert _valores(depois)["parecer_opiniao"] == "com_ressalva"
    assert depois[0]["rastro"]["publicado_em"] == "2025-09-02"
    assert list(tabela["versao"]) == [2]


def test_o_que_a_base_nao_classificou_nao_vira_item() -> None:
    """`nao_classificado` não é `nao`: a ficha não diz o que a base não soube dizer."""
    itens, tabela = dossie.parecer_do_auditor(
        _tabela(_parecer(2010, "2011-03-01", opiniao=NC, enfase=NC, continuidade=SIM)),
        D("2026-10-28"),
    )
    assert _valores(itens) == {"parecer_continuidade": SIM}
    assert (
        tabela.iloc[0]["opiniao"] == NC
    )  # a tabela mostra o que a base disse, como disse


def test_sem_parecer_nao_ha_item_nem_tabela() -> None:
    itens, tabela = dossie.parecer_do_auditor(pd.DataFrame(), D("2026-10-28"))
    assert itens == []
    assert tabela.empty


def test_a_tabela_mostra_so_os_ultimos_exercicios() -> None:
    pareceres = _tabela(
        *(_parecer(ano, f"{ano + 1}-03-15") for ano in range(2015, 2025))
    )
    _, tabela = dossie.parecer_do_auditor(pareceres, D("2025-06-01"))
    assert len(tabela) == dossie.EXERCICIOS_DO_PARECER
    assert tabela["referencia"].iloc[0] == date(2024, 12, 31)
