"""Leitores dos contratos dos TCEs (base/contratos_tces.py): só pessoa jurídica, sem nomes nem CPF.

Recortes no formato real medido em 03/11/2026, com nomes e documentos inventados. CNPJ
11.222.333/0001-81 tem DV certo; ...-82 é o mesmo com DV errado; o CPF 123.456.789-09 é o de
documentação.
"""

import io
import json
import zipfile
from datetime import date

from base import contratos_tces as t

HOJE = date(2026, 11, 3)
CNPJ = "11222333000181"
CNPJ_RUIM = "11222333000182"
CPF14 = "00012345678909"


def _pe(itens: list[dict]) -> bytes:
    corpo = {"resposta": {"status": "OK", "conteudo": itens}}
    return json.dumps(corpo, ensure_ascii=False).encode("iso-8859-1")


def test_pe_contratos_filtra_pelo_documento_ajustado_e_ignora_tipo_de_credor() -> None:
    itens = [
        {
            "NumeroDocumentoAjustado": CNPJ + "  ",
            "CodigoContrato": "10235923",
            "NumeroContrato": "014",
            "AnoContrato": "2025",
            "Valor": "10000.00",
            "Vigencia": "12/03/2025 a 12/07/2025",
            "Situacao": "Concluído",
            "RazaoSocial": "NÃO ENTRA",
            "Objeto": "NÃO ENTRA",
            "TipoCredor": "2",
        },
        {"NumeroDocumentoAjustado": CPF14, "TipoCredor": "2"},
        {"NumeroDocumentoAjustado": CNPJ_RUIM},
    ]
    lido = t.ler_pe(_pe(itens), "contratos", HOJE)
    assert lido.descartadas == 2
    (linha,) = lido.linhas
    assert linha["cnpj"] == CNPJ
    assert linha["valor"] == 10000.0
    assert linha["vigencia_inicio"] == "2025-03-12"
    assert linha["vigencia_fim"] == "2025-07-12"
    assert linha["situacao"] == "Concluído"
    assert linha["disponivel_em"] == "2026-11-03"
    assert not {"RazaoSocial", "Objeto", "razao_social", "objeto", "TipoCredor"} & set(
        linha
    )


def test_pe_aditivos() -> None:
    aditivo = {
        "NumeroDocumentoAjustado": CNPJ,
        "CodigoContrato": "434774",
        "NumeroTermoAditivo": "001",
        "AnoTermoAditivo": "2024",
        "Vigencia": "12/02/2019 a 11/02/2025",
        "JustificativaTermoAditivo": "NÃO ENTRA",
    }
    (linha,) = t.ler_pe(_pe([aditivo]), "aditivos", HOJE).linhas
    assert linha["numero_aditivo"] == "001"
    assert "JustificativaTermoAditivo" not in linha


def test_pe_licitacoes_so_o_vencedor_com_cnpj_e_sem_razao_social_nem_objeto() -> None:
    vencedor = {
        "NUMERODOCUMENTOAJUSTADO": f"{CNPJ}      ",
        "ADJUDICADA": "Vencedor",
        "CODIGOPL": "60089744",
        "CODIGOMODALIDADE": "11",
        "TOTALADJUDICADOLICITANTE": "3700.0000",
        "VALORORCAMENTOESTIMATIVO": "3700.000000000",
        "DATAEMISSAOEDITAL": "2025-06-10 00:00:00.0",
        "RAZAOSOCIAL": "NÃO ENTRA",
        "DESCRICAOOBJETO": "NÃO ENTRA",
    }
    itens = [
        vencedor,
        {**vencedor, "ADJUDICADA": "Não Vencedor"},
        {**vencedor, "NUMERODOCUMENTOAJUSTADO": "***.***.004-02"},
        {**vencedor, "NUMERODOCUMENTOAJUSTADO": "11222333000182"},
    ]
    leitura = t.ler_pe_licitacoes(_pe(itens), HOJE)
    (linha,) = leitura.linhas
    assert leitura.descartadas == 3
    assert linha["cnpj"] == CNPJ
    assert linha["valor_adjudicado"] == 3700.0
    assert linha["data_edital"] == "2025-06-10"
    assert linha["disponivel_em"] == "2026-11-03"
    assert not {"RAZAOSOCIAL", "DESCRICAOOBJETO", "razao_social", "objeto"} & set(linha)
    assert t.ler_pe_licitacoes(_pe([]), HOJE).linhas == []


def test_sp_so_cnpj_e_valor_com_virgula_sem_nome_do_fornecedor() -> None:
    registros = [
        {
            "orgao": "PREFEITURA",
            "mes": "Janeiro",
            "evento": "Empenhado",
            "nr_empenho": "516-2025",
            "id_fornecedor": f"CNPJ - PESSOA JURÍDICA - {CNPJ}",
            "nm_fornecedor": "FULANO 11813999805",
            "dt_emissao_despesa": "21/01/2025",
            "vl_despesa": "2.959,50",
        },
        {"id_fornecedor": "CPF - PESSOA FÍSICA - 123456", "nm_fornecedor": "BELTRANO"},
        {"id_fornecedor": f"CNPJ - PESSOA JURÍDICA - {CNPJ_RUIM}"},
    ]
    lido = t.ler_sp(json.dumps(registros).encode(), 2025, HOJE)
    assert lido.descartadas == 2
    (linha,) = lido.linhas
    assert (linha["cnpj"], linha["valor"], linha["data_emissao"]) == (
        CNPJ,
        2959.5,
        "2025-01-21",
    )
    assert linha["evento"] == "Empenhado"
    assert "FULANO" not in json.dumps(linha) and "nm_fornecedor" not in linha


def test_sp_lista_os_anos_sem_dado() -> None:
    assert t.anos_sem_dado({2015: 10, 2025: 0, 2026: 3, 2020: 0}) == [2020, 2025]


def _ce(elementos: list[dict]) -> bytes:
    return json.dumps({"elements": elementos}).encode()


def test_ce_junta_contratado_e_contrato_guarda_id_pncp_e_descarta_pessoal() -> None:
    base = {
        "codigo_municipio": "002",
        "numero_contrato": "01.27.2/2025",
        "data_contrato": "2025-02-04T00:00:00",
    }
    contratados = _ce(
        [
            {
                **base,
                "numero_documento_negociante": CNPJ,
                "nome_negociante": "NÃO ENTRA",
                "fone_negociante": "NÃO ENTRA",
                "data_referencia_doc": 202502,
            },
            {**base, "numero_documento_negociante": "12345678909"},
        ]
    )
    contratos = _ce(
        [
            {
                **base,
                "modalide_contrato": "OR",
                "valor_total_contrato": 30000.0,
                "data_inicio_vigencia_contrato": "2025-02-04T00:00:00",
                "data_fim_vigencia_contrato": "2026-02-04T00:00:00",
                "numero_id_contrato_pncp": "12345678000199-2-000001/2025",
                "descricao_objeto_contrato": "NÃO ENTRA",
            }
        ]
    )
    lido = t.ler_ce(contratados, contratos, HOJE)
    assert lido.descartadas == 1
    (linha,) = lido.linhas
    assert linha["cnpj"] == CNPJ and linha["valor"] == 30000.0
    assert linha["modalidade"] == "OR"
    assert linha["id_pncp"] == "12345678000199-2-000001/2025"
    assert linha["vigencia_fim"] == "2026-02-04"
    assert "NÃO ENTRA" not in json.dumps(linha, ensure_ascii=False)


def test_ce_id_pncp_em_branco_vira_none() -> None:
    base = {
        "codigo_municipio": "002",
        "numero_contrato": "1",
        "data_contrato": "2025-02-04T00:00:00",
    }
    contratados = _ce([{**base, "numero_documento_negociante": CNPJ}])
    contratos = _ce([{**base, "numero_id_contrato_pncp": " " * 25}])
    (linha,) = t.ler_ce(contratados, contratos, HOJE).linhas
    assert linha["id_pncp"] is None


def test_ce_contratado_sem_contrato_fica_marcado() -> None:
    base = {
        "codigo_municipio": "002",
        "numero_contrato": "9",
        "data_contrato": "2025-02-04T00:00:00",
    }
    (linha,) = t.ler_ce(
        _ce([{**base, "numero_documento_negociante": CNPJ}]), _ce([]), HOJE
    ).linhas
    assert linha["com_contrato"] == "False" and linha["valor"] is None


def _zip_rs(arquivos: dict[str, str]) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        for nome, texto in arquivos.items():
            z.writestr(nome, texto.encode("utf-8-sig"))
    return saida.getvalue()


CABECALHO_RS = (
    "CD_ORGAO;NM_ORGAO;NR_CONTRATO;ANO_CONTRATO;TP_DOCUMENTO;NR_DOCUMENTO;DT_INICIO_VIGENCIA;"
    "DT_FINAL_VIGENCIA;VL_CONTRATO;DT_ASSINATURA;DS_OBJETO"
)


def test_rs_so_tp_documento_j_e_nao_abre_pessoas_csv() -> None:
    contrato = "\n".join(
        [
            CABECALHO_RS,
            f"70701;CAMARA;5;2025;J;{CNPJ};01/02/2025;01/02/2026;1500.50;30/01/2025;NÃO ENTRA",
            "70701;CAMARA;6;2025;F;12345678909;01/02/2025;01/02/2026;10;30/01/2025;x",
            f"70701;CAMARA;7;2025;J;{CNPJ_RUIM};01/02/2025;01/02/2026;10;30/01/2025;x",
        ]
    )
    pacote = _zip_rs({"contrato.csv": contrato, "pessoas.csv": "CPF\n123.456.789-09"})
    lido = t.ler_rs(pacote, HOJE)
    assert lido.descartadas == 2
    (linha,) = lido.linhas
    assert linha["cnpj"] == CNPJ and linha["valor"] == 1500.5
    assert (
        linha["vigencia_inicio"] == "2025-02-01"
        and linha["data_assinatura"] == "2025-01-30"
    )
    assert "NÃO ENTRA" not in json.dumps(linha, ensure_ascii=False)


def test_rs_zip_sem_contrato_devolve_vazio() -> None:
    assert t.ler_rs(_zip_rs({"item.csv": "a"}), HOJE).linhas == []


def test_rs_indice_do_ckan_e_retomada() -> None:
    busca = {
        "result": {
            "results": [
                {
                    "name": "contratos-a",
                    "resources": [
                        {"url": "https://x/a.zip"},
                        {"url": "https://x/a.json"},
                    ],
                },
                {"name": "licitacoes-b", "resources": [{"url": "https://x/b.zip"}]},
                {"name": "contratos-c", "resources": [{"url": "https://x/c.ZIP"}]},
            ]
        }
    }
    pacotes = t.pacotes_de_contratos(json.dumps(busca).encode())
    assert pacotes == [
        ("contratos-a", "https://x/a.zip"),
        ("contratos-c", "https://x/c.ZIP"),
    ]
    assert t.pendentes([n for n, _ in pacotes], ["contratos-a"]) == ["contratos-c"]
