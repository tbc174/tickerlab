"""SIGSIF do MAPA (base/sigsif.py): estabelecimentos com SIF, habilitações à exportação e abates.
Nada vai à internet: os arquivos são os dublês de `dados_de_exemplo/mapa/`."""

from datetime import date
from pathlib import Path

import pandas as pd

from base import sigsif

PASTA = Path(__file__).parent.parent / "dados_de_exemplo" / "mapa"
ESTABELECIMENTOS = (PASTA / "sigsif_estabelecimentos_registrados.csv").read_bytes()
HABILITADOS = (PASTA / "sigsif_habilitados_exportacao.csv").read_bytes()
ABATES = (PASTA / "sigsif_abates.csv").read_bytes()
COLETA = date(2026, 11, 3)
ALFA, BETA = "33000167000101", "60746948000112"


def test_so_ficam_as_linhas_com_cnpj_e_o_cpf_nao_passa_nem_mascarado_nem_inteiro():
    tabela = sigsif.ler_estabelecimentos(ESTABELECIMENTOS, COLETA)
    assert set(tabela["cnpj"]) == {ALFA, BETA}
    assert tabela.attrs["descartadas_sem_cnpj"] == 3
    texto = tabela.to_csv()
    for nome in ("PESSOA FICTICIA", "789", "790", "791", "123.456", "12345678"):
        assert nome not in texto


def test_cpf_de_onze_digitos_nao_vira_cnpj_com_zeros_a_esquerda():
    cru = ESTABELECIMENTOS.decode().splitlines()
    cabecalho, cpf = cru[0], cru[-1]
    tabela = sigsif.ler_estabelecimentos(f"{cabecalho}\n{cpf}\n".encode(), COLETA)
    assert tabela.empty


def test_contato_e_endereco_nao_sao_copiados():
    tabela = sigsif.ler_estabelecimentos(ESTABELECIMENTOS, COLETA)
    proibidas = {"TELEFONE", "EMAIL", "LOGRADOURO", "BAIRRO", "CEP", "NOME_FANTASIA"}
    assert not proibidas & {c.upper() for c in tabela.columns}
    assert "exemplo.invalid" not in tabela.to_csv()


def test_o_sif_repete_por_categoria_e_o_numero_perde_os_zeros_a_esquerda():
    tabela = sigsif.ler_estabelecimentos(ESTABELECIMENTOS, COLETA)
    alfa = tabela[tabela["cnpj"] == ALFA]
    assert list(alfa["nr_sif"]) == ["123", "123"]
    assert list(alfa["categoria_classe"]) == ["ABATE DE BOVINOS", "INDUSTRIALIZACAO"]
    assert alfa["disponivel_em"].eq(pd.Timestamp(COLETA)).all()
    assert tabela["situacao"].tolist() == ["ATIVO", "ATIVO", "SUSPENSO"]


def test_habilitados_ligam_pelo_sif_e_nunca_pelo_nome():
    registrados = sigsif.ler_estabelecimentos(ESTABELECIMENTOS, COLETA)
    tabela = sigsif.ler_habilitados(HABILITADOS, registrados, COLETA)
    # o nome da habilitação 123 é outro, mas o SIF é o do Alfa
    assert tabela.loc[tabela["sif"] == "123", "cnpj"].item() == ALFA
    assert tabela.loc[tabela["sif"] == "456", "cnpj"].item() == BETA
    # o nome é igual ao do Alfa, mas o SIF 9999 não está nos registrados: sem CNPJ
    sem_sif = tabela[tabela["sif"] == "9999"]
    assert sem_sif["cnpj"].isna().all()


def test_sif_que_aponta_para_dois_cnpjs_fica_sem_cnpj():
    cru = ESTABELECIMENTOS.decode().splitlines()
    repetido = cru[3].replace("456", "123")
    registrados = sigsif.ler_estabelecimentos(
        "\n".join([*cru[:3], repetido]).encode(), COLETA
    )
    tabela = sigsif.ler_habilitados(HABILITADOS, registrados, COLETA)
    assert tabela.loc[tabela["sif"] == "123", "cnpj"].isna().all()


def test_habilitados_trazem_validade_ocorrencia_e_suspensao_como_datas():
    registrados = sigsif.ler_estabelecimentos(ESTABELECIMENTOS, COLETA)
    tabela = sigsif.ler_habilitados(HABILITADOS, registrados, COLETA)
    china = tabela[tabela["pais"].str.startswith("CHINA")].iloc[0]
    assert china["dt_validade"] == pd.Timestamp("2028-07-31")
    assert pd.isna(china["dt_suspensao"])
    beta = tabela[tabela["sif"] == "456"].iloc[0]
    assert beta["dt_suspensao"] == pd.Timestamp("2024-01-15")
    assert pd.isna(beta["dt_validade"])


def test_abates_ficam_por_uf_somados_e_sem_nenhuma_coluna_de_empresa():
    tabela = sigsif.ler_abates(ABATES, COLETA)
    assert not {"cnpj", "sif", "nr_sif", "estabelecimento"} & set(tabela.columns)
    suino = tabela[(tabela["uf"] == "BA") & (tabela["categoria"] == "Suino")].iloc[0]
    assert suino["mes"] == pd.Timestamp("2003-01-01")
    assert (suino["machos"], suino["femeas"], suino["total"]) == (1100, 1440, 2540)
    assert len(tabela) == 3


def test_atribuicao_cita_o_mapa_e_a_licenca():
    assert "Ministério da Agricultura" in sigsif.ATRIBUICAO
    assert "CC BY" in sigsif.ATRIBUICAO


def test_cpf_no_fim_da_razao_social_do_mei_sai():
    cru = ESTABELECIMENTOS.decode().splitlines()
    mei = cru[1].replace("FRIGORIFICO EXEMPLO ALFA S/A", "FULANO FICTICIO 12345678909")
    conteudo = "\n".join([cru[0], mei]).encode()
    tabela = sigsif.ler_estabelecimentos(conteudo, COLETA)
    assert tabela["razao_social"].item() == "FULANO FICTICIO"
    assert "12345678909" not in tabela.to_csv()
