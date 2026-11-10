"""Leitor de `Empresas` e vista de estabelecimentos sem pessoa (linha 584). Arquivos de mentira, sem internet."""

import io
import zipfile

import pandas as pd

from base import receita_empresas as re_

EMPRESAS = (
    '"33000167";"PETROLEO DE MENTIRA S.A.";"2046";"10";"1000,00";"05";""\n'
    '"12ABC345";"NOVA; COM PONTO E VIRGULA LTDA";"2062";"49";"0,00";"01";""\n'
    '"11222333";"FULANO DE TAL";"2135";"50";"5000,00";"01";""\n'
    '"44444444";"BELTRANO DA SILVA";"4090";"50";"0,00";"00";""\n'
    '"55555555";"MEI COM NATUREZA DE LTDA 52998224725";"2062";"49";"0,00";"01";""\n'
)


def _zip(texto: str) -> io.BytesIO:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        arquivo.writestr("K3241.EMPRECSV", texto.encode("latin-1"))
    saida.seek(0)
    return saida


def _empresas() -> pd.DataFrame:
    return pd.concat(re_.ler_empresas_pj(_zip(EMPRESAS)), ignore_index=True)


def test_leitor_traz_razao_natureza_e_porte_so_de_pj():
    tabela = _empresas().set_index("cnpj_basico")
    assert set(tabela.index) == {"33000167", "12ABC345", "55555555"}
    assert tabela.loc["33000167", "porte"] == "demais"
    assert tabela.loc["12ABC345", "porte"] == "micro"
    assert tabela.loc["12ABC345", "razao_social"] == "NOVA; COM PONTO E VIRGULA LTDA"


def test_empresario_individual_e_grupo_4_nem_saem_do_leitor():
    texto = _empresas().to_csv()
    assert "FULANO" not in texto and "BELTRANO" not in texto
    assert "11222333" not in texto and "44444444" not in texto


def test_cpf_no_texto_da_razao_social_sai():
    assert "52998224725" not in _empresas().to_csv()


def test_vista_deixa_de_fora_mei_e_raiz_desconhecida():
    estabelecimentos = pd.DataFrame(
        {
            "cnpj": [
                "33000167000101",
                "12ABC345000199",
                "55555555000100",
                "99999999000100",
                "11222333000100",
            ],
            "cnpj_basico": ["33000167", "12ABC345", "55555555", "99999999", "11222333"],
            "matriz": [True] * 5,
            "situacao_cadastral": ["02"] * 5,
            "data_inicio_atividade": pd.to_datetime(["1953-10-03"] * 5),
            "cnae_principal": ["0600001"] * 5,
            "uf": ["RJ"] * 5,
            "municipio": ["6001"] * 5,
            "logradouro": ["RUA X"] * 5,
            "cep": ["20000000"] * 5,
        }
    )
    simples = pd.DataFrame(
        {"cnpj_basico": ["55555555", "12ABC345"], "optante_mei": [True, False]}
    )
    vista = re_.estabelecimentos_sem_pessoa(estabelecimentos, _empresas(), simples)
    assert list(vista["cnpj_basico"]) == ["33000167", "12ABC345"]
    assert list(vista.columns) == list(re_.COLUNAS_DA_VISTA)
    assert "logradouro" not in vista.columns and "cep" not in vista.columns
