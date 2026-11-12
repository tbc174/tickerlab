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
from base.receita_retrato import ErroDeLayout

CHAVE = b"k" * 32
SEM_OPOSTOS = Opostos(frozenset(), CHAVE)
CPF = (
    "52998224725"  # número de exemplo que fecha nos dígitos; não é de ninguém conhecido
)


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
    assert (
        linha.pop("id_pessoa") == ""
    )  # razão sem CPF: sem id, a pessoa não tem como se opor
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
        "FULANA EXEMPLO 529.982.247-25",
        "FULANA EXEMPLO 529982247-25",
        "FULANA EXEMPLO 529 982 247 25",
        "FULANA EXEMPLO CPF 529/982/247/25",
        f"{CPF} FULANA EXEMPLO",
        "FULANA EXEMPLO ***982247**",
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
        "52998224725",
        "529.982.247-25",
        "***982247**",
        "***.982.247-**",
        "529 982 247 25",
        "CPF 529/982/247/25",
        "529.982.247 25",
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
