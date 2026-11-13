"""Lista suja do MTE e termos de embargo do IBAMA: só CNPJ de DV certo (CPF e nome da pessoa física nunca
entram), chave sem repetição e `disponivel_em` sem olhar o futuro.

Os arquivos daqui são de mentira, no formato conferido em 04/11/2026 nos guardados pelo arquivista."""

import pandas as pd

from base import cnpj as cnpjs
from base import ibama_embargos, mte_lista_suja


def _cnpj(raiz: str, filial: str = "0001") -> str:
    for dv in range(100):
        bruto = f"{raiz}{filial}{dv:02d}"
        if cnpjs.dv_confere(bruto):
            return bruto
    raise AssertionError(raiz)


EMPRESA = _cnpj("11222333")
OUTRA = _cnpj("33000167")
INVALIDO = EMPRESA[:-1] + str((int(EMPRESA[-1]) + 1) % 10)
CPF = "888.000.005-51"
DIA = pd.Timestamp("2026-10-14")


def _mte(*linhas: str) -> bytes:
    cabecalho = "ID;Ano da ação fiscal;UF;Empregador;CNPJ/CPF;Estabelecimento;Inclusão no Cadastro de Empregadores"
    return "\r\n".join([cabecalho, *linhas]).encode("latin-1")


def test_mte_so_cnpj_entra_e_o_nome_da_pessoa_fisica_nao_vaza():
    conteudo = _mte(
        f"1;2021;PA;EMPRESA DE MENTIRA LTDA;{cnpjs.formatar(EMPRESA)};FAZENDA A;05/04/2024 a 26/05/2025",
        f"2;2024;MS;JOAQUIM PRODUTOR RURAL;{CPF};FAZENDA B;01/01/2025",
        f"3;2024;MS;OUTRA LTDA;{INVALIDO};FAZENDA C;01/01/2025",
        f"4;2021;PA;EMPRESA DE MENTIRA LTDA;{cnpjs.formatar(EMPRESA)};FAZENDA A;05/04/2024",
    )
    tabela, contagem = mte_lista_suja.ler_retrato(conteudo)
    assert len(tabela) == 1
    assert tabela["cnpj"].iloc[0] == cnpjs.formatar(EMPRESA)
    assert tabela["incluida_em"].iloc[0] == pd.Timestamp("2024-04-05")
    assert contagem == {
        "linhas": 4,
        "pessoa_fisica": 1,
        "cnpj_invalido": 1,
        "id_repetido": 1,
    }
    assert "JOAQUIM" not in tabela.astype(str).to_csv()
    assert "366176019" not in tabela.astype(str).to_csv().replace(".", "").replace(
        "-", ""
    )


def test_mte_disponivel_pela_inclusao_nunca_depois_do_retrato():
    tabela = pd.DataFrame(
        {"incluida_em": pd.to_datetime(["2024-04-05", "2027-01-01", None])}
    )
    pronto = mte_lista_suja.disponivel_no_primeiro(tabela, DIA)
    assert list(pronto) == [pd.Timestamp("2024-04-05"), DIA, DIA]


def _embargo(
    seq: str, documento: str, embargo: str = "2025-09-25 15:10:00", desembargo: str = ""
) -> str:
    return (
        f"{seq};Lavrado;N;ABC{seq};{embargo};{documento};NOME {seq};2308708;CE;"
        f"71,9994;{'S' if desembargo else ''};{desembargo}"
    )


CABECALHO_EMBARGOS = (
    "SEQ_TAD;DES_STATUS_FORMULARIO;SIT_CANCELADO;NUM_TAD;DAT_EMBARGO;CPF_CNPJ_EMBARGADO;"
    "NOME_EMBARGADO;COD_MUNICIPIO;UF;QTD_AREA_EMBARGADA;SIT_DESEMBARGO;DAT_DESEMBARGO"
)


def _embargos(*linhas: str) -> bytes:
    return "\n".join([CABECALHO_EMBARGOS, *linhas]).encode("latin-1")


def test_embargos_so_cnpj_entra_com_area_em_decimal_e_ano_impossivel_vazio():
    conteudo = _embargos(
        _embargo("1", EMPRESA),
        _embargo("2", "88800000801"),  # CPF
        _embargo("3", INVALIDO),
        _embargo("4", OUTRA, embargo="2925-09-25 15:10:00"),
        _embargo("1", OUTRA),  # SEQ_TAD repetido
    )
    tabela, contagem = ibama_embargos.ler_retrato(conteudo, DIA)
    assert list(tabela["id_na_fonte"]) == ["1", "4"]
    assert tabela["area_embargada_ha"].iloc[0] == 71.9994
    assert tabela["embargada_em"].iloc[0] == pd.Timestamp("2025-09-25")
    assert pd.isna(tabela["embargada_em"].iloc[1])
    assert contagem == {
        "linhas": 5,
        "pessoa_fisica": 1,
        "cnpj_invalido": 1,
        "id_repetido": 1,
        "id_pelo_numero_do_termo": 0,
    }
    assert "NOME 2" not in tabela.astype(str).to_csv()


def test_embargos_disponivel_pelo_embargo_ou_desembargo_nunca_depois_do_retrato():
    conteudo = _embargos(
        _embargo("1", EMPRESA),
        _embargo("2", OUTRA, desembargo="2026-03-01 10:00:00"),
        _embargo("3", EMPRESA, embargo="2099-01-01 00:00:00"),
    )
    tabela, _ = ibama_embargos.ler_retrato(conteudo, DIA)
    pronto = ibama_embargos.disponivel_no_primeiro(tabela, DIA)
    assert list(pronto) == [
        pd.Timestamp("2025-09-25"),
        pd.Timestamp("2026-03-01"),
        DIA,
    ]


def _embargos_como_o_ibama_publica(*linhas: str) -> bytes:
    """O arquivo real (conferido em 13/11/2026, linha 914): UTF-8 com BOM e cabeçalho entre aspas."""
    cabecalho = ";".join(f'"{coluna}"' for coluna in CABECALHO_EMBARGOS.split(";"))
    return "﻿".encode() + "\n".join([cabecalho, *linhas]).encode("utf-8")


def test_embargos_le_o_arquivo_com_bom_e_cabecalho_entre_aspas():
    """Linha 914: lido como Latin-1, o BOM grudava no 1º cabeçalho, o `SEQ_TAD` sumia e todos os
    termos de PJ viravam um só."""
    conteudo = _embargos_como_o_ibama_publica(
        _embargo("1", EMPRESA).replace("Lavrado", "Em análise"),
        _embargo("2", OUTRA),
        _embargo("3", "88800000801"),  # CPF
    )
    tabela, contagem = ibama_embargos.ler_retrato(conteudo, DIA)
    assert list(tabela["id_na_fonte"]) == ["1", "2"]
    assert tabela["situacao_do_termo"].iloc[0] == "Em análise"
    assert contagem["pessoa_fisica"] == 1
    assert contagem["id_repetido"] == 0
    assert "NOME 3" not in tabela.astype(str).to_csv()


def test_embargos_sem_seq_tad_ficam_pelo_numero_do_termo_e_nao_se_juntam():
    """Linha 914: termo sem `SEQ_TAD` (há milhares no arquivo real) não pode virar um id vazio só."""
    conteudo = _embargos(
        _embargo("", EMPRESA),
        _embargo("", OUTRA).replace("ABC;", "XYZ;"),
        _embargo("7", OUTRA),
    )
    tabela, contagem = ibama_embargos.ler_retrato(conteudo, DIA)
    assert list(tabela["id_na_fonte"]) == ["TAD ABC", "TAD XYZ", "7"]
    assert contagem["id_repetido"] == 0
    assert contagem["id_pelo_numero_do_termo"] == 2
    assert tabela["id_na_fonte"].ne("").all()
