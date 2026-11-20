"""Lote 1 de tabelas ligadas pelo CNPJ no registro de piloto (linha 978; ADR 0108, Emenda 2, D11).

São tabelas que já chegam ao servidor (degrau 6 do recorte, mais `pgfn_divida` e `ifdata_valores`) e só não abriam
na API e no conector por falta do registro de piloto: a prova 7 (placar de qualidade de 18/11/2026, tirado do acervo
de casa) e o dicionário escrito. A conferência cruzada continua dispensada (por isso o aviso "Dado de piloto" em todo
bloco servido). O que este arquivo cobra é o **registro de verdade**; a regra do portão, em `test_prontidao.py`.
"""

from datetime import date

import pytest

from base import prontidao
from base.dicionario import TABELAS
from base.qualidade_automatica import REGRAS

HOJE = date(2026, 11, 18)
DO_LOTE_1 = (
    "aneel_indicadores_comerciais",
    "ans_idss",
    "fii_administradores",
    "fii_informe_mensal",
    "fip_informe",
    "ifdata_valores",
    "pgfn_divida",
)


@pytest.mark.parametrize("tabela", DO_LOTE_1)
def test_o_registro_de_verdade_libera_a_tabela_pelo_piloto(tabela: str) -> None:
    falta = prontidao.negacao_do_piloto(
        (tabela,),
        prontidao.PRONTIDAO_DE_PILOTO,
        prontidao.versoes_maiores(),
        prontidao.tabelas_com_pessoa_decidida(),
        HOJE,
    )
    assert falta is None


@pytest.mark.parametrize("tabela", DO_LOTE_1)
def test_a_versao_e_as_duas_provas_sao_as_do_piloto(tabela: str) -> None:
    registro = prontidao.PRONTIDAO_DE_PILOTO[tabela]
    assert registro.versao_maior == prontidao.versoes_maiores()[tabela]
    assert registro.qualidade is not None and registro.dicionario is not None
    assert registro.qualidade.data == HOJE
    assert registro.qualidade.prova == "placar-qualidade-2026-11-18"
    assert registro.dicionario.prova == "dicionario-escrito-2026-11-18"
    assert prontidao.prova_publicavel(registro.qualidade.prova)
    assert prontidao.prova_publicavel(registro.dicionario.prova)


@pytest.mark.parametrize("tabela", DO_LOTE_1)
def test_a_tabela_tem_regra_de_qualidade_e_nao_vira_prontidao_cheia(
    tabela: str,
) -> None:
    assert tabela in REGRAS
    assert tabela not in prontidao.PRONTIDAO
    assert not TABELAS[tabela].pessoa
