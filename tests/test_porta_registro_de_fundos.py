"""O registro de fundos da CVM 175 na porta (linha 810, PR 1): é o cadastro em dia dos FIPs.

O `cadastro_de_fundos` antigo (`cad_fi`) quase não traz mais fundo de participação; o
`registro_fundo` da CVM 175 traz todos. A porta o serve como `registro_de_fundos`, sem gestor
pessoa física (marca PF fica, CPF e nome saem) e com `aconteceu_em` = dia do registro na CVM.
Dados de mentira: CNPJs inventados e um CPF de ninguém.
"""

import io
import zipfile
from datetime import date

import pandas as pd

from base import fidc
from base.dicionario import TABELAS
from base.porta.duckdb import ARQUIVOS, conectar

TABELA = "registro_de_fundos"
CPF_FICTICIO = "52998224725"  # dígitos verificadores certos, de ninguém
CABECALHO = (
    "ID_Registro_Fundo;CNPJ_Fundo;Codigo_CVM;Data_Registro;Tipo_Fundo;Denominacao_Social;"
    "Data_Cancelamento;Situacao;Diretor;CNPJ_Administrador;Administrador;Tipo_Pessoa_Gestor;"
    "CPF_CNPJ_Gestor;Gestor\n"
)
LINHAS = (
    "1;11111111000111;101;2021-05-10;FIP;FIP A;;Em Funcionamento Normal;FULANO;"
    "22222222000122;ADMIN A;PJ;44444444000144;GESTORA B\n"
    f"2;33333333000133;102;2019-02-01;FIP;FIP B;2024-01-31;Cancelado;BELTRANO;"
    f"22222222000122;ADMIN A;PF;{CPF_FICTICIO};CICLANO\n"
    "3;55555555000155;103;2020-07-15;FII;FII C;;Em Funcionamento Normal;;"
    "22222222000122;ADMIN A;PJ;44444444000144;GESTORA B\n"
)


def _zip_da_cvm() -> bytes:
    conteudo = io.BytesIO()
    with zipfile.ZipFile(conteudo, "w") as arquivo:
        arquivo.writestr("registro_fundo.csv", (CABECALHO + LINHAS).encode("latin-1"))
    return conteudo.getvalue()


def test_registro_sem_diretor_e_sem_gestor_pessoa_fisica():
    """Os nomes da CVM 175 (`Tipo_Pessoa_Gestor`, `CPF_CNPJ_Gestor`, `Gestor`, `Diretor`) também
    passam pelo filtro de pessoa: o CPF e o nome do gestor PF saem, a marca PF fica."""
    tabela = fidc.ler_registro_de_fundos(_zip_da_cvm())["registro_fundo"]
    assert "Diretor" not in tabela.columns
    pf = tabela[tabela["Tipo_Pessoa_Gestor"] == "PF"].iloc[0]
    assert pd.isna(pf["CPF_CNPJ_Gestor"]) and pd.isna(pf["Gestor"])
    assert CPF_FICTICIO not in tabela.to_csv()
    pj = tabela[tabela["ID_Registro_Fundo"] == "1"].iloc[0]
    assert pj["CPF_CNPJ_Gestor"] == "44444444000144" and pj["Gestor"] == "GESTORA B"


def test_porta_serve_o_registro_com_a_data_do_registro(tmp_path):
    """A view lê o Parquet como a carga grava (tudo texto), dá `aconteceu_em` como dia e deixa
    separar o FIP ativo do cancelado."""
    tabela = fidc.ler_registro_de_fundos(_zip_da_cvm())["registro_fundo"]
    arquivo = tmp_path / ARQUIVOS[TABELA]
    arquivo.parent.mkdir(parents=True)
    tabela.to_parquet(arquivo, index=False)
    with conectar(
        tmp_path,
        tabelas={TABELA: TABELAS[TABELA]},
        arquivos={TABELA: ARQUIVOS[TABELA]},
    ) as con:
        fips = con.execute(
            f"SELECT CNPJ_Fundo, Situacao, aconteceu_em, CPF_CNPJ_Gestor FROM {TABELA} "
            "WHERE Tipo_Fundo = 'FIP' ORDER BY CNPJ_Fundo"
        ).fetchall()
    assert fips == [
        (
            "11111111000111",
            "Em Funcionamento Normal",
            date(2021, 5, 10),
            "44444444000144",
        ),
        ("33333333000133", "Cancelado", date(2019, 2, 1), None),
    ]


def test_registro_vem_do_arquivo_da_cvm_175():
    """O nome na porta é o do dicionário; o arquivo é o que a carga da CVM grava."""
    assert ARQUIVOS[TABELA] == "fidc/cadastro/registro_fundo.parquet"
    assert "FIP" in TABELAS[TABELA].descricao
