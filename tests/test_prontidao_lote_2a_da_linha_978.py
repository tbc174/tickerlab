"""Lote 2A de tabelas ligadas pelo CNPJ no registro de piloto (linha 978; ADR 0108, Emenda 2, D11).

Nove tabelas da CVM que já chegam ao servidor e não abriam por falta do registro de piloto: o FRE (comitês,
distribuição de capital, diversidade, empregados, extremos da remuneração), os pareceres dos auditores (DFP e
ITR), as assembleias de debenturistas e os processos das notas explicativas. Cada uma tem as três
coisas que o piloto cobra: a prova 7 (placar de qualidade de 18/11/2026, verde na VM), o dicionário escrito e a
marca de pessoa decidida pela raiz (todo CNPJ dentro da `cnpj_empresas_pj`, medido por `conferir_sem_pessoa`).
O que este arquivo cobra é o **registro de verdade**; a regra do portão fica em `test_prontidao.py`.
"""

from datetime import date

import pytest

from base import prontidao, sem_pessoa_por_raiz
from base.dicionario import TABELAS
from base.qualidade_automatica import REGRAS

HOJE = date(2026, 11, 18)
DO_LOTE_2A = (
    "fre_comites",
    "fre_distribuicao_capital",
    "fre_diversidade",
    "fre_empregados",
    "fre_remuneracao_extremos",
    "pareceres_dfp",
    "pareceres_itr",
    "debentures_assembleias",
    "processos_nas_notas",
)
# Fica fora por data: a linha (emissor, cnpj) vale desde o primeiro FCA, mas `ultimo_ano`, `conflito` e `empresa`
# são calculados sobre todo o histórico até a última carga (revisão cruzada de 18/11/2026). Quem consultasse
# "como era em 2012" veria a sobrevivência até 2024 e um conflito de CNPJ que só nasceu em 2019. Só abre depois
# de datar essas colunas (uma linha por FCA, como a `tickers_no_tempo`).
FORA_POR_DATA = ("emissores",)
# medidas em 18/11/2026 que ficaram de fora do lote: placar vermelho sem explicação escrita
VERMELHAS_NA_MEDIDA = (
    "fre_capital_social",
    "fre_conselho",
    "fre_remuneracao",
    "ratings",
    "valores_mobiliarios",
    "tickers_no_tempo",
    "codigos_invalidos",
    "dmpl_como_era",
    "insolvencia",
    "negociacoes",
    "anm_cfem_arrecadacao",
    "painel_dos_fundos",
    "securitizacao_certificados",
)


@pytest.mark.parametrize("tabela", DO_LOTE_2A)
def test_o_registro_de_verdade_libera_a_tabela_pelo_piloto(tabela: str) -> None:
    falta = prontidao.negacao_do_piloto(
        (tabela,),
        prontidao.PRONTIDAO_DE_PILOTO,
        prontidao.versoes_maiores(),
        prontidao.tabelas_com_pessoa_decidida(),
        HOJE,
    )
    assert falta is None


@pytest.mark.parametrize("tabela", DO_LOTE_2A)
def test_a_versao_e_as_duas_provas_sao_as_do_piloto(tabela: str) -> None:
    registro = prontidao.PRONTIDAO_DE_PILOTO[tabela]
    assert registro.versao_maior == prontidao.versoes_maiores()[tabela]
    assert registro.qualidade is not None and registro.dicionario is not None
    assert registro.qualidade.data == HOJE
    assert registro.qualidade.prova == "placar-qualidade-2026-11-18"
    assert registro.dicionario.prova == "dicionario-escrito-2026-11-18"
    assert prontidao.prova_publicavel(registro.qualidade.prova)
    assert prontidao.prova_publicavel(registro.dicionario.prova)


@pytest.mark.parametrize("tabela", DO_LOTE_2A)
def test_a_tabela_tem_regra_de_qualidade_e_nao_vira_prontidao_cheia(
    tabela: str,
) -> None:
    assert tabela in REGRAS
    assert tabela not in prontidao.PRONTIDAO
    assert not TABELAS[tabela].pessoa


@pytest.mark.parametrize("tabela", DO_LOTE_2A)
def test_a_marca_de_pessoa_vem_da_prova_da_raiz(tabela: str) -> None:
    """A tabela só vale como sem pessoa porque a raiz do CNPJ dela foi cruzada com a `cnpj_empresas_pj`."""
    coluna = sem_pessoa_por_raiz.SEM_PESSOA_PELA_RAIZ[tabela]
    assert coluna in TABELAS[tabela].colunas
    assert tabela in prontidao.SEM_PESSOA_NA_MONTAGEM


@pytest.mark.parametrize("tabela", DO_LOTE_2A)
def test_a_tabela_tem_a_data_em_que_ficou_publica(tabela: str) -> None:
    """Sem olhar o futuro: o contrato diz de que coluna vem o dia em que o dado ficou público."""
    publico_em = TABELAS[tabela].datas["publico_em"]
    assert publico_em in TABELAS[tabela].colunas


@pytest.mark.parametrize("tabela", VERMELHAS_NA_MEDIDA)
def test_o_que_ficou_vermelho_na_medida_nao_entra_no_registro(tabela: str) -> None:
    """Placar vermelho sem explicação escrita não tem a prova 7: a tabela fica fechada até a regra ser calibrada."""
    assert tabela not in prontidao.PRONTIDAO_DE_PILOTO
    assert tabela not in REGRAS


@pytest.mark.parametrize("tabela", FORA_POR_DATA)
def test_a_tabela_com_coluna_calculada_sobre_o_futuro_nao_entra_no_registro(
    tabela: str,
) -> None:
    """O placar é verde e a raiz confere, mas o `publico_em` da linha não cobre as colunas do histórico inteiro."""
    assert tabela not in prontidao.PRONTIDAO_DE_PILOTO
