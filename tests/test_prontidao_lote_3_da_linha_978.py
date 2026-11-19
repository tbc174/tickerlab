"""Lote 3 no registro de piloto (linha 978; ADR 0108, Emenda 2, D11; licença não trava o piloto: ADR 0122, Emenda 2).

Treze tabelas medidas na VM em 19/11/2026 (contagem por ano, vazios por coluna, repetidas por chave): placar sem
vermelho, sem coluna de CNPJ (a marca de pessoa não se aplica) e com a coluna do dia em que o dado ficou público. As
outras medidas do lote deram vermelho sem explicação verificada e ficaram de fora, com o motivo na nota do levantamento.
"""

from datetime import date

import pytest

from base import prontidao
from base.dicionario import TABELAS
from base.qualidade_automatica import REGRAS

HOJE = date(2026, 11, 19)
DO_LOTE_3 = (
    "anm_amb_agua_mineral",
    "antt_siade",
    "bcb_selic_focus",
    "cftc_cot_agro",
    "cnes_competencias",
    "comex_cafe",
    "comex_urf",
    "comex_via",
    "conab_cafe",
    "faostat_cafe",
    "ma_datas",
    "ons_capacidade",
    "usda_psd_cafe",
)
FICARAM_DE_FORA = (
    "anac_estatistico",
    "anm_amb_producao_beneficiada",
    "anm_amb_producao_bruta",
    "anp_vendas",
    "area_cafe_municipio",
    "ccee_pld",
    "clima_regiao_cafe",
    "curva_juros",
    "ons_restricao",
    "contraparte_cafe",
    "ma_candidatos",
    "ma_regua",
)


@pytest.mark.parametrize("tabela", DO_LOTE_3)
def test_o_registro_de_verdade_libera_a_tabela_pelo_piloto(tabela: str) -> None:
    falta = prontidao.negacao_do_piloto(
        (tabela,),
        prontidao.PRONTIDAO_DE_PILOTO,
        prontidao.versoes_maiores(),
        prontidao.tabelas_com_pessoa_decidida(),
        HOJE,
    )
    assert falta is None


@pytest.mark.parametrize("tabela", DO_LOTE_3)
def test_a_versao_e_as_duas_provas_sao_as_do_piloto(tabela: str) -> None:
    registro = prontidao.PRONTIDAO_DE_PILOTO[tabela]
    assert registro.versao_maior == prontidao.versoes_maiores()[tabela]
    assert registro.qualidade is not None and registro.dicionario is not None
    assert registro.qualidade.data == HOJE
    assert registro.qualidade.prova == "placar-qualidade-2026-11-19"
    assert registro.dicionario.prova == "dicionario-escrito-2026-11-19"
    assert prontidao.prova_publicavel(registro.qualidade.prova)
    assert prontidao.prova_publicavel(registro.dicionario.prova)


@pytest.mark.parametrize("tabela", DO_LOTE_3)
def test_a_tabela_tem_regra_de_qualidade_e_nao_vira_prontidao_cheia(
    tabela: str,
) -> None:
    assert tabela in REGRAS
    assert tabela not in prontidao.PRONTIDAO
    assert not TABELAS[tabela].pessoa
    assert not TABELAS[tabela].linhas_de_pessoa


@pytest.mark.parametrize("tabela", DO_LOTE_3)
def test_a_tabela_tem_a_data_em_que_ficou_publica(tabela: str) -> None:
    """Sem olhar o futuro: o contrato diz de que coluna vem o dia em que o dado ficou público."""
    assert TABELAS[tabela].datas["publico_em"] in TABELAS[tabela].colunas


@pytest.mark.parametrize("tabela", FICARAM_DE_FORA)
def test_as_que_mediram_vermelho_ou_com_raiz_de_fora_nao_entram(tabela: str) -> None:
    assert tabela not in prontidao.PRONTIDAO_DE_PILOTO
