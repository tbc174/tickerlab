"""Leitores de GO, MS e capital de SP (base/contratos_go_ms_sp.py): só pessoa jurídica, sem nomes.

Recortes no formato dos cabeçalhos medidos em 03/11/2026, com nomes e documentos inventados. CNPJ
11.222.333/0001-81 tem DV certo; ...-82 é o mesmo com DV errado; o CPF 123.456.789-09 é o de documentação.
"""

from datetime import date

from base import contratos_go_ms_sp as t

HOJE = date(2026, 11, 3)
CNPJ = "11222333000181"


def _csv(cabecalho: str, *linhas: str, codificacao: str = "utf-8") -> bytes:
    return "\n".join([cabecalho, *linhas]).encode(codificacao)


def test_go_licencas_fica_so_com_cnpj_valido_e_sem_nomes() -> None:
    corpo = _csv(
        "numero_licenca,versao,nome_empreendimento,nome_razao_social,cpf_cnpj,"
        "municipio_empreendimento,atividade,tipo_licenca,data_emissao,data_validade,status,orgao",
        "123,1,FAZENDA NAO ENTRA,EMPRESA NAO ENTRA,11.222.333/0001-81,Goiânia,ATIV,LO,"
        "2025-05-02,2029-05-02,Vigente,SEMAD",
        "124,1,SITIO,FULANO,***.456.789-**,Anápolis,ATIV,LP,2025-05-03,2026-05-03,Vigente,SEMAD",
        "125,1,X,Y,11222333000182,Jataí,ATIV,LI,2025-05-04,2026-05-04,Vigente,SEMAD",
    )
    lido = t.ler_go_licencas(corpo, HOJE)
    assert lido.descartadas == 2
    (linha,) = lido.linhas
    assert linha["cnpj"] == CNPJ
    assert linha["tipo_licenca"] == "LO"
    assert linha["municipio"] == "Goiânia"
    assert linha["data_emissao"] == "2025-05-02"
    assert linha["data_validade"] == "2029-05-02"
    assert linha["tribunal"] == "go"
    assert linha["disponivel_em"] == "2026-11-03"
    assert "NAO ENTRA" not in str(linha.values())
    assert not {"nome_empreendimento", "nome_razao_social", "atividade"} & set(linha)


def test_ms_descarta_pessoa_fisica_e_nao_le_o_nome_do_credor() -> None:
    cabecalho = (
        "_id,Orgão,Natureza de Despesa,Programa,Função,Sub-Função,Ação,Categoria,Grupo de Despesa,"
        "Modalidade,Elemento de Despesa,Cpf/Cnpj,Credor,Documento,Tipo de Licitação,"
        "Empenhado,Liquidado,Pago"
    )
    resto = "x,x,Saúde,Assistência,x,x,x,Direta,Material"
    corpo = _csv(
        cabecalho,
        f"1,SES,{resto},{CNPJ},EMPRESA NAO ENTRA,2016NE000123,Dispensa,1000.50,900.00,800.00",
        f"2,SES,{resto},123.456.789-09,PESSOA FISICA,2016NE000124,Dispensa,10,10,10",
        f"3,SES,{resto},***456789**,OUTRA PF,2016NE000125,Dispensa,10,10,10",
    )
    lido = t.ler_ms_despesas(corpo, 2016, 11, HOJE)
    assert lido.descartadas == 2
    (linha,) = lido.linhas
    assert linha["cnpj"] == CNPJ
    assert (linha["ano"], linha["mes"]) == ("2016", "11")
    assert (linha["empenhado"], linha["liquidado"], linha["pago"]) == (
        1000.5,
        900.0,
        800.0,
    )
    assert linha["numero_documento"] == "2016NE000123"
    assert "NAO ENTRA" not in str(linha.values())


def test_sp_capital_acha_o_cabecalho_por_apelido_em_cp1252_e_ponto_e_virgula() -> None:
    corpo = _csv(
        "Número do Contrato;Processo;Órgão;CNPJ;Razão Social;Objeto;Data de Assinatura;"
        "Início Vigência;Fim Vigência;Valor Total",
        f"001/2024;6010.2024/0001;SMS;{CNPJ};EMPRESA NAO ENTRA;OBJETO NAO ENTRA;"
        "02/01/2024;03/01/2024;02/01/2025;1.234,56",
        "002/2024;6010.2024/0002;SMS;123.456.789-09;PF;OBJ;02/01/2024;03/01/2024;02/01/2025;10,00",
        codificacao="cp1252",
    )
    lido = t.ler_sp_capital_contratos(corpo, HOJE)
    assert lido.descartadas == 1
    (linha,) = lido.linhas
    assert linha["cnpj"] == CNPJ
    assert linha["numero_contrato"] == "001/2024"
    assert linha["orgao"] == "SMS"
    assert linha["data_assinatura"] == "2024-01-02"
    assert linha["vigencia_fim"] == "2025-01-02"
    assert linha["valor"] == 1234.56
    assert linha["tribunal"] == "sp_capital"
    assert "NAO ENTRA" not in str(linha.values())


def test_arquivo_sem_linhas_devolve_leitura_vazia() -> None:
    lido = t.ler_go_licencas(b"cpf_cnpj,numero_licenca\n", HOJE)
    assert lido.linhas == []
    assert lido.descartadas == 0


def test_sp_capital_pula_as_linhas_de_titulo_e_le_o_cabecalho_real_de_2024() -> None:
    vazia = ";".join(['""'] * 9)
    corpo = _csv(
        '﻿"PREFEITURA DO MUNICÍPIO DE SÃO PAULO";"";"";"";"";"";"";"";""',
        '"Contratos da Prefeitura do Município de São Paulo";"";"";"";"";"";"";"";""',
        vazia,
        '"Nome do Órgão";"Contrato";"Data da Assinatura";"Vigência (dias/mês)";"Objeto";'
        '"Modalidade";"Processo Administrativo";"CNPJ/CPF";"Fornecedor e Nome de Fantasia";'
        '"Valor(R$)"',
        '"SECRETARIA X";"273";"21/12/2023";"12 M";"OBJETO NAO ENTRA";"DISPENSA  ";'
        '"6022.2023/0005315-6";"11.222.333/0001-81";"EMPRESA NAO ENTRA";"36.500,00"',
        '"SECRETARIA X";"274";"21/12/2023";"12 M";"OBJ";"DISPENSA";"6022.2023/1";'
        '"123.456.789-09";"PF NAO ENTRA";"10,00"',
    )
    lido = t.ler_sp_capital_contratos(corpo, HOJE)
    assert lido.descartadas == 1
    (linha,) = lido.linhas
    assert linha["cnpj"] == CNPJ
    assert linha["numero_contrato"] == "273"
    assert linha["orgao"] == "SECRETARIA X"
    assert linha["numero_processo"] == "6022.2023/0005315-6"
    assert linha["data_assinatura"] == "2023-12-21"
    assert linha["valor"] == 36500.0
    assert "NAO ENTRA" not in str(linha.values())
