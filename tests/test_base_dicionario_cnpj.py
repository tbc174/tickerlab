"""Tabelas do CNPJ aberto no dicionário (fila 119; ADR 0106): as colunas registradas são as que a carga
mensal grava, o sócio pessoa física é só o `id_pessoa` e a tabela com dado de pessoa fica marcada."""

import pandas as pd
import pytest

from base import receita_diff as rd
from base import receita_retrato as rr
from base.dicionario import TABELAS
from scripts.carga_receita_mes import CHAVES
from tests.test_base_receita_retrato import _estab, _simples, _socio, _zip

CHAVE_DE_PESSOAS = b"k" * 32
TABELAS_DO_CNPJ = ("estabelecimentos", "simples", "qsa")


def _vigentes() -> dict[str, pd.DataFrame]:
    """As três tabelas vigentes como a carga as monta, com uma linha de mentira cada."""
    estabelecimentos = next(rr.ler_estabelecimentos(_zip(_estab())))
    simples = next(rr.ler_simples(_zip(_simples("33000167", mei="S"))))
    texto = _socio("33000167", "1", "HOLDING SA", "11222333") + _socio(
        "33000167", "2", "MARIA DA SILVA", "***123456**"
    )
    qsa = rd.qsa_para_diff(next(rr.ler_qsa([_zip(texto)])), CHAVE_DE_PESSOAS)
    return {"estabelecimentos": estabelecimentos, "simples": simples, "qsa": qsa}


@pytest.mark.parametrize("nome", TABELAS_DO_CNPJ)
def test_dicionario_tem_as_colunas_que_a_carga_grava(nome):
    vigente = _vigentes()[nome]
    assert set(TABELAS[f"cnpj_{nome}"].colunas) == set(vigente.columns)
    depois = vigente.copy()
    coluna = next(c for c in depois.columns if c not in CHAVES[nome])
    depois[coluna] = "mudou"
    mudancas = rd.diff(vigente, depois, CHAVES[nome], "2026-11")
    assert set(TABELAS[f"cnpj_{nome}_mudancas"].colunas) == set(mudancas.columns)


@pytest.mark.parametrize("nome", TABELAS_DO_CNPJ)
def test_tabelas_do_cnpj_sao_vendaveis_com_atribuicao(nome):
    for tabela in (TABELAS[f"cnpj_{nome}"], TABELAS[f"cnpj_{nome}_mudancas"]):
        assert tabela.familia_da_fonte == "rfb-cnpj"
        assert "CC BY" in tabela.ressalva_de_revenda
        assert "legítimo interesse" in tabela.descricao


def test_nome_e_cpf_do_socio_nao_estao_no_dicionario():
    """O nome fica no esquema `pessoas` (acervo restrito, atrás do portão); aqui só o `id_pessoa`."""
    for nome in ("cnpj_qsa", "cnpj_qsa_mudancas"):
        colunas = " ".join(TABELAS[nome].colunas)
        assert "id_pessoa" in colunas
        assert not {"nome", "nome_socio", "cpf", "cpf_mascarado"} & set(
            TABELAS[nome].colunas
        )


def test_tabelas_com_dado_de_pessoa_estao_marcadas():
    """`cnpj_qsa` tem o pseudônimo do sócio; `cnpj_estabelecimentos` leva o endereço inteiro do
    empresário individual e do MEI até o leitor de empresas existir (fila: leitor `Empresas*`)."""
    com_pessoa = {n for n, t in TABELAS.items() if t.pessoa and n.startswith("cnpj_")}
    assert com_pessoa == {
        "cnpj_qsa",
        "cnpj_qsa_mudancas",
        "cnpj_estabelecimentos",
        "cnpj_estabelecimentos_mudancas",
    }


def test_estabelecimentos_nao_guarda_contato_nem_nome_fantasia():
    colunas = set(TABELAS["cnpj_estabelecimentos"].colunas)
    assert not {"telefone", "ddd", "fax", "email", "nome_fantasia"} & colunas
