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
    with pytest.raises(pessoa.CnpjInvalidoError):
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


def test_arquivo_estragado_e_acervo_indisponivel_nao_cnpj_invalido(tmp_path):
    acervo = _acervo(tmp_path, LINHAS)
    (acervo / pessoa.SOCIOS / "11.parquet").write_bytes(b"isto nao e parquet")
    with pytest.raises(pessoa.AcervoIndisponivelError):
        pessoa.socios_da_empresa(acervo, EMPRESA)


def test_os_limites_dizem_o_que_fica_de_fora():
    texto = " ".join(pessoa.LIMITES).lower()
    assert "menor" in texto and "cpf" in texto and "retrato" in texto


# ---------------------------------------------------------------- contato do estabelecimento


def _contato(cnpj, matriz=True, **campos):
    """Um estabelecimento de mentira no formato do montador (`contato/<xx>.parquet`)."""
    return {
        "cnpj_basico": cnpj[:8],
        "cnpj": cnpj,
        "matriz": matriz,
        "tipo_logradouro": "RUA",
        "logradouro": "DOS EXEMPLOS",
        "numero": "100",
        "complemento": None,
        "bairro": "CENTRO",
        "cep": "01001000",
        "municipio": "7107",
        "uf": "SP",
        "telefone_1": "1130001000",
        "telefone_2": None,
        "email": "contato@exemplo.com.br",
    } | campos


FILIAL = "11222333000262"
CONTATOS = [
    _contato(FILIAL, matriz=False, telefone_2="11990001000", complemento="LOJA 3"),
    _contato(EMPRESA),
    _contato(OUTRA, email=None, telefone_1=None),
    _contato("22333444000181"),
]


def _acervo_de_contato(pasta: Path, linhas: list[dict], **colunas_a_mais) -> Path:
    tabela = pd.DataFrame(linhas).assign(mes_do_retrato=MES, **colunas_a_mais)
    (pasta / pessoa.CONTATO).mkdir(parents=True)
    for prefixo, parte in tabela.groupby(tabela["cnpj_basico"].str[:2]):
        parte.to_parquet(pasta / pessoa.CONTATO / f"{prefixo}.parquet", index=False)
    return pasta


def test_contato_so_da_empresa_a_matriz_antes_da_filial(tmp_path):
    contato = pessoa.contato_da_empresa(_acervo_de_contato(tmp_path, CONTATOS), EMPRESA)
    assert contato.estabelecimentos == [
        {
            "cnpj": EMPRESA,
            "matriz": True,
            "logradouro": "RUA DOS EXEMPLOS, 100",
            "bairro": "CENTRO",
            "cep": "01001000",
            "municipio": "SAO PAULO",
            "uf": "SP",
            "telefones": ["1130001000"],
            "email": "contato@exemplo.com.br",
        },
        {
            "cnpj": FILIAL,
            "matriz": False,
            "logradouro": "RUA DOS EXEMPLOS, 100, LOJA 3",
            "bairro": "CENTRO",
            "cep": "01001000",
            "municipio": "SAO PAULO",
            "uf": "SP",
            "telefones": ["1130001000", "11990001000"],
            "email": "contato@exemplo.com.br",
        },
    ]
    assert contato.total == 2 and contato.mes_do_retrato == MES


def test_o_estabelecimento_pedido_vem_primeiro(tmp_path):
    acervo = _acervo_de_contato(tmp_path, CONTATOS)
    contato = pessoa.contato_da_empresa(acervo, "11.222.333/0002-62")
    assert [e["cnpj"] for e in contato.estabelecimentos] == [FILIAL, EMPRESA]


def test_contato_sem_telefone_nem_email_sai_so_com_o_endereco(tmp_path):
    contato = pessoa.contato_da_empresa(_acervo_de_contato(tmp_path, CONTATOS), OUTRA)
    (unico,) = contato.estabelecimentos
    assert unico["telefones"] == [] and unico["email"] is None
    assert unico["logradouro"] == "RUA DOS EXEMPLOS, 100"


def test_coluna_a_mais_no_contato_nunca_sai(tmp_path):
    acervo = _acervo_de_contato(tmp_path, CONTATOS, nome_fantasia="FANTASIA EXEMPLO")
    contato = pessoa.contato_da_empresa(acervo, EMPRESA)
    assert "FANTASIA" not in str(contato)


def test_empresa_sem_estabelecimento_ativo_sai_vazia(tmp_path):
    acervo = _acervo_de_contato(tmp_path, CONTATOS)
    for cnpj in ("11000000000100", "99000000000100"):  # com e sem arquivo do prefixo
        assert pessoa.contato_da_empresa(acervo, cnpj) == pessoa.Contato([], 0, None)


def test_contato_mostra_ate_o_maximo_e_diz_o_total(tmp_path, monkeypatch):
    monkeypatch.setattr(pessoa, "MAXIMO_DE_ESTABELECIMENTOS", 1)
    contato = pessoa.contato_da_empresa(_acervo_de_contato(tmp_path, CONTATOS), FILIAL)
    assert [e["cnpj"] for e in contato.estabelecimentos] == [FILIAL]
    assert contato.total == 2


def test_municipio_desconhecido_sai_com_o_codigo(tmp_path):
    linhas = [_contato(EMPRESA, municipio="0000", tipo_logradouro=None)]
    (unico,) = pessoa.contato_da_empresa(
        _acervo_de_contato(tmp_path, linhas), EMPRESA
    ).estabelecimentos
    assert unico["municipio"] == "código 0000"
    assert unico["logradouro"] == "DOS EXEMPLOS, 100"


@pytest.mark.parametrize("cnpj", ["", "123", "../../etc/passwd", "11222333/../x"])
def test_cnpj_invalido_no_contato_nao_vira_caminho(tmp_path, cnpj):
    with pytest.raises(pessoa.CnpjInvalidoError):
        pessoa.contato_da_empresa(_acervo_de_contato(tmp_path, CONTATOS), cnpj)


def test_sem_a_tabela_de_contato_o_acervo_esta_indisponivel(tmp_path):
    acervo = _acervo(
        tmp_path, LINHAS
    )  # só os sócios: o contato ainda não foi montado aqui
    with pytest.raises(pessoa.AcervoIndisponivelError):
        pessoa.contato_da_empresa(acervo, EMPRESA)


def test_contato_estragado_e_acervo_indisponivel(tmp_path):
    acervo = _acervo_de_contato(tmp_path, CONTATOS)
    (acervo / pessoa.CONTATO / "11.parquet").write_bytes(b"isto nao e parquet")
    with pytest.raises(pessoa.AcervoIndisponivelError):
        pessoa.contato_da_empresa(acervo, EMPRESA)


def test_os_limites_do_contato_avisam_do_mei_e_do_retrato():
    texto = " ".join(pessoa.LIMITES_DO_CONTATO).lower()
    assert "mei" in texto and "retrato" in texto and "ativos" in texto


def _acervo_de_individuais(pasta: Path, raizes: list[str]) -> None:
    (pasta / pessoa.INDIVIDUAIS).mkdir(parents=True)
    tabela = pd.DataFrame(
        {"cnpj_basico": raizes, "titular": "FULANA EXEMPLO", "id_pessoa": "x"}
    )
    for prefixo, parte in tabela.groupby(tabela["cnpj_basico"].str[:2]):
        parte.to_parquet(pasta / pessoa.INDIVIDUAIS / f"{prefixo}.parquet", index=False)


def test_contato_de_individual_sai_so_com_municipio_uf_telefone_e_email(tmp_path):
    pasta = _acervo_de_contato(tmp_path / "acervo", CONTATOS)
    _acervo_de_individuais(pasta, [EMPRESA[:8]])
    for estabelecimento in pessoa.contato_da_empresa(pasta, EMPRESA).estabelecimentos:
        assert (
            estabelecimento["logradouro"] is None and estabelecimento["bairro"] is None
        )
        assert estabelecimento["cep"] is None
        assert estabelecimento["uf"] == "SP" and estabelecimento["municipio"]
    primeiro = pessoa.contato_da_empresa(pasta, EMPRESA).estabelecimentos[0]
    assert primeiro["telefones"] == ["1130001000"] and primeiro["email"]


def test_empresa_que_nao_e_individual_segue_com_o_endereco_inteiro(tmp_path):
    pasta = _acervo_de_contato(tmp_path / "acervo", CONTATOS)
    _acervo_de_individuais(pasta, ["22333444"])  # outra raiz é MEI; esta não
    inteira = pessoa.contato_da_empresa(pasta, EMPRESA).estabelecimentos[0]
    assert (
        inteira["logradouro"] == "RUA DOS EXEMPLOS, 100"
        and inteira["cep"] == "01001000"
    )
    assert (
        pessoa.contato_da_empresa(pasta, "22333444000181").estabelecimentos[0]["cep"]
        is None
    )
