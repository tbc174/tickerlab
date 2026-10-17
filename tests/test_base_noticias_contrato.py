"""Contrato das tabelas das notícias de dado (ADR 0093, plano das notícias, Tarefa 3)."""

from base.dicionario import TABELAS

PROIBIDAS = ("pessoa", "diretor", "nome", "cpf", "administrador", "conselheiro")


def test_tabelas_existem_com_chaves_e_as_tres_datas():
    fatos = TABELAS["noticias_fatos"]
    assert fatos.chaves == ("id_fato",)
    assert fatos.datas == {
        "aconteceu_em": "aconteceu_em",
        "publico_em": "publico_em",
        "coletado_em": "coletado_em",
    }
    numeros = TABELAS["noticias_numeros"]
    assert numeros.chaves == ("id_fato", "campo")
    assert numeros.datas == {"publico_em": "origem_divulgado_em"}


def test_colunas_do_plano_estao_no_dicionario():
    assert list(TABELAS["noticias_fatos"].colunas) == [
        "id_fato",
        "pauta",
        "versao_do_gatilho",
        "cnpj",
        "empresa",
        "tabela_de_origem",
        "chave_de_origem",
        "aconteceu_em",
        "publico_em",
        "coletado_em",
        "link",
        "topico",
        "metodo_do_topico",
        "versao_do_topico",
        "trecho",
        "reapresentacao",
        "fato_anterior",
        "marcas",
        "licenca",
        "hash_da_linha",
        "versao_do_codigo",
    ]
    assert list(TABELAS["noticias_numeros"].colunas) == [
        "id_fato",
        "campo",
        "valor",
        "unidade",
        "periodo",
        "origem_conta",
        "origem_periodo",
        "origem_versao",
        "origem_divulgado_em",
        "calculo",
    ]


def test_nenhuma_coluna_de_pessoa_e_a_tabela_nao_guarda_pessoa():
    for nome in ("noticias_fatos", "noticias_numeros"):
        tabela = TABELAS[nome]
        assert tabela.pessoa is False
        for coluna in tabela.colunas:
            assert not any(p in coluna.lower() for p in PROIBIDAS), (nome, coluna)


def test_licenca_e_modulo():
    for nome in ("noticias_fatos", "noticias_numeros"):
        assert TABELAS[nome].modulo == "mercado_e_empresas"
        assert TABELAS[nome].familia_da_fonte in {"cvm", "bcb"}
