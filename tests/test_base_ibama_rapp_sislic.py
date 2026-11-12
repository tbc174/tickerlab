"""RAPP de madeira e lenha e SISLIC do Ibama (base/ibama_rapp_sislic.py).
Nada vai à internet: os arquivos são os dublês de `dados_de_exemplo/ibama/` (retrato de 03/11/2026)."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from base import ibama_rapp_sislic as ibama

PASTA = Path(__file__).parent.parent / "dados_de_exemplo" / "ibama"
RAPP = (PASTA / "rapp_madeira_lenha.csv").read_bytes()
SISLIC = (PASTA / "sislic_licencas.csv").read_bytes()
COLETA = date(2026, 11, 3)


def _rapp_com(linha: str) -> bytes:
    cabecalho = RAPP.decode("utf-8-sig").splitlines()[0]
    return f"{cabecalho}\r\n{linha}\r\n".encode("utf-8-sig")


def test_o_cnpj_pontuado_vira_so_digitos_e_a_raiz_sai_dele():
    tabela = ibama.ler_rapp_madeira_lenha(RAPP, COLETA)
    primeira = tabela.iloc[0]
    assert primeira["cnpj"] == "00001180000126"
    assert primeira["cnpj_raiz"] == "00001180"
    assert tabela["cnpj"].str.fullmatch(r"\d{14}").all()


def test_a_unidade_da_lenha_fica_numa_coluna_sem_converter():
    tabela = ibama.ler_rapp_madeira_lenha(RAPP, COLETA)
    assert set(tabela["lenha_unidade"]) == {"estéreo ou m³"}
    assert set(tabela["tora_unidade"]) == {"m³"}
    assert set(tabela["area_unidade"]) == {"ha"}
    cereal = tabela[tabela["cnpj"] == "00012377000160"].iloc[0]
    assert (
        cereal["lenha"] == 20000.0 and cereal["tora"] == 20000.0
    )  # nenhum fator aplicado


def test_zero_declarado_continua_zero_e_o_texto_avisa_que_nao_declarar_nao_e_zero():
    tabela = ibama.ler_rapp_madeira_lenha(RAPP, COLETA)
    zerada = tabela.iloc[0]
    assert (
        zerada["lenha"] == 0.0
        and zerada["tora"] == 0.0
        and zerada["area_explorada"] == 0.0
    )
    assert not tabela[["lenha", "tora", "area_explorada"]].isna().any().any()
    assert "não declarar não é o mesmo que zero" in ibama.AVISO_RAPP


def test_campo_vazio_vira_nulo_e_nao_zero():
    tabela = ibama.ler_rapp_madeira_lenha(
        _rapp_com("00.001.180/0001-26;X;RIO DE JANEIRO;RIO;2024;;0,00;0,00;Ativa"),
        COLETA,
    )
    assert pd.isna(tabela["lenha"].iloc[0]) and tabela["tora"].iloc[0] == 0.0


def test_pessoa_fisica_fica_de_fora_do_rapp():
    tabela = ibama.ler_rapp_madeira_lenha(
        _rapp_com("888.000.000-46;FULANO;GOIAS;RIO VERDE;2020;1,00;0,00;0,00;Ativa"),
        COLETA,
    )
    assert tabela.empty


def test_o_rapp_pega_o_comeco_e_o_fim_do_arquivo_e_a_chave_nao_repete():
    tabela = ibama.ler_rapp_madeira_lenha(RAPP, COLETA)
    assert tabela["razao_social"].iloc[0].startswith("CENTRAIS ELETRICAS")
    assert tabela["razao_social"].iloc[-1].startswith("TOCHETTO")
    assert not tabela.duplicated(ibama.CHAVE_RAPP).any()
    assert (tabela["disponivel_em"] == pd.Timestamp(COLETA)).all()
    cereal_2019 = tabela[(tabela["cnpj"] == "00012377000160") & (tabela["ano"] == 2019)]
    assert cereal_2019["lenha"].iloc[0] == 22000.0


def test_cabecalho_inesperado_do_rapp_para_com_erro():
    with pytest.raises(ValueError, match="cabeçalho"):
        ibama.ler_rapp_madeira_lenha(b"A;B\r\n1;2\r\n", COLETA)


def test_o_sislic_le_comeco_meio_e_fim_do_arquivo_ordenado_por_tipo():
    tabela = ibama.ler_sislic(SISLIC, COLETA)
    tipos = list(dict.fromkeys(tabela["tipo_licenca"]))
    assert tipos[0] == "Anuência"
    assert "Licença de Operação" in tipos
    assert tipos[-1] == "Retificação de Licença Prévia para Perfuração"
    assert len(tabela) == 24
    assert not tabela.duplicated(ibama.CHAVE_SISLIC).any()
    primeira = tabela.iloc[0]
    assert primeira["emitida_em"] == pd.Timestamp("2026-10-23")
    assert primeira["atualizado_no_relatorio"] == pd.Timestamp("2026-11-03 01:04")
    assert (tabela["disponivel_em"] == pd.Timestamp(COLETA)).all()


def test_o_pac_fica_como_veio_sem_interpretar():
    tabela = ibama.ler_sislic(SISLIC, COLETA)
    assert set(tabela["pac"]) == {"Sim", "No"}


def test_o_titular_que_nao_parece_pessoa_juridica_nao_e_guardado():
    cabecalho = SISLIC.decode("utf-8-sig").splitlines()[0]
    linha = (
        "Licença de Operação;1/2020;01/01/2020;01/01/2025;Fazenda X;MARIA DA SILVA;"
        "02001.000001/2020-01;Agro;No;03/11/2026 01:04"
    )
    tabela = ibama.ler_sislic(f"{cabecalho}\n{linha}\n".encode("utf-8-sig"), COLETA)
    assert tabela["titular"].iloc[0] == ""
    assert tabela["processo_ibama"].iloc[0] == "02001.000001/2020-01"
    assert (ibama.ler_sislic(SISLIC, COLETA)["titular"] != "").all()


def test_a_ligacao_e_so_pelo_numero_do_processo_e_o_nome_nunca_liga():
    licencas = ibama.ler_sislic(SISLIC, COLETA)
    autos = pd.DataFrame(
        {
            "NUM_PROCESSO": ["02001002739200411", "99999000000200000"],
            "NOME": [
                "OUTRO NOME",
                "UHE Cachoeira Dourada",
            ],  # o 2º tem o nome de um empreendimento
        }
    )
    ligadas = ibama.ligar_por_processo(licencas, autos, "NUM_PROCESSO")
    assert list(ligadas["processo_ibama"]) == ["02001.002739/2004-11"]
    assert list(ligadas["NOME"]) == ["OUTRO NOME"]


def test_processo_vazio_nao_liga_com_processo_vazio():
    licencas = ibama.ler_sislic(SISLIC, COLETA).assign(processo_ibama="")
    autos = pd.DataFrame({"NUM_PROCESSO": [""]})
    assert ibama.ligar_por_processo(licencas, autos, "NUM_PROCESSO").empty
