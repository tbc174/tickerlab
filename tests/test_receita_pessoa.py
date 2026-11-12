"""Leitor do sócio pessoa física para a tela da equipe (linha 808): menor e CPF nunca saem.

Todo nome aqui é inventado. Layout do `Socios*.zip`: raiz; tipo; nome; documento; qualificação; data de
entrada; país; CPF do representante; nome do representante; qualificação do representante; faixa etária.
"""

import io
import zipfile
from collections import Counter

import pandas as pd
import pytest

from base import receita_pessoa as rp
from base.oposicao_na_tela import Opostos
from base.receita_retrato import ErroDeLayout

SEM_OPOSTOS = Opostos(frozenset(), b"k" * 32)
SEM_REP = '"***000000**";"";"00"'


def _linha(raiz, tipo, nome, qualificacao="49", faixa="5", representante=SEM_REP):
    return (
        f'"{raiz}";"{tipo}";"{nome}";"***123456**";"{qualificacao}";"20200131";"";'
        f'{representante};"{faixa}"\n'
    )


def _zip(*linhas: str) -> io.BytesIO:
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as arquivo:
        arquivo.writestr("K.SOCIOCSV", "".join(linhas).encode("latin-1"))
    memoria.seek(0)
    return memoria


def _ler(*linhas: str) -> tuple[pd.DataFrame, Counter]:
    partes = list(rp.ler_socios_pf(_zip(*linhas), SEM_OPOSTOS))
    socios = pd.concat([p.socios for p in partes], ignore_index=True)
    descartes = sum((p.descartes for p in partes), Counter())
    return socios, descartes


def test_adulto_sai_so_com_as_quatro_colunas():
    socios, descartes = _ler(_linha("11222333", "2", "FULANA EXEMPLO DA SILVA"))
    assert list(socios.columns) == [
        "cnpj_basico",
        "nome_socio",
        "qualificacao",
        "data_entrada",
    ]
    linha = socios.iloc[0]
    assert linha["cnpj_basico"] == "11222333"
    assert linha["nome_socio"] == "FULANA EXEMPLO DA SILVA"
    assert linha["qualificacao"] == "49"
    assert linha["data_entrada"] == pd.Timestamp("2020-01-31")
    assert not descartes


@pytest.mark.parametrize(
    ("faixa", "motivo"),
    [
        ("1", rp.MENOR_PELA_FAIXA),
        ("2", rp.MENOR_PELA_FAIXA),
        ("0", rp.FAIXA_DESCONHECIDA),
        ("", rp.FAIXA_DESCONHECIDA),
        ("X", rp.FAIXA_DESCONHECIDA),
    ],
)
def test_faixa_de_menor_ou_desconhecida_fica_fora(faixa, motivo):
    socios, descartes = _ler(_linha("11222333", "2", "CRIANCA EXEMPLO", faixa=faixa))
    assert socios.empty
    assert descartes == {motivo: 1}


@pytest.mark.parametrize("faixa", sorted(rp.FAIXAS_DE_ADULTO))
def test_toda_faixa_de_adulto_fica(faixa):
    socios, _ = _ler(_linha("11222333", "2", "ADULTO EXEMPLO", faixa=faixa))
    assert len(socios) == 1


@pytest.mark.parametrize(
    "representante",
    [
        '"***654321**";"";"00"',
        '"***000000**";"RESPONSAVEL EXEMPLO";"00"',
        '"***000000**";"";"35"',
    ],
)
def test_quem_tem_representante_legal_fica_fora_mesmo_com_faixa_de_adulto(
    representante,
):
    socios, descartes = _ler(
        _linha("11222333", "2", "REPRESENTADO EXEMPLO", representante=representante)
    )
    assert socios.empty
    assert descartes == {rp.COM_REPRESENTANTE: 1}


@pytest.mark.parametrize("codigo", sorted(rp.QUALIFICACOES_DE_MENOR_OU_INCAPAZ))
def test_qualificacao_de_menor_ou_incapaz_fica_fora(codigo):
    socios, descartes = _ler(
        _linha("11222333", "2", "INCAPAZ EXEMPLO", qualificacao=codigo)
    )
    assert socios.empty
    assert descartes == {rp.QUALIFICACAO_DE_MENOR: 1}


@pytest.mark.parametrize("codigo", sorted(rp.QUALIFICACOES_DE_QUEM_REPRESENTA))
def test_quem_esta_no_quadro_por_um_menor_ou_incapaz_fica_fora(codigo):
    socios, descartes = _ler(
        _linha("11222333", "2", "RESPONSAVEL EXEMPLO", qualificacao=codigo)
    )
    assert socios.empty
    assert descartes == {rp.QUALIFICACAO_DE_REPRESENTANTE: 1}


def test_as_qualificacoes_de_quem_representa_batem_com_a_tabela_da_receita():
    from base.receita_codigos import qualificacao

    nomes = {qualificacao(c) for c in rp.QUALIFICACOES_DE_QUEM_REPRESENTA}
    assert nomes == {"Curador", "Mãe", "Pai", "Tutor"}


def test_as_qualificacoes_de_menor_batem_com_a_tabela_da_receita():
    from base.receita_codigos import qualificacao

    for codigo in rp.QUALIFICACOES_DE_MENOR_OU_INCAPAZ:
        nome = (qualificacao(codigo) or "").lower()
        assert "menor" in nome or "incapaz" in nome, codigo


def test_nenhuma_qualificacao_de_menor_ou_incapaz_da_tabela_ficou_de_fora():
    import csv

    from base.receita_codigos import PASTA

    with open(PASTA / "rfb_qualificacoes.csv", encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.reader(arquivo, delimiter=";"))
    da_tabela = {
        codigo.zfill(2)
        for codigo, nome, *_ in linhas
        if "menor" in nome.lower() or "incapaz" in nome.lower()
    }
    assert da_tabela == rp.QUALIFICACOES_DE_MENOR_OU_INCAPAZ


def test_socio_empresa_e_estrangeiro_ficam_fora():
    socios, descartes = _ler(
        _linha("11222333", "1", "HOLDING DE MENTIRA LTDA", faixa="0"),
        _linha("11222333", "3", "ESTRANGEIRO EXEMPLO"),
        _linha("11222333", "2", "FULANA EXEMPLO"),
    )
    assert list(socios["nome_socio"]) == ["FULANA EXEMPLO"]
    assert descartes == {rp.NAO_E_PESSOA_FISICA: 2}


def test_cpf_escrito_no_nome_sai_e_o_documento_nunca_aparece():
    socios, _ = _ler(
        _linha("11222333", "2", "FULANO EXEMPLO ***123456**"),
        _linha("11222333", "2", "BELTRANA EXEMPLO 123.456.789-09"),
    )
    assert list(socios["nome_socio"]) == ["FULANO EXEMPLO", "BELTRANA EXEMPLO"]
    tudo = socios.astype(str).to_string()
    assert "123456" not in tudo and "***" not in tudo


def test_linha_sem_nome_fica_fora():
    socios, descartes = _ler(_linha("11222333", "2", " "))
    assert socios.empty and descartes == {rp.SEM_NOME: 1}


def test_layout_com_campo_a_mais_quebra_a_leitura():
    linha = _linha("11222333", "2", "FULANA EXEMPLO").rstrip("\n") + ';"novo"\n'
    with pytest.raises(ErroDeLayout):
        _ler(linha)
