"""Quem tem o contato da própria pessoa (PR 3 da ADR 0128, Emenda 4): MEI pelo Simples, EIRELI e o quadro de
um sócio só. Arquivos de mentira, sem internet; todo nome aqui é inventado."""

import io
import zipfile

import numpy as np
import pandas as pd
import pytest

from base import cnpj
from base import receita_contato_de_pessoa as rcp
from base.receita_retrato import ErroDeLayout


def _zip(membro: str, texto: str) -> io.BytesIO:
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as arquivo:
        arquivo.writestr(membro, texto.encode("latin-1"))
    memoria.seek(0)
    return memoria


def _textos(numeros: np.ndarray) -> list[str]:
    """As raízes de volta em texto, para comparar com o que o teste escreveu."""
    todas = pd.Series(
        ["11222333", "22333444", "33444555", "44555666", "55666777", "66777888"]
    )
    return sorted(
        todas[cnpj.contem(cnpj.ordenados(numeros), cnpj.raizes_em_numeros(todas))]
    )


# --------------------------------------------------------------------------- MEI pelo Simples


def _simples(raiz: str, mei: str) -> str:
    return f'"{raiz}";"S";"20200101";"00000000";"{mei}";"20200101";"00000000"\n'


def test_mei_do_simples_e_so_quem_tem_a_opcao_atual_pelo_mei():
    arquivo = _zip(
        "F.K.SIMPLES",
        _simples("11222333", "S")
        + _simples("22333444", "N")
        + _simples("33444555", " S "),
    )
    assert _textos(rcp.raizes_do_mei(arquivo)) == ["11222333", "33444555"]


def test_simples_com_outro_layout_falha_em_vez_de_cortar_nada():
    with pytest.raises(ErroDeLayout):
        rcp.raizes_do_mei(_zip("F.K.SIMPLES", '"11222333";"S";"S"\n'))


# --------------------------------------------------------------------------- EIRELI pela natureza


def _empresa(raiz: str, natureza: str) -> str:
    return f'"{raiz}";"EMPRESA DE MENTIRA";"{natureza}";"49";"0";"01";""\n'


def test_eireli_e_as_duas_naturezas_da_antiga_eireli():
    texto = (
        _empresa("11222333", "2305")
        + _empresa("22333444", "2313")
        + _empresa("33444555", "2062")
    )
    texto += _empresa(
        "44555666", "230-5"
    )  # com pontuação, como o código aparece escrito
    assert _textos(rcp.raizes_de_eireli(_zip("K.EMPRECSV", texto))) == [
        "11222333",
        "22333444",
        "44555666",
    ]


# --------------------------------------------------------------------------- quadro de um sócio só


def _socio(raiz: str, tipo: str, nome: str, documento: str = "***123456**") -> str:
    return f'"{raiz}";"{tipo}";"{nome}";"{documento}";"49";"20200131";"";"***000000**";"";"00";"5"\n'


def _unipessoais(*arquivos: str) -> list[str]:
    quadros = rcp.QuadrosDeSocios()
    for texto in arquivos:
        quadros.anotar(_zip("K.SOCIOCSV", texto))
    return _textos(quadros.unipessoais())


def test_quadro_de_um_socio_pessoa_fisica_e_unipessoal():
    assert _unipessoais(_socio("11222333", "2", "FULANA EXEMPLO")) == ["11222333"]


def test_socio_unico_do_exterior_tambem_entra_porque_pode_ser_pessoa():
    """Na dúvida entra no corte (Diretoria, 18/11/2026): o tipo 3 da Receita é o sócio do exterior, pessoa ou não."""
    assert _unipessoais(_socio("11222333", "3", "FOREIGN EXAMPLE")) == ["11222333"]


def test_socio_unico_que_e_empresa_nao_e_unipessoal_de_pessoa():
    assert (
        _unipessoais(
            _socio("11222333", "1", "HOLDING DE MENTIRA LTDA", "11222333000181")
        )
        == []
    )


def test_dois_socios_nao_e_unipessoal():
    texto = _socio("11222333", "2", "FULANA EXEMPLO") + _socio(
        "11222333", "2", "BELTRANO EXEMPLO", "***654321**"
    )
    assert _unipessoais(texto) == []


def test_pessoa_com_um_socio_empresa_nao_e_unipessoal():
    texto = _socio("11222333", "2", "FULANA EXEMPLO") + _socio(
        "11222333", "1", "HOLDING LTDA", "22333444000181"
    )
    assert _unipessoais(texto) == []


def test_a_mesma_linha_repetida_conta_uma_vez():
    """Linha repetida no arquivo não faz de uma pessoa duas: na dúvida, a empresa entra no corte."""
    linha = _socio("11222333", "2", "FULANA EXEMPLO")
    assert _unipessoais(linha + linha) == ["11222333"]


def test_o_quadro_e_contado_em_todos_os_arquivos_do_mes():
    """Uma raiz partida entre dois `Socios*.zip` tem os sócios dos dois somados."""
    primeiro = _socio("11222333", "2", "FULANA EXEMPLO") + _socio(
        "22333444", "2", "CICRANA EXEMPLO"
    )
    segundo = _socio("11222333", "2", "BELTRANO EXEMPLO", "***654321**")
    assert _unipessoais(primeiro, segundo) == ["22333444"]


def test_sem_arquivo_anotado_nenhuma_raiz():
    assert len(rcp.QuadrosDeSocios().unipessoais()) == 0


def test_socios_com_outro_layout_falha():
    quadros = rcp.QuadrosDeSocios()
    with pytest.raises(ErroDeLayout):
        quadros.anotar(_zip("K.SOCIOCSV", '"11222333";"2";"FULANA"\n'))
