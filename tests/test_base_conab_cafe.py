"""Levantamentos de safra de café da CONAB, como publicados (PR 7 do plano do café, tarefa 7.1).

Licença CC BY-ND: a tabela guarda e devolve os números como a CONAB publicou; os testes cobrem a leitura,
a regra de nunca sobrescrever e o "como estava em D" (sem olhar o futuro).
"""

from datetime import date

import pandas as pd
import pytest

from base.commodities import conab_cafe
from tests.ajudantes_da_conab import planilha

D1, D2, D3, D4 = (
    date(2026, 2, 5),
    date(2026, 5, 21),
    date(2026, 9, 24),
    date(2026, 12, 4),
)


def _ler(levantamento=3, divulgado_em=D3, fator=1.0):
    return conab_cafe.ler_levantamento(
        planilha(2026, fator), levantamento, divulgado_em
    )


def test_ler_levantamento_colunas_e_valores():
    tabela = _ler()
    assert list(tabela.columns) == list(conab_cafe.COLUNAS)
    mg = tabela[(tabela.tipo == "arabica") & (tabela.uf == "MG")].iloc[0]
    assert mg.safra == 2026 and mg.levantamento == 3
    assert mg.divulgado_em == pd.Timestamp(D3)
    assert mg.producao_mil_sacas == pytest.approx(3000.0)
    assert mg.produtividade_sc_ha == pytest.approx(30.0)
    assert mg.area_producao_ha == pytest.approx(100000.0)
    assert mg.area_formacao_ha == pytest.approx(8000.0)  # vem da aba de área


def test_so_a_safra_do_levantamento_entra_nao_a_coluna_do_ano_anterior():
    assert set(_ler().safra) == {2026}


def test_ufs_o_brasil_e_outros_entram_regioes_e_subregioes_nao():
    ufs = set(_ler().uf)
    assert ufs == {"MG", "ES", "OUTROS", "BRASIL"}


def test_arabica_conilon_e_total_ficam_separados():
    tabela = _ler()
    assert set(tabela.tipo) == {"arabica", "conilon", "total"}
    producao = tabela[tabela.uf == "MG"].set_index("tipo").producao_mil_sacas
    assert producao["arabica"] == pytest.approx(3000.0)
    assert producao["conilon"] == pytest.approx(900.0)


def test_celula_vazia_vira_nan_nao_zero():
    tabela = _ler()
    outros = tabela[(tabela.tipo == "arabica") & (tabela.uf == "OUTROS")].iloc[0]
    assert pd.isna(outros.area_formacao_ha)  # OUTROS não está na aba de área


def test_levantamento_fora_de_1_a_4_e_recusado():
    with pytest.raises(ValueError):
        _ler(levantamento=5)


def test_planilha_sem_a_aba_esperada_da_erro_claro():
    with pytest.raises(conab_cafe.ErroDeLeitura):
        conab_cafe.ler_levantamento(b"nao e uma planilha", 1, D1)


def test_identificar_levantamento_e_safra_pelo_endereco():
    url = (
        "https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/safras/safra-de-cafe/"
        "3o-levantamento-de-cafe-safra-2026/site_previsao-de-safra-cafe-set-2026.xls"
    )
    assert conab_cafe.identificar(url) == (3, 2026)
    assert conab_cafe.identificar("https://x/sem-padrao.xls") is None


def test_quatro_levantamentos_da_mesma_safra_ficam_todos():
    guardada = pd.DataFrame(columns=list(conab_cafe.COLUNAS))
    for n, dia in enumerate((D1, D2, D3, D4), start=1):
        guardada = conab_cafe.acrescentar(guardada, _ler(n, dia, fator=1 + n / 10))
    mg = guardada[(guardada.tipo == "arabica") & (guardada.uf == "MG")]
    assert sorted(mg.levantamento) == [1, 2, 3, 4]
    assert mg.producao_mil_sacas.nunique() == 4  # nenhum sobrescreveu outro


def test_coletar_de_novo_o_mesmo_levantamento_nao_duplica():
    guardada = conab_cafe.acrescentar(
        pd.DataFrame(columns=list(conab_cafe.COLUNAS)), _ler()
    )
    de_novo = conab_cafe.acrescentar(guardada, _ler())
    assert len(de_novo) == len(guardada)


def test_revisao_do_mesmo_levantamento_com_outra_data_fica_ao_lado():
    guardada = conab_cafe.acrescentar(
        pd.DataFrame(columns=list(conab_cafe.COLUNAS)), _ler()
    )
    revisada = conab_cafe.acrescentar(guardada, _ler(3, date(2026, 10, 2), fator=1.1))
    mg = revisada[(revisada.tipo == "arabica") & (revisada.uf == "MG")]
    assert len(mg) == 2 and set(mg.divulgado_em) == {
        pd.Timestamp(D3),
        pd.Timestamp("2026-10-02"),
    }


def test_corte_em_d_nao_muda_o_passado():
    guardada = pd.DataFrame(columns=list(conab_cafe.COLUNAS))
    for n, dia in enumerate((D1, D2, D3), start=1):
        guardada = conab_cafe.acrescentar(guardada, _ler(n, dia, fator=1 + n / 10))
    entre_1_e_2 = conab_cafe.como_estava_em(guardada, date(2026, 3, 1))
    mg = entre_1_e_2[(entre_1_e_2.tipo == "arabica") & (entre_1_e_2.uf == "MG")]
    assert list(mg.levantamento) == [1]
    assert mg.producao_mil_sacas.iloc[0] == pytest.approx(3300.0)
    # cortar o futuro não muda o que a data já conhecia
    pelo_mais_novo = conab_cafe.como_estava_em(guardada, date(2026, 12, 31))
    mg2 = pelo_mais_novo[
        (pelo_mais_novo.tipo == "arabica") & (pelo_mais_novo.uf == "MG")
    ]
    assert list(mg2.levantamento) == [3]


def test_como_estava_em_d_antes_do_primeiro_devolve_vazio():
    guardada = conab_cafe.acrescentar(
        pd.DataFrame(columns=list(conab_cafe.COLUNAS)), _ler()
    )
    assert conab_cafe.como_estava_em(guardada, date(2026, 1, 1)).empty


def _pagina(publicado: str) -> bytes:
    return (
        f'<span class="documentPublished"><span>Publicado em</span> <!-- c --> '
        f'<span class="value">{publicado}</span></span>'
    ).encode()


def test_data_de_publicacao_vem_do_publicado_em_da_pagina():
    assert conab_cafe.data_de_publicacao(_pagina("04/09/2025 09h00")) == date(
        2025, 9, 4
    )
    assert conab_cafe.data_de_publicacao(b"<html></html>") is None
    assert conab_cafe.data_de_publicacao(_pagina("31/02/2025 09h00")) is None


def test_data_fora_de_ordem_na_safra_vira_none_e_as_outras_ficam():
    datas = {
        (2024, 1): date(2025, 1, 24),  # a página reeditada: depois do 3º e do 4º
        (2024, 3): date(2024, 9, 19),
        (2024, 4): date(2025, 1, 21),
        (2026, 1): date(2026, 2, 5),
        (2026, 2): None,
        (2026, 3): date(2026, 9, 24),
    }
    em_ordem = conab_cafe.datas_em_ordem(datas)
    assert em_ordem[(2024, 1)] is None
    assert em_ordem[(2024, 3)] == date(2024, 9, 19)
    assert em_ordem[(2024, 4)] == date(2025, 1, 21)
    assert em_ordem[(2026, 1)] == date(2026, 2, 5)
    assert em_ordem[(2026, 2)] is None and em_ordem[(2026, 3)] == date(2026, 9, 24)


def test_a_marca_de_data_aproximada_acompanha_a_linha():
    assert not _ler()["divulgado_aproximado"].any()
    aproximada = conab_cafe.ler_levantamento(planilha(2026), 3, D3, aproximada=True)
    assert aproximada["divulgado_aproximado"].all()


def test_corte_por_data_nao_mostra_levantamento_antes_da_publicacao():
    # o 3º foi coletado em out/2026, mas a CONAB o publicou em 24/09: vale desde 24/09, não desde a coleta
    tabela = pd.concat([_ler(1, D1), _ler(3, D3)], ignore_index=True)
    assert set(
        conab_cafe.como_estava_em(tabela, date(2026, 9, 23))["levantamento"]
    ) == {1}
    assert set(conab_cafe.como_estava_em(tabela, D3)["levantamento"]) == {3}
