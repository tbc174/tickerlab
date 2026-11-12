"""O titular do empresário individual e do MEI no leitor do acervo de pessoa (linha 808, PR do titular).

Todo nome aqui é inventado. O arquivo `individuais/<xx>.parquet` traz a raiz, o nome do titular, o pseudônimo
(`id_pessoa`, que nunca sai) e o mês do retrato.
"""

from pathlib import Path

import pandas as pd
import pytest

from src.analista import pessoa
from tests import test_analista_pessoa as acervo_de_mentira

EMPRESA = acervo_de_mentira.EMPRESA
MES = acervo_de_mentira.MES
INDIVIDUAIS = [
    {"cnpj_basico": "11222333", "titular": "TITULAR EXEMPLO", "id_pessoa": "p-aaa"},
    {
        "cnpj_basico": "33444555",
        "titular": "OUTRO TITULAR EXEMPLO",
        "id_pessoa": "p-bbb",
    },
]


def _acervo_de_individuais(pasta: Path, linhas: list[dict], **a_mais) -> Path:
    """`individuais/<xx>.parquet` no formato do montador, mais o `socios_pf` que a pasta exige."""
    if not (pasta / pessoa.SOCIOS).is_dir():
        acervo_de_mentira._acervo(pasta, acervo_de_mentira.LINHAS)
    tabela = pd.DataFrame(linhas).assign(mes_do_retrato=MES, **a_mais)
    (pasta / pessoa.INDIVIDUAIS).mkdir(parents=True)
    for prefixo, parte in tabela.groupby(tabela["cnpj_basico"].str[:2]):
        parte.to_parquet(pasta / pessoa.INDIVIDUAIS / f"{prefixo}.parquet", index=False)
    return pasta


def test_o_titular_da_empresa_e_so_o_nome(tmp_path):
    acervo = _acervo_de_individuais(tmp_path, INDIVIDUAIS)
    titular = pessoa.titular_da_empresa(acervo, EMPRESA)
    assert titular.titulares == [{"nome": "TITULAR EXEMPLO"}]
    assert titular.total == 1 and titular.mes_do_retrato == MES
    assert "p-aaa" not in str(titular)  # o pseudônimo fica no arquivo


def test_aceita_o_cnpj_com_pontuacao_e_qualquer_filial(tmp_path):
    acervo = _acervo_de_individuais(tmp_path, INDIVIDUAIS)
    assert pessoa.titular_da_empresa(
        acervo, "11.222.333/0001-81"
    ) == pessoa.titular_da_empresa(acervo, "11222333000262")


def test_coluna_a_mais_no_arquivo_nunca_sai(tmp_path):
    acervo = _acervo_de_individuais(tmp_path, INDIVIDUAIS, cpf="***123456**")
    titular = pessoa.titular_da_empresa(acervo, EMPRESA)
    assert all(set(t) == {"nome"} for t in titular.titulares)
    assert "123456" not in str(titular)


def test_empresa_que_nao_e_individual_sai_vazia(tmp_path):
    acervo = _acervo_de_individuais(tmp_path, INDIVIDUAIS)
    assert pessoa.titular_da_empresa(acervo, "99000000000100") == pessoa.Titular(
        [], 0, None
    )


def test_titular_sem_nome_nao_sai(tmp_path):
    linhas = [{"cnpj_basico": "11222333", "titular": "", "id_pessoa": "p-ccc"}]
    acervo = _acervo_de_individuais(tmp_path, linhas)
    assert pessoa.titular_da_empresa(acervo, EMPRESA).total == 0


@pytest.mark.parametrize("cnpj", ["", "123", "../../etc/passwd"])
def test_cnpj_invalido_nao_vira_caminho(tmp_path, cnpj):
    with pytest.raises(pessoa.CnpjInvalidoError):
        pessoa.titular_da_empresa(_acervo_de_individuais(tmp_path, INDIVIDUAIS), cnpj)


def test_servidor_sem_a_tabela_de_individuais_e_acervo_indisponivel(tmp_path):
    acervo = acervo_de_mentira._acervo(tmp_path, acervo_de_mentira.LINHAS)
    with pytest.raises(pessoa.AcervoIndisponivelError):
        pessoa.titular_da_empresa(acervo, EMPRESA)


def test_arquivo_estragado_e_acervo_indisponivel(tmp_path):
    acervo = _acervo_de_individuais(tmp_path, INDIVIDUAIS)
    (acervo / pessoa.INDIVIDUAIS / "11.parquet").write_bytes(b"isto nao e parquet")
    with pytest.raises(pessoa.AcervoIndisponivelError):
        pessoa.titular_da_empresa(acervo, EMPRESA)


def test_os_limites_dizem_que_e_o_nome_da_razao_social_sem_cpf():
    texto = " ".join(pessoa.LIMITES_DO_TITULAR).lower()
    assert "cpf" in texto and "razão social" in texto
