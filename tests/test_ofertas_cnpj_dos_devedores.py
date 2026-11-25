"""Linha 1034: o CNPJ do devedor (ou coobrigado) de cada requerimento de oferta pela Resolução 160.

O informe mensal da CVM não traz cedente nem devedor de todo certificado de CRA (em 2024, 249 dos 755 não têm
nenhuma linha). Nesses casos o CNPJ da empresa só aparece no texto livre `Identificacao_devedores_coobrigados`
do requerimento de oferta, que a base inteira tirava por poder citar pessoa. `ler_cnpj_dos_devedores` tira só
os CNPJ de empresa desse texto (nunca o texto, nunca CPF) e deixa a empresa achável pela raiz.
"""

import io
import re
import zipfile

import pandas as pd
import pytest

from base import ofertas
from base.porta import Porta
from base.raizes_de_empresa import RaizesDeEmpresa
from tests.ajudantes_de_cpf import cpf_que_confere, no_formato

ATLAS = "22.875.049/0001-20"
OUTRA = "11.222.333/0001-81"
SECURITIZADORA = "26.609.050/0001-64"
CPF = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}")
# CPF que confere, montado na hora (nenhum arquivo do repositório guarda um: tests/ajudantes_de_cpf.py)
UM_CPF = no_formato(cpf_que_confere("888777666"), "ddd.ddd.ddd-dd")
CABECALHO = (
    "Numero_Requerimento;Numero_Processo;Data_requerimento;Data_Registro;Data_Encerramento;"
    "Valor_Mobiliario;CNPJ_Emissor;Nome_Emissor;Emissao;Identificacao_devedores_coobrigados"
)


def _zip(*requerimentos: tuple[str, str, str]) -> bytes:
    """Um ZIP da CVM com `oferta_resolucao_160.csv`: (número, registro, texto dos devedores) por linha."""
    linhas = [CABECALHO]
    for numero, registro, devedores in requerimentos:
        linhas.append(
            f"{numero};SRE/{numero}/2024;2024-06-28;{registro};2024-12-16;"
            f"Certificados de Recebíveis do Agronegócio;{SECURITIZADORA};TRAVESSIA SECURITIZADORA S.A.;1;{devedores}"
        )
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        arquivo.writestr(
            ofertas.RESOLUCAO_160, "\r\n".join(linhas).encode("latin-1") + b"\r\n"
        )
    return saida.getvalue()


def _cnpjs(tabela: pd.DataFrame) -> list[str]:
    return sorted(tabela["cnpj"])


def test_o_cnpj_do_devedor_sai_do_texto_do_requerimento():
    zip_da_cvm = _zip(
        ("16392", "2024-07-01", f"Devedora: Atlas Agro S.A. (CNPJ: {ATLAS})")
    )
    tabela = ofertas.ler_cnpj_dos_devedores(zip_da_cvm)
    assert _cnpjs(tabela) == [ATLAS]
    linha = tabela.iloc[0]
    assert linha["cnpj_emissor"] == SECURITIZADORA
    assert linha["numero_processo"] == "SRE/16392/2024"
    assert linha["valor_mobiliario"] == "Certificados de Recebíveis do Agronegócio"


def test_nenhum_texto_do_requerimento_e_nenhum_cpf_vai_para_a_tabela():
    texto = f"Produtor FICTICIO DA SILVA CPF {UM_CPF} e a empresa {ATLAS}"
    tabela = ofertas.ler_cnpj_dos_devedores(_zip(("1", "2024-07-01", texto)))
    assert _cnpjs(tabela) == [ATLAS]
    assert "identificacao_devedores_coobrigados" not in tabela.columns
    for coluna in tabela.columns:
        valores = tabela[coluna].astype(str)
        assert not valores.str.contains(CPF).any(), coluna
        assert not valores.str.contains("FICTICIO").any(), coluna


def test_requerimento_so_com_cpf_ou_sem_texto_nao_gera_linha():
    zip_da_cvm = _zip(
        ("1", "2024-07-01", f"Produtor rural CPF {UM_CPF}"),
        ("2", "2024-07-01", ""),
    )
    assert ofertas.ler_cnpj_dos_devedores(zip_da_cvm).empty


def test_um_requerimento_com_dois_cnpjs_vira_duas_linhas_e_o_repetido_conta_uma_vez():
    texto = f"{ATLAS}, {OUTRA}, de novo {ATLAS}"
    tabela = ofertas.ler_cnpj_dos_devedores(_zip(("1", "2024-07-01", texto)))
    assert _cnpjs(tabela) == sorted([ATLAS, OUTRA])


def test_cnpj_com_digito_verificador_errado_ou_sem_pontuacao_fica_de_fora():
    errado = "22.875.049/0001-21"
    solto = "22875049000120"  # 14 dígitos soltos podem ser outra coisa: só vale o formato de CNPJ
    texto = f"{errado} e {solto}"
    assert ofertas.ler_cnpj_dos_devedores(_zip(("1", "2024-07-01", texto))).empty


def test_o_proprio_emissor_citado_no_texto_nao_e_devedor():
    tabela = ofertas.ler_cnpj_dos_devedores(
        _zip(("1", "2024-07-01", f"{SECURITIZADORA} e {ATLAS}"))
    )
    assert _cnpjs(tabela) == [ATLAS]


def test_requerimento_sem_registro_nao_entra_e_a_data_publica_e_a_da_oferta():
    zip_da_cvm = _zip(
        ("1", "2024-07-01", ATLAS),
        ("2", "", OUTRA),  # em análise: ainda não era público
    )
    tabela = ofertas.ler_cnpj_dos_devedores(zip_da_cvm)
    assert _cnpjs(tabela) == [ATLAS]
    linha = tabela.iloc[0]
    assert linha["anunciada_em"] == pd.Timestamp("2024-07-01")
    assert linha["disponivel_em"] == pd.Timestamp(
        "2024-12-16"
    )  # o encerramento: a linha inteira


def test_cnpj_alfanumerico_valido_entra():
    alfa = "12.ABC.345/01DE-35"  # o exemplo oficial da Receita (base/cnpj.py)
    tabela = ofertas.ler_cnpj_dos_devedores(_zip(("1", "2024-07-01", f"CNPJ {alfa}")))
    assert _cnpjs(tabela) == [alfa]


# --- só empresa: MEI, empresário individual e raiz sem Receita não entram (ADR 0075) ----------------------
def test_so_fica_o_devedor_cuja_raiz_esta_na_lista_de_empresas():
    tabela = ofertas.ler_cnpj_dos_devedores(
        _zip(("1", "2024-07-01", f"{ATLAS} e {OUTRA}"))
    )
    empresas = RaizesDeEmpresa.de_lista(
        ["22875049"]
    )  # a outra raiz é de MEI ou sem Receita
    assert _cnpjs(ofertas.so_devedor_de_empresa(tabela, empresas)) == [ATLAS]


def test_lista_de_empresas_vazia_recusa_em_vez_de_apagar_tudo():
    tabela = ofertas.ler_cnpj_dos_devedores(_zip(("1", "2024-07-01", ATLAS)))
    with pytest.raises(ValueError, match="lista de empresas"):
        ofertas.so_devedor_de_empresa(tabela, RaizesDeEmpresa.de_lista([]))


def test_tabela_vazia_continua_vazia_com_as_mesmas_colunas():
    tabela = ofertas.ler_cnpj_dos_devedores(_zip(("1", "2024-07-01", "")))
    saida = ofertas.so_devedor_de_empresa(
        tabela, RaizesDeEmpresa.de_lista(["22875049"])
    )
    assert saida.empty
    assert list(saida.columns) == list(ofertas.COLUNAS_DOS_DEVEDORES)


# --- a empresa pela porta: as duas emissões da Atlas Agro, sem olhar o futuro --------------------------------
def _acervo_com_as_duas_emissoes(pasta) -> None:
    """O CRA de 2022 (informe mensal da Opea) e o de 2024 (requerimento da Travessia), como na base real."""
    informe = pd.DataFrame(
        {
            "competencia": pd.to_datetime(["2022-07-01", "2023-07-01"]),
            "cnpj_securitizadora": "02.773.542/0001-22",
            "codigo_certificado": "BRRBRACRA256",
            "produto": "CRA",
            "disponivel_em": pd.to_datetime(["2022-09-01", "2023-10-11"]),
            "papel": "devedor",
            "cnpj": ATLAS,
        }
    )
    requerimento = ofertas.ler_cnpj_dos_devedores(
        _zip(("16392", "2024-07-01", f"Devedora Atlas Agro (CNPJ: {ATLAS})"))
    )
    for caminho, tabela in (
        ("securitizacao_cedente_devedor/2022.parquet", informe),
        ("ofertas/cnpj_dos_devedores.parquet", requerimento),
    ):
        arquivo = pasta / caminho
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        tabela.to_parquet(arquivo, index=False)


def test_as_duas_emissoes_da_atlas_agro_aparecem_pelo_cnpj_dela(tmp_path):
    _acervo_com_as_duas_emissoes(tmp_path)
    with Porta(tmp_path) as porta:
        do_informe = porta.ler("securitizacao_cedente_devedor", filtros={"cnpj": ATLAS})
        do_requerimento = porta.ler(
            "ofertas_cnpj_dos_devedores", filtros={"cnpj": ATLAS}
        )
    assert set(do_informe["codigo_certificado"]) == {
        "BRRBRACRA256"
    }  # a 1ª emissão (2022)
    assert list(do_requerimento["numero_processo"]) == ["SRE/16392/2024"]  # a 2ª (2024)
    assert list(do_requerimento["cnpj_emissor"]) == [SECURITIZADORA]


def test_o_requerimento_so_vale_depois_de_ficar_publico(tmp_path):
    _acervo_com_as_duas_emissoes(tmp_path)
    with Porta(tmp_path) as porta:
        antes = porta.ler(
            "ofertas_cnpj_dos_devedores",
            como_era_em="2024-12-15",  # o dia antes do encerramento: a linha inteira ainda não era pública
            filtros={"cnpj": ATLAS},
        )
        depois = porta.ler(
            "ofertas_cnpj_dos_devedores",
            como_era_em="2024-12-16",
            filtros={"cnpj": ATLAS},
        )
    assert antes.empty
    assert len(depois) == 1
