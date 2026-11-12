"""Leitor do titular do empresário individual e do MEI para a tela da equipe (linha 808, PR 4).

Riscos que estes testes pegam: o CPF do dono ficar no nome (a razão social do empresário individual vem
com ele), sociedade entrar como se fosse pessoa e nome vazio ou só de números sair. Todo nome e CPF aqui é
inventado.
"""

import io
import zipfile
from collections import Counter

import pandas as pd
import pytest

from base import receita_individuais as ri
from base.oposicao_na_tela import Opostos
from base.pessoas import chave as chaves
from base.pessoas.chave import id_da_raiz
from base.receita_contato import RaizesDeIndividual
from base.receita_retrato import ErroDeLayout
from tests.ajudantes_de_cpf import CPF_DE_TESTE, formatado, meio, no_formato

CHAVE = b"k" * 32
SEM_OPOSTOS = Opostos(frozenset(), CHAVE)
CPF = CPF_DE_TESTE  # inventado, montado na hora (tests/ajudantes_de_cpf.py); não é de ninguém


def _linha(raiz="11222333", razao="FULANA EXEMPLO", natureza="2135") -> str:
    return f'"{raiz}";"{razao}";"{natureza}";"50";"0";"01";""\n'


def _zip(*linhas: str) -> io.BytesIO:
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as arquivo:
        arquivo.writestr("K.EMPRECSV", "".join(linhas).encode("latin-1"))
    memoria.seek(0)
    return memoria


def _ler(*linhas: str) -> tuple[pd.DataFrame, Counter]:
    partes = list(ri.ler_individuais(_zip(*linhas), SEM_OPOSTOS, set()))
    tabela = pd.concat([p.individuais for p in partes], ignore_index=True)
    return tabela, sum((p.descartes for p in partes), Counter())


def test_individual_sai_com_a_raiz_e_o_nome_e_nada_mais():
    tabela, descartes = _ler(_linha())
    assert list(tabela.columns) == list(ri.COLUNAS)
    linha = tabela.iloc[0].to_dict()
    # razão sem CPF: o id vem da raiz do CNPJ, para a oposição achar a linha (P1 da revisão cruzada)
    assert linha.pop("id_pessoa") == id_da_raiz("11222333", SEM_OPOSTOS.chave)
    assert linha == {"cnpj_basico": "11222333", "titular": "FULANA EXEMPLO"}
    assert not descartes


@pytest.mark.parametrize("natureza", ["2062", "2054", "2305", "4014", "1015", ""])
def test_so_o_empresario_individual_sai(natureza):
    tabela, descartes = _ler(_linha(natureza=natureza), _linha(raiz="22333444"))
    assert list(tabela["cnpj_basico"]) == ["22333444"]
    assert descartes == {ri.NAO_E_INDIVIDUAL: 1}


@pytest.mark.parametrize(
    "razao",
    [
        f"FULANA EXEMPLO {CPF}",
        f"FULANA EXEMPLO {formatado(CPF)}",
        f"FULANA EXEMPLO {no_formato(CPF, 'ddddddddd-dd')}",
        f"FULANA EXEMPLO {no_formato(CPF, 'ddd ddd ddd dd')}",
        f"FULANA EXEMPLO CPF {no_formato(CPF, 'ddd/ddd/ddd/dd')}",
        f"{CPF} FULANA EXEMPLO",
        f"FULANA EXEMPLO ***{meio(CPF)}**",
    ],
)
def test_cpf_no_nome_sai_em_qualquer_formato(razao):
    tabela, _ = _ler(_linha(razao=razao))
    assert tabela.loc[0, "titular"] == "FULANA EXEMPLO"
    assert "529" not in tabela.to_csv() and "982" not in tabela.to_csv()


def test_numero_que_nao_e_cpf_fica_no_nome():
    tabela, _ = _ler(_linha(razao="LOJA 24 HORAS DE EXEMPLO 2023"))
    assert tabela.loc[0, "titular"] == "LOJA 24 HORAS DE EXEMPLO 2023"


@pytest.mark.parametrize("razao", [CPF, "", "   ", "12 34"])
def test_nome_que_sobra_vazio_ou_so_de_numeros_nao_sai(razao):
    tabela, descartes = _ler(_linha(razao=razao), _linha(raiz="22333444"))
    assert list(tabela["cnpj_basico"]) == ["22333444"]
    assert descartes == {ri.TITULAR_SEM_NOME: 1}


def test_cnpj_com_letras_sai_em_maiusculas():
    tabela, _ = _ler(_linha(raiz="1a2b3c4d"))
    assert tabela.loc[0, "cnpj_basico"] == "1A2B3C4D"


@pytest.mark.parametrize(
    "escrito",
    [
        CPF,
        formatado(CPF),
        f"***{meio(CPF)}**",
        f"***.{no_formato(meio(CPF), 'ddd.ddd')}-**",
        no_formato(CPF, "ddd ddd ddd dd"),
        f"CPF {no_formato(CPF, 'ddd/ddd/ddd/dd')}",
        no_formato(CPF, "ddd.ddd.ddd dd"),
    ],
)
def test_oposto_sai_com_o_cpf_escrito_em_qualquer_formato(escrito):
    primeiro, ultimo = chaves.primeiro_e_ultimo("FULANA EXEMPLO")
    opostos = Opostos(
        frozenset({chaves.id_pessoa(CPF, primeiro, ultimo, CHAVE)}), CHAVE
    )
    tiradas: set[str] = set()
    partes = list(
        ri.ler_individuais(
            _zip(_linha(razao=f"FULANA EXEMPLO {escrito}")), opostos, tiradas
        )
    )
    assert partes[0].individuais.empty and tiradas == {"11222333"}
    assert partes[0].descartes[ri.OPOSTO] == 1


def test_layout_com_campo_a_mais_quebra_a_leitura():
    with pytest.raises(ErroDeLayout):
        list(
            ri.ler_individuais(
                _zip(_linha().rstrip("\n") + ';"X"\n'), SEM_OPOSTOS, set()
            )
        )


def test_toda_raiz_de_individual_vai_para_o_contato_cortar_o_endereco_ate_a_sem_nome():
    raizes = RaizesDeIndividual()
    sem_nome = _linha(raiz="44555666", razao="12345")
    list(ri.ler_individuais(_zip(_linha(), sem_nome), SEM_OPOSTOS, set(), raizes))
    achadas = raizes.contem(pd.Series(["11222333", "44555666", "99999999"]))
    assert achadas.tolist() == [True, True, False]
