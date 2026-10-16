"""FIDC desde 2013 e cadastro de fundos (série 3 da base de ML, PR 6; camada 1 do TickerLab Capital).

Amostras reais recortadas (`tests/arquivos/cvm/fidc/`: 3 fundos, 2 meses de 2013 e de 2019, ago/2026),
sem nenhum CPF real. Inventário de 14/10/2026: 15 a 18 tabelas conforme o ano, colunas renomeadas;
a tabela I traz até 9 documentos de cedentes (CNPJ fica, CPF sai); no cadastro, diretor fora e gestor
pessoa física sem CPF nem nome.
"""

import io
import re
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from base import fidc

PASTA = Path(__file__).parent / "arquivos" / "cvm" / "fidc"
ARQUIVOS = (
    "inf_mensal_fidc_2013.zip",
    "inf_mensal_fidc_2019.zip",
    "inf_mensal_fidc_202608.zip",
)
CPF_FICTICIO = "52998224725"  # dígitos verificadores certos, de ninguém


def _ler(nome: str) -> dict[str, pd.DataFrame]:
    return fidc.ler_informe((PASTA / nome).read_bytes())


def _linhas_brutas(nome: str, tabela: str) -> int:
    with zipfile.ZipFile(PASTA / nome) as arquivo:
        return sum(
            arquivo.read(n).decode("latin-1").count("\n") - 1
            for n in arquivo.namelist()
            if re.search(rf"_{tabela}_\d{{6}}\.csv$", n)
        )


@pytest.mark.parametrize("nome", ARQUIVOS)
def test_le_as_tabelas_do_informe_de_cada_layout(nome):
    tabelas = _ler(nome)
    assert {"tab_I", "tab_II", "tab_IV", "tab_X_1"} <= set(tabelas)
    for chave, tabela in tabelas.items():
        assert {"competencia", "cnpj_fundo"} <= set(tabela.columns), chave
        assert (
            tabela["cnpj_fundo"].str.fullmatch(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}").all()
        ), chave
        assert len(tabela) == _linhas_brutas(nome, chave), chave


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("33000167000101", "33.000.167/0001-01"),  # Petrobras
        ("7526557000100", "07.526.557/0001-00"),  # Ambev, sem o zero à esquerda
        # o CNPJ do Banco do Brasil sem os zeros ("191") também é um CPF válido (000.000.001-91):
        # na dúvida, é tratado como dado pessoal e sai
        ("191", None),
        (CPF_FICTICIO, None),  # CPF: dado pessoal, sai
        ("12345678901234", None),  # não fecha como CNPJ
        ("9", None),
        ("", None),
        (None, None),
    ],
)
def test_documento_de_empresa(valor, esperado):
    assert fidc.documento_de_empresa(valor) == esperado


def _zip_com(nome: str, texto: str) -> bytes:
    conteudo = io.BytesIO()
    with zipfile.ZipFile(conteudo, "w") as arquivo:
        arquivo.writestr(nome, texto.encode("latin-1"))
    return conteudo.getvalue()


def test_nenhum_cpf_de_cedente_entra_na_base():
    with zipfile.ZipFile(PASTA / "inf_mensal_fidc_202608.zip") as arquivo:
        nome = next(n for n in arquivo.namelist() if "_tab_I_" in n)
        texto = arquivo.read(nome).decode("latin-1")
    cabecalho, primeira, *_ = texto.splitlines()
    colunas = cabecalho.split(";")
    valores = primeira.split(";")
    posicao = next(i for i, c in enumerate(colunas) if "CPF_CNPJ_CEDENTE" in c)
    valores[posicao] = CPF_FICTICIO
    tabela = fidc.ler_informe(_zip_com(nome, f"{cabecalho}\n{';'.join(valores)}\n"))[
        "tab_I"
    ]
    documentos = tabela[[c for c in tabela.columns if "CPF" in c]]
    assert CPF_FICTICIO not in set(documentos.stack().astype(str))
    assert (
        documentos.stack()
        .dropna()
        .str.fullmatch(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
        .all()
    )


CADASTRO = (
    "TP_FUNDO;CNPJ_FUNDO;DENOM_SOCIAL;SIT;DIRETOR;PF_PJ_GESTOR;CPF_CNPJ_GESTOR;GESTOR;CNPJ_ADMIN;ADMIN\n"
    "FIDC;11.111.111/0001-11;FUNDO A;EM FUNCIONAMENTO NORMAL;FULANO DE TAL;PF;"
    f"{CPF_FICTICIO};CICLANO;22.222.222/0001-22;ADMIN A\n"
    "FIDC;33.333.333/0001-33;FUNDO B;CANCELADA;BELTRANO;PJ;44.444.444/0001-44;GESTORA B;"
    "22.222.222/0001-22;ADMIN A\n"
)


def test_cadastro_sem_diretor_e_sem_gestor_pessoa_fisica():
    tabela = fidc.ler_cadastro_de_fundos(CADASTRO.encode("latin-1"))
    assert "DIRETOR" not in tabela.columns
    pf, pj = tabela.iloc[0], tabela.iloc[1]
    assert (
        pf["PF_PJ_GESTOR"] == "PF"
        and pd.isna(pf["CPF_CNPJ_GESTOR"])
        and pd.isna(pf["GESTOR"])
    )
    assert pj["CPF_CNPJ_GESTOR"] == "44.444.444/0001-44" and pj["GESTOR"] == "GESTORA B"
    assert set(tabela["CNPJ_FUNDO"]) == {
        "11.111.111/0001-11",
        "33.333.333/0001-33",
    }  # o cancelado fica


def test_historico_do_cadastro_sem_diretor_responsavel():
    conteudo = io.BytesIO()
    with zipfile.ZipFile(conteudo, "w") as arquivo:
        arquivo.writestr(
            "cad_fi_hist_admin.csv",
            "CNPJ_FUNDO;DT_REG;CNPJ_ADMIN;ADMIN;DT_INI_ADMIN;DT_FIM_ADMIN\n"
            "11.111.111/0001-11;2010-01-01;22.222.222/0001-22;ADMIN A;2010-01-01;\n",
        )
        arquivo.writestr(
            "cad_fi_hist_diretor_resp.csv",
            "CNPJ_FUNDO;DT_REG;DIRETOR;DT_INI_DIRETOR;DT_FIM_DIRETOR\n"
            "11.111.111/0001-11;2010-01-01;FULANO DE TAL;2010-01-01;\n",
        )
    tabelas = fidc.ler_historico_do_cadastro(conteudo.getvalue())
    assert set(tabelas) == {"admin"}


def test_informe_vale_45_dias_depois_da_competencia():
    tabela = pd.DataFrame({"competencia": pd.to_datetime(["2026-08-31"])})
    assert fidc.disponivel_em(tabela).tolist() == [pd.Timestamp("2026-10-15")]


def test_cnpj_alfanumerico_atravessa_fidc():
    """Com letra é CNPJ (nunca CPF): fica, formatado, se o DV confere."""
    assert fidc.documento_de_empresa("12.ABC.345/01DE-35") == "12.ABC.345/01DE-35"
    assert fidc.documento_de_empresa("12abc34501de35") == "12.ABC.345/01DE-35"
    assert fidc.documento_de_empresa("12ABC34501DE36") is None


def test_meses_com_cabecalhos_diferentes_nao_deixam_cnpj_do_fundo_vazio():
    """Arquivo anual juntando cabeçalho novo (CNPJ_FUNDO_CLASSE) e antigo (CNPJ_FUNDO)."""
    conteudo = io.BytesIO()
    with zipfile.ZipFile(conteudo, "w") as arquivo:
        arquivo.writestr(
            "inf_mensal_fidc_tab_I_202001.csv",
            "CNPJ_FUNDO;DT_COMPTC;VL\n11.222.333/0001-81;2020-01-31;1\n".encode(
                "latin-1"
            ),
        )
        arquivo.writestr(
            "inf_mensal_fidc_tab_I_202002.csv",
            "CNPJ_FUNDO_CLASSE;DT_COMPTC;VL\n44.555.666/0001-81 ;2020-02-29;2\n".encode(
                "latin-1"
            ),
        )
    tabela = fidc.ler_informe(conteudo.getvalue())["tab_I"]
    assert tabela["cnpj_fundo"].notna().all()
    assert list(tabela["cnpj_fundo"]) == ["11.222.333/0001-81", "44.555.666/0001-81"]
    assert not {"CNPJ_FUNDO", "CNPJ_FUNDO_CLASSE"} & set(tabela.columns)
