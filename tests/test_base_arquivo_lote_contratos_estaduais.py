"""Coleta dos contratos, sanções e fornecedores do SIGA do RJ (linha 1075, lote 1 dos estados).

O SIGA publica três CSVs de endereço fixo em `www.compras.rj.gov.br/siga/imagens/`, regravados inteiros todo dia,
em Latin-1 com ";" (PDDL nos conjuntos do CKAN do estado, lida em 25/11/2026). Aqui se confere o que a coleta
baixa e o que sai **antes** de guardar: só linha de CNPJ inteiro, sem o nome do fornecedor, o objeto, o processo
e o endereço do PNCP, e sem linha com CPF (o SIGA mascara o CPF) em campo nenhum. Os arquivos são de mentira.
"""

import csv
import io
from datetime import UTC, datetime

import pytest

from base.arquivo import lote_contratos_estaduais as lote
from base.arquivo import registro
from base.arquivo.fontes import FONTES, POR_ID
from base.arquivo.lote_ordem_cronologica import filtrar_csv
from base.licenca import familia_do_endereco
from src.banco.coletas import Marca, licenca_da_fonte, marca_da_fonte
from tests.test_base_arquivo_lote_ordem_cronologica import Servidor, _pagina

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


def test_o_siga_e_baixado_so_dos_enderecos_fixos():
    servidor = Servidor({})
    for arquivo in lote.ARQUIVOS_FIXOS:
        (alvo,) = POR_ID[arquivo.formato.id].descobrir(servidor, AGORA)
        assert alvo.url == arquivo.url
        assert alvo.url.startswith("https://www.compras.rj.gov.br/siga/imagens/")
    assert servidor.pedidos == []  # descobrir não pede nada: os endereços são fixos
    assert {f.id for f in lote.fontes()} == {
        "govrj-contratos",
        "govrj-sancoes",
        "govrj-fornecedores",
        "govrj-compras-diretas",
        "esdados-contratos",
        "esdados-empenhos",
    }


PAGINA_DO_ES = "https://dados.es.gov.br/dataset/portal-da-transparencia-contratos"
RECURSO_DO_ES = "https://dados.es.gov.br/dataset/x/resource/{}/download/{}"


def test_o_es_e_descoberto_pela_pagina_e_o_nome_do_arquivo_escolhe_o_conjunto():
    """O pacote do ES junta contratos, empenhos, aditivos e comissões; link de fora do portal é ignorado."""
    enderecos = [
        RECURSO_DO_ES.format("a", "contratos-2025.csv"),
        RECURSO_DO_ES.format("b", "empenhos-2025.csv"),
        RECURSO_DO_ES.format("c", "alteracoescontratuais-2025.csv"),
        RECURSO_DO_ES.format("d", "comissoes-2025.csv"),
        RECURSO_DO_ES.format("e", "contratos-2024.csv"),
        "https://outro.exemplo/dataset/x/resource/f/download/contratos-2023.csv",
    ]
    servidor = Servidor({PAGINA_DO_ES: _pagina(*enderecos)})
    contratos = POR_ID["esdados-contratos"].descobrir(servidor, AGORA)
    empenhos = POR_ID["esdados-empenhos"].descobrir(servidor, AGORA)
    assert [a.url for a in contratos] == [enderecos[0], enderecos[4]]
    assert [a.url for a in empenhos] == [enderecos[1]]
    assert set(servidor.pedidos) == {PAGINA_DO_ES}  # a página, nunca a /api/ do CKAN
    assert POR_ID["esdados-contratos"].pausa_minima == 10.0  # Crawl-Delay do robots


def _filtrar_utf8(conteudo: str, formato) -> str:
    saida = io.BytesIO()
    filtrar_csv(io.BytesIO(conteudo.encode("utf-8")), saida, formato)
    return saida.getvalue().decode("utf-8")


def test_contratos_do_es_saem_sem_fornecedor_objeto_nem_linha_de_cpf():
    cabecalho = (
        "\ufeffIdOrgao;NomeOrgao;NumeroProcesso;ModalidadeProcesso;NumeroEdital;NumeroDocumento;TipoDocumento;"
        "Fornecedor;CnpjFornecedor;Objeto;TipoAquisicao;Situacao;DataCelebracao;DataInicioVigencia;"
        "DataFimVigencia;ValorInicial;ValorFinal;eRegistroPreco;procRealizadoSiga;orgaoOrigemProcesso;"
        "justificativaProcForaSiga;numProcUtilizacao;origem;origemContrato;idOrigem;CnpjFormatado;Id\r\n"
    )

    def linha(documento: str, ident: str) -> str:
        return (
            f"12;SECRETARIA DE SAUDE;2025-ABCDE;Pregão Eletrônico;001/2025;Contrato 001/2025;Contrato;"
            f"{NOME_FICTICIO};{documento};Serviço de limpeza;Serviço;Celebrado;10/02/2025 00:00:00;;;"
            f"1000,50;1200,00;N;S;;;;1;1;{ident};{CNPJ};{ident}\r\n"
        )

    guardado = _filtrar_utf8(
        cabecalho + linha("07091063000140", "1") + linha("88800000046", "2"),
        lote.ES_CONTRATOS,
    )
    assert guardado.count("\r\n") == 2  # o cabeçalho e a linha do CNPJ
    for fora in (
        NOME_FICTICIO,
        "limpeza",
        "88800000046",
        "cnpjformatado",
        "fornecedor;",
        "objeto",
    ):
        assert fora not in guardado, fora
    assert '"cnpjfornecedor"' in guardado and '"valorfinal"' in guardado


def test_empenhos_do_es_saem_sem_o_nome_do_fornecedor():
    cabecalho = (
        "NumeroProcesso;NumeroDocumento;TipoDocumento;Id;NumeroEmpenho;valorGlobal;saldo;nomeFornecedor;"
        "cnpjFornecedor;TipoEmpenho;situacao;fonteRecurso;programaTrabalho;naturezaDespesa\r\n"
    )
    guardado = _filtrar_utf8(
        cabecalho
        + f"2025-ABCDE;Contrato 001/2025;Contrato;10;2025NE00001;500,00;;{NOME_FICTICIO};07091063000140;;;;;\r\n",
        lote.ES_EMPENHOS,
    )
    assert guardado.count("\r\n") == 2
    assert NOME_FICTICIO not in guardado and "nomefornecedor" not in guardado
    assert '"numeroempenho"' in guardado


def test_compras_diretas_do_rj_saem_sem_processo_objeto_enquadramento_nem_item():
    cabecalho = (
        "Unidade;ID Processo;Processo;Objeto;Afastamento;Enquadramento Legal;Data de Aprovação;"
        "Valor do Processo (R$);CNPJ_CPF;ID Forn;Fornecedor Vencedor;ID Item;Item;Qtd.;Unidade de Medida;"
        "Vl. Unitário (R$);PED;Regime;Temporalidade;Data_extracao;\r\n"
    )

    def linha(documento: str) -> str:
        return (
            f"SES - SECRETARIA DE SAUDE;9001;SEI-1234/2025;Compra de canetas;Dispensa - Pequeno valor;"
            f"Art. 75, II;10/03/2025;1.500,00;{documento};77;{NOME_FICTICIO};555;CANETA AZUL;100;UN;15,00;"
            "NAO;Lei 14.133/2021;12;25/11/2026;\r\n"
        )

    guardado = _filtrar(
        cabecalho + linha(CNPJ) + linha(CPF_MASCARADO), lote.RJ_COMPRAS_DIRETAS
    )
    assert guardado.count("\r\n") == 2
    for fora in (NOME_FICTICIO, "canetas", "CANETA", "SEI-1234", "Art. 75", "***"):
        assert fora not in guardado, fora
    assert '"vl. unitário (r$)"' in guardado and '"id item"' in guardado


def test_sem_a_coluna_do_documento_nada_e_guardado():
    with pytest.raises(ValueError, match="cpf/cnpj"):
        _filtrar("Código do Contrato;Fornecedor\r\n101;X\r\n", lote.RJ_CONTRATOS)


def test_fontes_registradas_com_licenca_e_familia_do_endereco():
    for arquivo in lote.ARQUIVOS_FIXOS:
        fonte = POR_ID[arquivo.formato.id]
        assert fonte in FONTES
        assert familia_do_endereco(arquivo.url) == "govrj"
        assert "PDDL" in licenca_da_fonte(fonte.id)
        assert marca_da_fonte(fonte.id) is Marca.VENDAVEL
    assert "govrj" in registro.TERMOS_LIDOS_EM
    assert POR_ID["govrj-sancoes"].grupo == lote.SEMANAL
    for formato in lote.CONJUNTOS_DO_ES:
        assert POR_ID[formato.id] in FONTES
        assert (
            familia_do_endereco(RECURSO_DO_ES.format("a", "contratos-2025.csv"))
            == "esdados"
        )
        assert "CC BY" in licenca_da_fonte(formato.id)
        assert marca_da_fonte(formato.id) is Marca.VENDAVEL


def test_ponto_e_virgula_so_no_fim_do_cabecalho_nao_derruba_as_linhas():
    """O COMPRAS_DIRETAS.CSV de 25/11/2026 traz ";" no fim do cabeçalho (21 nomes, o último vazio) e não nas
    linhas (20 campos): o filtro tirava toda linha por ter uma coluna a menos, e a coleta guardava só o
    cabeçalho. A coluna sem nome do fim não conta; linha com um campo vazio a mais no fim também passa, e com
    um campo cheio a mais sai (não dá para saber qual coluna é qual)."""
    cabecalho = (
        "Unidade;ID Processo;Afastamento;Data de Aprovação;Valor do Processo (R$);CNPJ_CPF;ID Item;Qtd.;"
        "Unidade de Medida;Vl. Unitário (R$);PED;Regime;Temporalidade;\r\n"
    )

    def linha(item: str, fim: str = "") -> str:
        return f"SES;9001;Dispensa;10/03/2025;1.500,00;{CNPJ};{item};100;UN;15,00;NAO;Lei 14.133/2021;12{fim}\r\n"

    guardado = _filtrar(
        cabecalho + linha("555") + linha("556", ";") + linha("557", ";SOBRA"),
        lote.RJ_COMPRAS_DIRETAS,
    )
    lido = list(csv.reader(io.StringIO(guardado), delimiter=";"))
    assert lido[0] == [
        n for n in lote.RJ_COMPRAS_DIRETAS.formato.guardadas if n in lido[0]
    ]
    assert len(lido[0]) == 13
    assert [r[lido[0].index("id item")] for r in lido[1:]] == ["555", "556"]
