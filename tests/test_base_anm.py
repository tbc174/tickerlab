"""CFEM, SIGBM e AMB da ANM (base/anm.py).

Nada vai à internet. Os três AMB em `dados_de_exemplo/anm/` são o começo e o fim dos arquivos reais (retrato
de 03/11/2026). O CFEM e o SIGBM reais só foram vistos até o cabeçalho (têm documento de pessoa): as linhas
dos dois arquivos de exemplo são fictícias, com CNPJs inventados de DV válido.
"""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from base import anm
from base import cnpj as cnpj_mod

PASTA = Path(__file__).parent.parent / "dados_de_exemplo" / "anm"
CFEM = (PASTA / "cfem_arrecadacao.csv").read_bytes()
SIGBM = (PASTA / "sigbm_barragens.csv").read_bytes()
BRUTA = (PASTA / "amb_producao_bruta.csv").read_bytes()
BENEFICIADA = (PASTA / "amb_producao_beneficiada.csv").read_bytes()
AGUA = (PASTA / "amb_agua_mineral.csv").read_bytes()
COLETA = date(2026, 11, 3)

VALE = "33592510000154"
CSN_MINERACAO = "08902291000115"
CBA = "61409892000173"


def _com_linhas(arquivo: bytes, *linhas: str) -> bytes:
    """O arquivo de exemplo com linhas a mais no fim (já no formato do CSV)."""
    return arquivo + "".join(f"{linha}\r\n" for linha in linhas).encode("cp1252")


def _cfem_de(*cnpjs: str) -> bytes:
    cabecalho = CFEM.decode("cp1252").splitlines()[0]
    linhas = [
        f'"2024","3","8300{i}","2015","PJ","{c}","FERRO","MG","3106200","Belo Horizonte","1","t","1,5","01/04/2024"'
        for i, c in enumerate(cnpjs)
    ]
    return ("\r\n".join([cabecalho, *linhas]) + "\r\n").encode("cp1252")


# ---- CFEM -----------------------------------------------------------------------------------------------


def test_cfem_cnpj_pontuado_ou_nao_vira_14_caracteres_e_a_raiz_sai_dele():
    tabela = anm.ler_cfem(CFEM, COLETA)
    assert tabela["cnpj"].str.fullmatch(r"\d{14}").all()
    assert tabela["cnpj"].iloc[0] == tabela["cnpj"].iloc[1] == "11111111000191"
    assert set(tabela["cnpj_raiz"]) == {"11111111", "22222222", "33333333"}
    assert tabela["cnpj"].map(cnpj_mod.dv_confere).all()


def test_cfem_pessoa_fisica_cpf_mascarado_e_documento_vazio_ficam_de_fora():
    tabela = anm.ler_cfem(CFEM, COLETA)
    assert len(tabela) == 4  # de 7 linhas: 2 de CPF (um mascarado), 1 sem documento
    assert tabela.attrs["descartadas"] == 3
    assert not tabela["processo"].isin(["830003", "830004", "830005"]).any()


def test_cfem_a_data_de_criacao_da_linha_e_o_disponivel_em_e_a_coleta_so_vale_sem_data():
    tabela = anm.ler_cfem(CFEM, COLETA).set_index("processo")
    assert tabela["disponivel_em"].iloc[0] == pd.Timestamp(2024, 4, 15, 10, 30)
    assert tabela["disponivel_em"].iloc[1] == pd.Timestamp(2024, 5, 2, 8)
    assert tabela.loc["830002", "disponivel_em"] == pd.Timestamp(2024, 5, 20)
    # a linha sem DataCriacao não é "do passado": só vale a partir da coleta
    assert tabela.loc["830006", "disponivel_em"] == pd.Timestamp(COLETA)
    assert pd.isna(tabela.loc["830006", "criado_em"])


def test_cfem_numeros_brasileiros_e_zero_declarado():
    tabela = anm.ler_cfem(CFEM, COLETA).set_index("processo")
    assert tabela["valor_recolhido"].iloc[0] == 12345.67
    assert tabela["valor_recolhido"].iloc[1] == 1234.5  # "1.234,50": ponto de milhar
    assert (
        tabela.loc["830002", "quantidade"] == 0.0
        and tabela.loc["830002", "valor_recolhido"] == 0.0
    )


def test_cfem_cabecalho_diferente_e_recusado():
    with pytest.raises(ValueError, match="cabeçalho inesperado"):
        anm.ler_cfem(b'"Ano","Mes"\r\n"2024","3"\r\n', COLETA)


def test_cfem_ponte_com_o_qsa_da_receita_por_tres_cnpjs_conhecidos():
    for conhecido in (VALE, CSN_MINERACAO, CBA):
        assert cnpj_mod.dv_confere(conhecido)
    # a CFEM traz a Vale numa filial e a CBA com pontuação; o QSA é por raiz
    filial_da_vale = (
        "33592510" + "0002" + cnpj_mod.digitos_verificadores("335925100002")
    )
    tabela = anm.ler_cfem(
        _cfem_de(filial_da_vale, CSN_MINERACAO, CBA, "11111111000191"), COLETA
    )
    qsa = pd.DataFrame(
        {
            "cnpj_basico": ["33592510", "08902291", "61409892", "99999999"],
            "socio": ["A", "B", "C", "D"],
        }
    )
    ligada = anm.ligar_ao_qsa(tabela, qsa)
    assert dict(zip(ligada["cnpj_raiz"], ligada["socio"], strict=True)) == {
        "33592510": "A",
        "08902291": "B",
        "61409892": "C",
    }
    assert "11111111" not in set(
        ligada["cnpj_raiz"]
    )  # sem quadro, sem linha: nada é inventado


# ---- SIGBM ----------------------------------------------------------------------------------------------


def test_sigbm_categoria_de_risco_e_dano_potencial_ficam_como_vieram_com_a_data_da_dce():
    tabela = anm.ler_sigbm(SIGBM, COLETA)
    primeira = tabela.iloc[0]
    assert (primeira["categoria_risco"], primeira["dano_potencial"]) == ("Alto", "Alto")
    assert primeira["classificado_em"] == pd.Timestamp(2025, 9, 30)
    assert tabela.iloc[1]["classificado_em"] == pd.Timestamp(2025, 3, 31)
    assert pd.isna(
        tabela.iloc[2]["classificado_em"]
    )  # sem data na fonte, nulo (nada inventado)
    assert primeira["nivel_emergencia"] == "Sem Emergência"
    assert (
        primeira["altura_atual_m"] == 45.5 and primeira["volume_atual_m3"] == 1234567.8
    )


def test_sigbm_o_disponivel_em_e_a_coleta_e_o_cnpj_e_o_do_empreendedor():
    tabela = anm.ler_sigbm(SIGBM, COLETA)
    assert (tabela["disponivel_em"] == pd.Timestamp(COLETA)).all()
    assert tabela["cnpj"].iloc[0] == "11111111000191"
    assert tabela["cnpj_raiz"].iloc[0] == "11111111"
    assert (
        "empreendedor" in anm.AVISO_SIGBM and "não é necessariamente" in anm.AVISO_SIGBM
    )


def test_sigbm_empreendedor_pessoa_fisica_fica_sem_documento_e_sem_nome():
    tabela = anm.ler_sigbm(SIGBM, COLETA)
    pf = tabela[tabela["id"] == "3"].iloc[0]
    assert pf["cnpj"] == "" and pf["cnpj_raiz"] == "" and pf["empreendedor"] == ""
    assert pf["nome"] == "Barragem Fictícia 3"  # a barragem fica; a pessoa não
    assert tabela["empreendedor"].iloc[0] == "Mineradora Fictícia S.A."


def test_sigbm_sem_uma_coluna_exigida_e_recusado():
    cabecalho = (
        SIGBM.decode("cp1252").splitlines()[0].replace('"Nível de Emergência",', "")
    )
    with pytest.raises(ValueError, match="Nível de Emergência"):
        anm.ler_sigbm(cabecalho.encode("cp1252"), COLETA)


# ---- AMB ------------------------------------------------------------------------------------------------


def test_amb_le_o_arquivo_real_em_cp1252_com_virgula_e_aspas():
    assert b"\xc3" not in BRUTA  # CP1252 de verdade, não UTF-8
    tabela = anm.ler_amb_producao_bruta(BRUTA, COLETA)
    assert len(tabela) == 9
    primeira = tabela.iloc[0]
    assert (primeira["ano"], primeira["uf"], primeira["substancia"]) == (
        2010,
        "AC",
        "Areia",
    )
    assert primeira["classe"] == "Não-Metálicos"
    assert primeira["producao_rom_t"] == 155024.5 and primeira["venda_t"] == 127314.03
    assert set(tabela["ano"]) == {2010, 2025}  # começo e fim do arquivo


def test_amb_virgula_zeros_vira_zero_e_nao_nulo():
    tabela = anm.ler_amb_producao_bruta(BRUTA, COLETA)
    assert (tabela["contido"].iloc[0], tabela["consumo_t"].iloc[0]) == (0.0, 0.0)
    assert not tabela.drop(columns="contido_indicacao").isna().any().any()
    assert anm.numero(",000000") == 0.0 and anm.numero(",00") == 0.0
    assert pd.isna(anm.numero(""))


def test_amb_as_unidades_do_contido_ficam_por_linha_sem_converter():
    bruta = anm.ler_amb_producao_bruta(BRUTA, COLETA)
    ferro = bruta[bruta["substancia"] == "Ferro"].iloc[0]
    assert (ferro["contido_unidade"], ferro["contido_indicacao"], ferro["contido"]) == (
        "t",
        "Fe",
        1200.0,
    )
    assert set(bruta["contido_unidade"]) == {"-", "t"}
    benef = anm.ler_amb_producao_beneficiada(BENEFICIADA, COLETA)
    estanho = benef[benef["substancia"] == "Estanho"].iloc[0]
    assert (estanho["producao_unidade"], estanho["contido_indicacao"]) == ("kg", "Sn")
    assert estanho["producao"] == 4284188.5  # nenhum fator aplicado: kg continua kg
    assert set(benef["producao_unidade"]) == {"t", "kg"}


def test_amb_agua_mineral_em_litros_e_valor_por_embalagem():
    tabela = anm.ler_amb_agua_mineral(AGUA, COLETA)
    primeira = tabela.iloc[0]
    assert (primeira["uf"], primeira["unidade"]) == ("AC", "l")
    assert (
        primeira["litros_garrafao"] == 38315345.0
        and primeira["litros_garrafa_vidro"] == 0.0
    )
    assert set(tabela["ano"]) == {2010, 2025}
    assert tabela[anm.CHAVE_AMB_AGUA].duplicated().sum() == 0


def test_amb_chave_repetida_e_listada_sem_somar_nem_descartar():
    repetida = '"2010","AL","Não-Metálicos","Saibro","1,000000",",000000000000000","-","","1","1",",000000",",000000",",000000",",000000"'
    arquivo = _com_linhas(BRUTA, repetida)
    tabela = anm.ler_amb_producao_bruta(arquivo, COLETA)
    assert len(tabela) == 10  # nada descartado
    repetidas = anm.chaves_repetidas(tabela, anm.CHAVE_AMB_COM_INDICACAO)
    assert list(repetidas["producao_rom_t"]) == [
        10859.12,
        1.0,
    ]  # nada somado, ordem do arquivo
    assert (
        len(
            anm.chaves_repetidas(
                anm.ler_amb_producao_bruta(BRUTA, COLETA), anm.CHAVE_AMB_COM_INDICACAO
            )
        )
        == 0
    )


def test_amb_o_disponivel_em_e_a_coleta_e_nao_o_ano_base():
    for tabela in (
        anm.ler_amb_producao_bruta(BRUTA, COLETA),
        anm.ler_amb_producao_beneficiada(BENEFICIADA, COLETA),
        anm.ler_amb_agua_mineral(AGUA, COLETA),
    ):
        assert (tabela["disponivel_em"] == pd.Timestamp(COLETA)).all()
        assert (
            tabela["disponivel_em"]
            > pd.to_datetime(tabela["ano"].astype(str) + "-12-31")
        ).all()


def test_amb_cabecalho_do_outro_arquivo_e_recusado():
    with pytest.raises(ValueError, match="cabeçalho inesperado"):
        anm.ler_amb_producao_bruta(BENEFICIADA, COLETA)


def test_o_arquivo_em_utf8_tambem_e_aceito_caso_a_anm_mude():
    texto = BRUTA.decode("cp1252")
    assert len(anm.ler_amb_producao_bruta(texto.encode("utf-8-sig"), COLETA)) == 9
