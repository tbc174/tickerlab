"""ESTBAN do BCB: leitura do ZIP, chave, verbetes somados e o `disponivel_em` sem olhar o futuro."""

import io
import zipfile
from datetime import date

import pandas as pd
import pytest

from base import estban

CABECALHO = (
    "#DATA_BASE;UF;CODMUN;MUNICIPIO;CNPJ;NOME_INSTITUICAO;AGENCIA;"
    "VERBETE_160_OPERACOES_DE_CREDITO;"
    "VERBETE_141_CORRESPONDENTES_NO_EXTERIOR + VERBETE_142_CORRESPONDENTES_NO_PAIS;"
    "VERBETE_144_COBRANCA_EM_TRANSITO + VERBETE_145_ORDENS_DE_PAGAMENTO\t+ VERBETE_146_VAL_LIGADAS;"
    "VERBETE_420_DEPOSITOS_DE_POUPANCA;CODMUN_IBGE"
)
LINHAS = [
    "202512;AC;50830;ACRELANDIA;00000000;BCO DO BRASIL S.A.;'00000000517569;1000;5;-3;70;1200013",
    "202512;AC;9465;ASSIS BRASIL;00360305;CAIXA ECONOMICA FEDERAL;'00360305358920;250;0;7;30;1200054",
    "202512;SP;71072;SAO PAULO;00360305;CAIXA ECONOMICA FEDERAL;'00360305000100;900;1;2;40;3550308",
    "202512;SP;71072;SAO PAULO;60746948;BCO BRADESCO S.A.;'60746948000112;800;1;2;60;3550308",
]


def _zip(
    linhas=LINHAS, geracao="2026-08-03", cabecalho=CABECALHO, competencia="202512"
):
    texto = "\n".join(
        [
            "ESTBAN (Documento 4500) por agencia",
            f"Data de geracao dos dados: {geracao}",
            cabecalho,
            *linhas,
            "",
        ]
    )
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as arquivo:
        arquivo.writestr(f"{competencia}_ESTBAN_AG.CSV", texto.encode("cp1252"))
    return saida.getvalue()


def test_le_a_identificacao_e_tira_o_apostrofo_da_agencia():
    tabela = estban.ler_competencia(_zip())
    primeira = tabela.iloc[0]
    assert primeira["competencia"] == 202512
    assert primeira["agencia"] == "00000000517569"
    assert primeira["cnpj_raiz"] == "00000000"
    assert primeira["codigo_ibge_municipio"] == "1200013"
    assert primeira["instituicao"] == "BCO DO BRASIL S.A."
    assert len(tabela) == 4


def test_verbetes_somados_ganham_o_codigo_de_todos_os_termos():
    tabela = estban.ler_competencia(_zip())
    assert estban.colunas_de_verbete(tabela) == [
        "verbete_160",
        "verbete_141_142",
        "verbete_144_145_146",
        "verbete_420",
    ]
    assert tabela["verbete_144_145_146"].tolist() == [-3, 7, 2, 2]
    assert estban.codigo_do_verbete("VERBETE_141_X + VERBETE_142_Y") == "141+142"


def test_valores_negativos_sao_mantidos_e_o_tipo_e_inteiro():
    tabela = estban.ler_competencia(_zip())
    assert str(tabela["verbete_160"].dtype) == "Int64"
    assert tabela["verbete_144_145_146"].min() == -3


def test_chave_repetida_levanta_erro():
    with pytest.raises(ValueError, match="repetida"):
        estban.ler_competencia(_zip([LINHAS[0], LINHAS[0]]))


def test_mistura_de_competencias_levanta_erro():
    outra = LINHAS[1].replace("202512", "202511")
    with pytest.raises(ValueError, match="mistura"):
        estban.ler_competencia(_zip([LINHAS[0], outra]))


def test_sem_data_de_geracao_ou_sem_cabecalho_levanta_erro():
    sem_geracao = zipfile.ZipFile(io.BytesIO(_zip()))
    texto = sem_geracao.read("202512_ESTBAN_AG.CSV").decode("cp1252")
    texto = texto.replace("Data de geracao dos dados: 2026-08-03", "outra coisa")
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        arquivo.writestr("202512_ESTBAN_AG.CSV", texto.encode("cp1252"))
    with pytest.raises(ValueError, match="geração"):
        estban.ler_competencia(saida.getvalue())
    with pytest.raises(ValueError, match="cabeçalho"):
        estban.ler_competencia(_zip(cabecalho="DATA_BASE;UF"))


def test_zip_com_mais_de_um_arquivo_levanta_erro():
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        arquivo.writestr("a.csv", b"x")
        arquivo.writestr("b.csv", b"y")
    with pytest.raises(ValueError, match="1 arquivo"):
        estban.ler_competencia(saida.getvalue())


def test_acentos_em_cp1252_voltam_certos():
    linha = LINHAS[0].replace("ACRELANDIA", "SÃO JOÃO D'OESTE")
    tabela = estban.ler_competencia(_zip([linha]))
    assert tabela.loc[0, "municipio"] == "SÃO JOÃO D'OESTE"


def test_disponivel_em_e_a_data_de_geracao_do_preambulo():
    tabela = estban.ler_competencia(_zip(geracao="2026-08-03"))
    assert tabela["gerado_em"].iloc[0] == pd.Timestamp("2026-08-03")
    assert tabela["disponivel_em"].iloc[0] == pd.Timestamp("2026-08-03")


def test_disponivel_em_considera_a_modificacao_no_servidor():
    assert estban.disponivel_em(date(2026, 10, 1), date(2026, 10, 13)) == pd.Timestamp(
        "2026-10-13"
    )
    assert estban.disponivel_em(date(2026, 10, 1)) == pd.Timestamp("2026-10-01")
    tabela = estban.ler_competencia(_zip(), modificado_em=date(2026, 8, 4))
    assert tabela["disponivel_em"].iloc[0] == pd.Timestamp("2026-08-04")


def test_sem_olhar_o_futuro_nada_e_publico_antes_da_data_base():
    tabela = estban.ler_competencia(_zip())
    assert (tabela["disponivel_em"] > tabela["data_base"]).all()
    assert (estban.atraso_de_publicacao_em_dias(tabela) == 215).all()  # 31/12 a 03/08


def test_nao_usa_data_base_mais_prazo_fixo():
    cedo = estban.ler_competencia(_zip(geracao="2026-08-03"))["disponivel_em"].iloc[0]
    assert cedo > pd.Timestamp("2025-12-01") + pd.Timedelta(days=90)


def test_formato_longo_tem_uma_linha_por_verbete_e_preserva_a_soma():
    tabela = estban.ler_competencia(_zip())
    longa = estban.em_formato_longo(tabela)
    assert len(longa) == len(tabela) * 4
    assert set(longa["verbete"]) == {"160", "141+142", "144+145+146", "420"}
    assert not longa.duplicated(estban.CHAVE_LONGA).any()
    assert longa.loc[longa["verbete"] == "160", "saldo"].sum() == 2950


def test_por_municipio_soma_as_instituicoes():
    tabela = estban.ler_competencia(_zip())
    saldo = estban.por_municipio(tabela, estban.VERBETE_CREDITO)
    sao_paulo = saldo[saldo["codigo_ibge_municipio"] == "3550308"].iloc[0]
    assert sao_paulo["saldo"] == 1700
    assert sao_paulo["agencias"] == 2
    assert sao_paulo["verbete"] == "160"


def test_endereco_da_competencia():
    assert estban.endereco_da_competencia(202606).endswith("/202606_ESTBAN_AG.csv.zip")


def test_mesmo_codigo_de_agencia_em_instituicoes_diferentes_nao_e_repetida():
    """No arquivo real de 202602, 4 instituições têm a agência `00000000000191` em Brasília."""
    linhas = [
        "202512;DF;35800;BRASILIA;04902979;BCO DA AMAZONIA S.A.;'00000000000191;10;0;0;0;5300108",
        "202512;DF;35800;BRASILIA;13009717;BCO DO EST. DE SE S.A.;'00000000000191;20;0;0;0;5300108",
    ]
    assert len(estban.ler_competencia(_zip(linhas))) == 2
