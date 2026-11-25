"""Coleta dos contratos, sanções e fornecedores do SIGA do RJ (linha 1075, lote 1 dos estados).

O SIGA publica três CSVs de endereço fixo em `www.compras.rj.gov.br/siga/imagens/`, regravados inteiros todo dia,
em Latin-1 com ";" (PDDL nos conjuntos do CKAN do estado, lida em 25/11/2026). Aqui se confere o que a coleta
baixa e o que sai **antes** de guardar: só linha de CNPJ inteiro, sem o nome do fornecedor, o objeto, o processo
e o endereço do PNCP, e sem linha com CPF (o SIGA mascara o CPF) em campo nenhum. Os arquivos são de mentira.
"""

import io
from datetime import UTC, datetime

import pytest

from base.arquivo import lote_contratos_estaduais as lote
from base.arquivo import registro
from base.arquivo.fontes import FONTES, POR_ID
from base.arquivo.lote_ordem_cronologica import filtrar_csv
from base.licenca import familia_do_endereco
from src.banco.coletas import Marca, licenca_da_fonte, marca_da_fonte
from tests.test_base_arquivo_lote_ordem_cronologica import Servidor

AGORA = datetime(2026, 11, 25, 22, tzinfo=UTC)
CNPJ = "07.091.063/0001-40"
OUTRO_CNPJ = "00.220.359/0005-06"
CNPJ_DV_ERRADO = "07.091.063/0001-41"
CPF_MASCARADO = "***.000.000-**"
CPF_NO_TEXTO = "888.000.000-46"
NOME_FICTICIO = "FORNECEDOR FICTICIO LTDA"
CABECALHO_DOS_CONTRATOS = (
    "Código do Contrato;ID Processo;ID Licitação;Contratação;Status Contratação;Data Contratação;Unidade;"
    "IDUG;CodUG;Processo;Objeto;Tipo de Aquisição;Critério de Julgamento;Data Início Vigência;"
    "Data Fim Vigência;ID Forn;Fornecedor;CPF/CNPJ;"
    "Valor Total Contrato/Valor Estimado para Contratação (R$);Valor Total Empenhado (R$);"
    "Valor Total Liquidado (R$); Valor Total Pago (R$);Data Public DEORJ;regimejuridico;URL PNCP;"
    "DATA_ASSINATURA;EMERGENCIAL;data_extracao\r\n"
)


def _contrato(
    documento: str, objeto: str = "Serviço de limpeza", codigo: str = "101"
) -> str:
    return (
        f"{codigo};5001;7001;2026000123;Contratado;10/02/2026;SECRETARIA DE SAUDE;12;296100;SEI-1234/2026;"
        f"{objeto};Pregão Eletrônico;Menor Preço;01/03/2026;28/02/2027;900;{NOME_FICTICIO};{documento};"
        "1.234.567,89;500.000,00;400.000,00;350.000,00 ;15/02/2026;Lei 14.133/2021;"
        "https://pncp.gov.br/app/contratos/1/2026/1;12/02/2026;N;25/11/2026\r\n"
    )


def _filtrar(conteudo: str, arquivo: lote.ArquivoFixo) -> str:
    saida = io.BytesIO()
    filtrar_csv(io.BytesIO(conteudo.encode("latin-1")), saida, arquivo.formato)
    return saida.getvalue().decode("utf-8")


def test_contratos_guardam_so_cnpj_inteiro_sem_nome_objeto_processo_nem_pncp():
    guardado = _filtrar(
        CABECALHO_DOS_CONTRATOS
        + _contrato(CNPJ)
        + _contrato(CPF_MASCARADO, codigo="102")
        + _contrato(CNPJ_DV_ERRADO, codigo="103")
        + _contrato(OUTRO_CNPJ, objeto=f"pago a {CPF_NO_TEXTO}", codigo="104"),
        lote.RJ_CONTRATOS,
    )
    linhas = guardado.strip().splitlines()
    assert len(linhas) == 2  # o cabeçalho e o contrato do CNPJ inteiro
    cabecalho = linhas[0]
    assert '"cpf/cnpj"' in cabecalho and '"valor total pago (r$)"' in cabecalho
    for fora in (
        "fornecedor",
        "objeto",
        '"processo"',
        "url pncp",
        "data_extracao",
        "id forn",
    ):
        assert fora not in cabecalho, fora
    for fora in (
        NOME_FICTICIO,
        "limpeza",
        "SEI-1234",
        "pncp.gov.br",
        "***",
        CPF_NO_TEXTO,
    ):
        assert fora not in guardado, fora
    assert CNPJ in guardado and OUTRO_CNPJ not in guardado


def test_sancoes_e_fornecedores_guardam_so_as_colunas_da_lista():
    sancoes = _filtrar(
        "ID Forn;Nome/Razão Social;CPF/CNPJ;Órgão/Entidade Apenadora;Enquadramento Legal;Motivo;Contrato;"
        "Data de Efetivação;Status da Penalidade;data_extracao\r\n"
        f"1;{NOME_FICTICIO};{CNPJ};SEFAZ;Art. 87 da Lei 8.666/93;Inexecução parcial;123/2025;01/06/2025;Vigente;25/11/2026\r\n"
        f"2;{NOME_FICTICIO};{CPF_MASCARADO};SEFAZ;Art. 87;Atraso;9/2025;01/06/2025;Vigente;25/11/2026\r\n",
        lote.RJ_SANCOES,
    )
    fornecedores = _filtrar(
        "ID Forn;Nome/Razão Social;CPF/CNPJ;CRC;Tipo Empresarial;ME/EPP;Situação da Empresa;Data de Cadastro;"
        "Cidade;UF;Data_extracao\r\n"
        f"1;{NOME_FICTICIO};{CNPJ};SIM;Sociedade Limitada;NÃO;Ativo;10/01/2020;Niterói;RJ;25/11/2026\r\n",
        lote.RJ_FORNECEDORES,
    )
    assert sancoes.count("\n") == 2 and fornecedores.count("\n") == 2
    for guardado in (sancoes, fornecedores):
        assert NOME_FICTICIO not in guardado and "nome" not in guardado
        assert "***" not in guardado and "id forn" not in guardado
    assert '"órgão/entidade apenadora"' in sancoes and '"motivo"' in sancoes
    assert '"me/epp"' in fornecedores and '"cidade"' in fornecedores


def test_a_coleta_baixa_so_os_tres_enderecos_fixos_do_siga():
    existem = {
        a.url: CABECALHO_DOS_CONTRATOS.encode("latin-1") for a in lote.ARQUIVOS_FIXOS
    }
    servidor = Servidor(existem)
    for fonte in lote.fontes():
        (alvo,) = fonte.descobrir(servidor, AGORA)
        assert alvo.url.startswith("https://www.compras.rj.gov.br/siga/imagens/")
    assert servidor.pedidos == []  # descobrir não pede nada: os endereços são fixos
    assert {f.id for f in lote.fontes()} == {
        "govrj-contratos",
        "govrj-sancoes",
        "govrj-fornecedores",
    }


def test_sem_a_coluna_do_documento_nada_e_guardado():
    with pytest.raises(ValueError, match="cpf/cnpj"):
        _filtrar("Código do Contrato;Fornecedor\r\n101;X\r\n", lote.RJ_CONTRATOS)


def test_fontes_registradas_com_licenca_pddl_e_familia_do_endereco():
    for arquivo in lote.ARQUIVOS_FIXOS:
        fonte = POR_ID[arquivo.formato.id]
        assert fonte in FONTES
        assert familia_do_endereco(arquivo.url) == "govrj"
        assert "PDDL" in licenca_da_fonte(fonte.id)
        assert marca_da_fonte(fonte.id) is Marca.VENDAVEL
    assert "govrj" in registro.TERMOS_LIDOS_EM
    assert POR_ID["govrj-sancoes"].grupo == lote.SEMANAL
