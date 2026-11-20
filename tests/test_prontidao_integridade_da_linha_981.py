"""A cópia reduzida só-PJ de uma tabela de pessoa sai pelo piloto (linha 981; ADR 0108, Emenda 3, D11.4).

Frase aprovada pelo Tiago em 19/11/2026: "tabela marcada com pessoa só sai pelo piloto quando o servidor guarda apenas
a cópia reduzida só-PJ, conferida por máquina (conferir_cadastros), e a resposta serve só a linha com marca de pessoa
falsa". Vale para a CGU (CEIS, CNEP, CEPIM e leniência), os embargos do IBAMA e a Lista Suja do MTE; a tabela inteira
(com pessoa) continua fechada, e qualquer outra tabela de pessoa também.
"""

from datetime import date
from pathlib import Path

import duckdb
import pytest

from base import prontidao, recorte_dos_cadastros
from base.dicionario import TABELAS
from base.porta import duckdb as porta_duckdb

HOJE = date(2026, 11, 19)
DA_INTEGRIDADE = ("sancoes_cgu", "ibama_embargos", "mte_lista_suja")


def test_a_lista_da_copia_reduzida_e_so_de_cadastro_que_o_recorte_confere() -> None:
    assert frozenset(DA_INTEGRIDADE) == prontidao.COPIA_REDUZIDA_SO_PJ
    assert set(recorte_dos_cadastros.CADASTROS) >= prontidao.COPIA_REDUZIDA_SO_PJ
    for nome in prontidao.COPIA_REDUZIDA_SO_PJ:
        assert nome in recorte_dos_cadastros.COLUNAS


@pytest.mark.parametrize("tabela", DA_INTEGRIDADE)
def test_a_tabela_continua_marcada_com_pessoa_e_tem_a_marca_por_linha(
    tabela: str,
) -> None:
    contrato = TABELAS[tabela]
    assert contrato.pessoa  # a tabela inteira segue sendo de pessoa
    assert contrato.linhas_de_pessoa == "trata_como_pessoa"
    assert contrato.linhas_de_pessoa in contrato.colunas


@pytest.mark.parametrize("tabela", DA_INTEGRIDADE)
def test_so_a_copia_reduzida_com_a_marca_por_linha_conta_como_decidida(
    tabela: str,
) -> None:
    colunas = TABELAS[tabela].colunas
    assert prontidao.pessoa_decidida(
        tabela, pessoa=True, colunas=colunas, linhas_de_pessoa="trata_como_pessoa"
    )
    # sem a marca por linha a porta não separa a pessoa: continua fechada, como no texto antigo
    assert not prontidao.pessoa_decidida(
        tabela, pessoa=True, colunas=colunas, linhas_de_pessoa=""
    )


def test_tabela_de_pessoa_fora_da_lista_continua_fechada_mesmo_com_a_marca() -> None:
    assert not prontidao.pessoa_decidida(
        "susep_cadastro",
        pessoa=True,
        colunas=("cnpj", "trata_como_pessoa"),
        linhas_de_pessoa="trata_como_pessoa",
    )
    for nome in ("ans_cadastro", "susep_cadastro", "gleif_ponte", "cnpj_qsa"):
        assert nome not in prontidao.tabelas_com_pessoa_decidida()


@pytest.mark.parametrize("tabela", DA_INTEGRIDADE)
def test_a_tabela_esta_entre_as_de_pessoa_decidida(tabela: str) -> None:
    assert tabela in prontidao.tabelas_com_pessoa_decidida()


@pytest.mark.parametrize("tabela", DA_INTEGRIDADE)
def test_sem_o_registro_de_piloto_a_tabela_nao_sai(tabela: str) -> None:
    """A marca decidida não basta: sem as duas provas a negação é a de sempre."""
    falta = prontidao.negacao_do_piloto(
        (tabela,),
        {},
        prontidao.versoes_maiores(),
        frozenset({tabela}),
        HOJE,
    )
    assert falta is prontidao.Falta.SEM_PRONTIDAO


def test_so_as_tres_tabelas_de_pessoa_ficam_decididas() -> None:
    """Toda tabela marcada com pessoa que sai do inventário de fechadas é uma das três."""
    de_pessoa_e_decididas = {
        nome for nome in prontidao.tabelas_com_pessoa_decidida() if TABELAS[nome].pessoa
    }
    assert de_pessoa_e_decididas == set(DA_INTEGRIDADE)


@pytest.mark.parametrize("tabela", DA_INTEGRIDADE)
def test_sem_a_marca_por_linha_a_tabela_inteira_volta_a_ficar_fechada(
    tabela: str,
) -> None:
    sem_a_marca = prontidao.pessoa_decidida(
        tabela, pessoa=True, colunas=TABELAS[tabela].colunas, linhas_de_pessoa=""
    )
    assert sem_a_marca is False


@pytest.mark.parametrize("tabela", DA_INTEGRIDADE)
def test_a_porta_so_serve_a_linha_com_a_marca_de_pessoa_falsa(
    tabela: str, tmp_path: Path
) -> None:
    """A linha com a marca verdadeira (ou vazia: na dúvida é pessoa) nunca sai pela porta."""
    colunas = TABELAS[tabela].colunas
    select = porta_duckdb._sem_as_linhas_de_pessoa(
        "SELECT * FROM t", TABELAS[tabela], list(colunas)
    )
    con = duckdb.connect()
    con.execute("CREATE TABLE t (id VARCHAR, trata_como_pessoa BOOLEAN)")
    con.execute(
        "INSERT INTO t VALUES ('empresa', false), ('pessoa', true), ('duvida', NULL)"
    )
    assert [linha[0] for linha in con.execute(select).fetchall()] == ["empresa"]
    sem_a_coluna = porta_duckdb._sem_as_linhas_de_pessoa(
        "SELECT * FROM t", TABELAS[tabela], ["id"]
    )
    assert con.execute(sem_a_coluna).fetchall() == []


@pytest.mark.parametrize("tabela", DA_INTEGRIDADE)
def test_o_registro_de_verdade_libera_a_tabela_pelo_piloto(tabela: str) -> None:
    falta = prontidao.negacao_do_piloto(
        (tabela,),
        prontidao.PRONTIDAO_DE_PILOTO,
        prontidao.versoes_maiores(),
        prontidao.tabelas_com_pessoa_decidida(),
        HOJE,
    )
    assert falta is None


@pytest.mark.parametrize("tabela", DA_INTEGRIDADE)
def test_a_versao_e_as_duas_provas_sao_as_do_piloto(tabela: str) -> None:
    registro = prontidao.PRONTIDAO_DE_PILOTO[tabela]
    assert registro.versao_maior == prontidao.versoes_maiores()[tabela]
    assert registro.qualidade is not None and registro.dicionario is not None
    assert registro.qualidade.data == HOJE
    assert prontidao.prova_publicavel(registro.qualidade.prova)
    assert prontidao.prova_publicavel(registro.dicionario.prova)


@pytest.mark.parametrize("tabela", DA_INTEGRIDADE)
def test_a_tabela_inteira_de_pessoa_nao_vira_prontidao_cheia(tabela: str) -> None:
    assert tabela not in prontidao.PRONTIDAO
