"""Lote 2B no registro de piloto (linha 978; ADR 0108, Emenda 2, D11): as duas tabelas que o lote 1 deixou fora e o Fiagro.

`aneel_inadimplencia` e `fii_ativos` mediram vermelho no lote 1 só pela chave do rascunho da regra; as medidas de
contagem de 18/11/2026 na VM (linhas por ano, vazios por coluna, repetidas por chave candidata) mostraram a chave
certa de cada uma, e o placar ficou verde (a inadimplência com o salto de 2013 e de 2014 explicado por escrito).
`cvm_fiagro` mediu verde no lote 2 e ficou para este por causa do limite de dez tabelas por PR; a marca de pessoa
dela vem da raiz do CNPJ (0 raiz fora da `cnpj_empresas_pj`).
"""

from datetime import date

import pytest

from base import prontidao, sem_pessoa_por_raiz
from base.dicionario import TABELAS
from base.qualidade_automatica import REGRAS

HOJE = date(2026, 11, 18)
DO_LOTE_2B = ("aneel_inadimplencia", "fii_ativos", "cvm_fiagro")


@pytest.mark.parametrize("tabela", DO_LOTE_2B)
def test_o_registro_de_verdade_libera_a_tabela_pelo_piloto(tabela: str) -> None:
    falta = prontidao.negacao_do_piloto(
        (tabela,),
        prontidao.PRONTIDAO_DE_PILOTO,
        prontidao.versoes_maiores(),
        prontidao.tabelas_com_pessoa_decidida(),
        HOJE,
    )
    assert falta is None


@pytest.mark.parametrize("tabela", DO_LOTE_2B)
def test_a_versao_e_as_duas_provas_sao_as_do_piloto(tabela: str) -> None:
    registro = prontidao.PRONTIDAO_DE_PILOTO[tabela]
    assert registro.versao_maior == prontidao.versoes_maiores()[tabela]
    assert registro.qualidade is not None and registro.dicionario is not None
    assert registro.qualidade.data == HOJE
    assert registro.qualidade.prova == "placar-qualidade-2026-11-18"
    assert registro.dicionario.prova == "dicionario-escrito-2026-11-18"
    assert prontidao.prova_publicavel(registro.qualidade.prova)
    assert prontidao.prova_publicavel(registro.dicionario.prova)


@pytest.mark.parametrize("tabela", DO_LOTE_2B)
def test_a_tabela_tem_regra_de_qualidade_e_nao_vira_prontidao_cheia(
    tabela: str,
) -> None:
    assert tabela in REGRAS
    assert tabela not in prontidao.PRONTIDAO
    assert not TABELAS[tabela].pessoa


@pytest.mark.parametrize("tabela", DO_LOTE_2B)
def test_a_tabela_tem_a_data_em_que_ficou_publica(tabela: str) -> None:
    """Sem olhar o futuro: o contrato diz de que coluna vem o dia em que o dado ficou público."""
    assert TABELAS[tabela].datas["publico_em"] in TABELAS[tabela].colunas


def test_a_inadimplencia_explica_por_escrito_o_salto_de_2013_e_de_2014() -> None:
    explicados = REGRAS["aneel_inadimplencia"].saltos_explicados
    assert {2013, 2014} <= set(explicados)
    assert all("não foi confirmado" in texto for texto in explicados.values())


def test_o_fiagro_tem_a_marca_de_pessoa_pela_raiz() -> None:
    assert sem_pessoa_por_raiz.SEM_PESSOA_PELA_RAIZ["cvm_fiagro"] == "cnpj"
    assert sem_pessoa_por_raiz.RAIZ_SEPARADA["cvm_fiagro"] == "cnpj_basico"
    assert "cvm_fiagro" in prontidao.SEM_PESSOA_NA_MONTAGEM
    assert "cvm_fiagro" in prontidao.tabelas_com_pessoa_decidida()
