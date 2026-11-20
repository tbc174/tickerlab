"""As quatro fontes ampliadas no registro de piloto (linha 978; ADR 0108, Emenda 3, D11).

`anatel_pados`, `anatel_produtos_homologados`, `anp_tancagem` e `mte_pat` têm CNPJ de 14 dígitos em todas as linhas e a
marca `trata_como_pessoa` por linha (titular de MEI ou de empresário individual). O contrato diz `pessoa=False`, e
`pessoa_decidida` já vale pela marca por linha; o que faltava era o registro de piloto. Só contam como prontas porque o
servidor da API guarda apenas a cópia reduzida só-PJ de `base/recorte_dos_cadastros.py` (degrau 8), conferida por
`conferir_cadastros` a cada montagem. O placar de 19/11/2026 deu verde nas quatro.
"""

from datetime import date

import pytest

from base import prontidao, recorte_dos_cadastros
from base.dicionario import TABELAS
from base.qualidade_automatica import REGRAS

HOJE = date(2026, 11, 19)
AMPLIADAS = (
    "anatel_pados",
    "anatel_produtos_homologados",
    "anp_tancagem",
    "mte_pat",
)


def test_a_lista_decidida_e_a_que_o_recorte_reduz() -> None:
    assert frozenset(AMPLIADAS) == frozenset(recorte_dos_cadastros.AMPLIADAS)
    for nome in AMPLIADAS:
        assert nome in recorte_dos_cadastros.COLUNAS


@pytest.mark.parametrize("tabela", AMPLIADAS)
def test_a_marca_de_pessoa_por_linha_existe_e_a_tabela_conta_como_decidida(
    tabela: str,
) -> None:
    contrato = TABELAS[tabela]
    assert contrato.linhas_de_pessoa == "trata_como_pessoa"
    assert contrato.linhas_de_pessoa in contrato.colunas
    assert tabela in prontidao.tabelas_com_pessoa_decidida()


@pytest.mark.parametrize("tabela", AMPLIADAS)
def test_sem_o_registro_de_piloto_a_tabela_nao_sai(tabela: str) -> None:
    falta = prontidao.negacao_do_piloto(
        (tabela,), {}, prontidao.versoes_maiores(), frozenset({tabela}), HOJE
    )
    assert falta is prontidao.Falta.SEM_PRONTIDAO


@pytest.mark.parametrize("tabela", AMPLIADAS)
def test_o_registro_de_verdade_libera_a_tabela_pelo_piloto(tabela: str) -> None:
    falta = prontidao.negacao_do_piloto(
        (tabela,),
        prontidao.PRONTIDAO_DE_PILOTO,
        prontidao.versoes_maiores(),
        prontidao.tabelas_com_pessoa_decidida(),
        HOJE,
    )
    assert falta is None


@pytest.mark.parametrize("tabela", AMPLIADAS)
def test_a_versao_e_as_duas_provas_sao_as_do_piloto(tabela: str) -> None:
    registro = prontidao.PRONTIDAO_DE_PILOTO[tabela]
    assert registro.versao_maior == prontidao.versoes_maiores()[tabela]
    assert registro.qualidade is not None and registro.dicionario is not None
    assert registro.qualidade.data == HOJE
    assert prontidao.prova_publicavel(registro.qualidade.prova)
    assert prontidao.prova_publicavel(registro.dicionario.prova)


@pytest.mark.parametrize("tabela", AMPLIADAS)
def test_a_tabela_tem_regra_de_qualidade_e_nao_vira_prontidao_cheia(
    tabela: str,
) -> None:
    assert tabela in REGRAS
    assert tabela not in prontidao.PRONTIDAO
