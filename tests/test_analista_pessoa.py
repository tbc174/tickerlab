"""O leitor do acervo de pessoa da tela da equipe (linha 808). Todo nome aqui é inventado."""

from pathlib import Path

import pandas as pd
import pytest

from src.analista import pessoa

EMPRESA = "11222333000181"
OUTRA = "11999888000100"
MES = "2026-10"


def _acervo(pasta: Path, linhas: list[dict], **colunas_a_mais) -> Path:
    """Um acervo de mentira no formato do montador: `socios_pf/<xx>.parquet`."""
    tabela = pd.DataFrame(linhas).assign(mes_do_retrato=MES, **colunas_a_mais)
    tabela["data_entrada"] = pd.to_datetime(tabela["data_entrada"])
    (pasta / pessoa.SOCIOS).mkdir(parents=True)
    for prefixo, parte in tabela.groupby(tabela["cnpj_basico"].str[:2]):
        parte.to_parquet(pasta / pessoa.SOCIOS / f"{prefixo}.parquet", index=False)
    return pasta


def _socio(raiz, nome, qualificacao="49", entrada="2020-01-31"):
    return {
        "cnpj_basico": raiz,
        "nome_socio": nome,
        "qualificacao": qualificacao,
        "data_entrada": entrada,
    }


LINHAS = [
    _socio("11222333", "FULANA EXEMPLO", "49", "2021-05-10"),
    _socio("11222333", "BELTRANO EXEMPLO", "05", "2019-03-01"),
    _socio("11999888", "SICRANA EXEMPLO"),
    _socio("22333444", "OUTRO PREFIXO EXEMPLO"),
]


def test_so_os_socios_da_empresa_do_mais_antigo_ao_mais_novo(tmp_path):
    socios = pessoa.socios_da_empresa(_acervo(tmp_path, LINHAS), EMPRESA)
    assert socios.socios == [
        {
            "nome": "BELTRANO EXEMPLO",
            "qualificacao": "Administrador",
            "entrou_em": "2019-03-01",
        },
        {
            "nome": "FULANA EXEMPLO",
            "qualificacao": "Sócio-Administrador",
            "entrou_em": "2021-05-10",
        },
    ]
    assert socios.total == 2 and socios.mes_do_retrato == MES


def test_aceita_o_cnpj_com_pontuacao_e_qualquer_filial(tmp_path):
    acervo = _acervo(tmp_path, LINHAS)
    da_matriz = pessoa.socios_da_empresa(acervo, "11.222.333/0001-81")
    da_filial = pessoa.socios_da_empresa(acervo, "11222333000262")
    assert da_matriz == da_filial and da_matriz.total == 2


def test_coluna_a_mais_no_arquivo_nunca_sai(tmp_path):
    acervo = _acervo(tmp_path, LINHAS, cpf="***123456**", faixa_etaria="5")
    socios = pessoa.socios_da_empresa(acervo, EMPRESA)
    assert all(set(s) == {"nome", "qualificacao", "entrou_em"} for s in socios.socios)
    assert "123456" not in str(socios)


def test_empresa_sem_socio_pessoa_fisica_sai_vazia(tmp_path):
    acervo = _acervo(tmp_path, LINHAS)
    assert pessoa.socios_da_empresa(acervo, "11000000000100").total == 0
    assert pessoa.socios_da_empresa(acervo, "99000000000100") == pessoa.Socios(
        [], 0, None
    )


def test_sem_data_de_entrada_vai_para_o_fim_e_codigo_desconhecido_sai_com_o_codigo(
    tmp_path,
):
    linhas = [
        _socio("11222333", "SEM DATA EXEMPLO", "49", None),
        _socio("11222333", "COM DATA EXEMPLO", "ZZ"),
    ]
    socios = pessoa.socios_da_empresa(_acervo(tmp_path, linhas), EMPRESA).socios
    assert [s["nome"] for s in socios] == ["COM DATA EXEMPLO", "SEM DATA EXEMPLO"]
    assert "ZZ" in socios[0]["qualificacao"] and socios[1]["entrou_em"] is None


def test_mostra_ate_o_maximo_e_diz_o_total(tmp_path, monkeypatch):
    monkeypatch.setattr(pessoa, "MAXIMO_DE_SOCIOS", 2)
    linhas = [_socio("11222333", f"SOCIO {n} EXEMPLO") for n in range(5)]
    socios = pessoa.socios_da_empresa(_acervo(tmp_path, linhas), EMPRESA)
    assert len(socios.socios) == 2 and socios.total == 5


@pytest.mark.parametrize("cnpj", ["", "123", "../../etc/passwd", "11222333/../x"])
def test_cnpj_invalido_nao_vira_caminho(tmp_path, cnpj):
    with pytest.raises(ValueError, match="CNPJ"):
        pessoa.socios_da_empresa(_acervo(tmp_path, LINHAS), cnpj)


def test_pasta_do_acervo_vem_da_variavel(tmp_path, monkeypatch):
    monkeypatch.delenv(pessoa.VARIAVEL, raising=False)
    with pytest.raises(pessoa.AcervoIndisponivelError):
        pessoa.pasta_do_acervo()
    monkeypatch.setenv(pessoa.VARIAVEL, str(tmp_path))  # sem a tabela dentro
    with pytest.raises(pessoa.AcervoIndisponivelError):
        pessoa.pasta_do_acervo()
    monkeypatch.setenv(pessoa.VARIAVEL, str(_acervo(tmp_path, LINHAS)))
    assert pessoa.pasta_do_acervo() == tmp_path


def test_os_limites_dizem_o_que_fica_de_fora():
    texto = " ".join(pessoa.LIMITES).lower()
    assert "menor" in texto and "cpf" in texto and "retrato" in texto
