"""Coleta e carga dos TCEs de PE, SP, CE e RS (scripts/carga_tces.py): sem internet, só CNPJ, `disponivel_em` = download.

CNPJ 11.222.333/0001-81 tem DV certo; ...-82 é o mesmo com DV errado; nomes e documentos são inventados.
"""

import io
import json
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts import carga_tces as carga

HOJE = date(2026, 11, 4)
CNPJ = "11222333000181"
CNPJ_RUIM = "11222333000182"


def _pe(itens: list[dict], tamanho: int | None = None) -> bytes:
    resposta = {
        "status": "OK",
        "tamanhoResultado": str(tamanho or len(itens)),
        "conteudo": itens,
    }
    return json.dumps({"resposta": resposta}, ensure_ascii=False).encode("iso-8859-1")


def _zip_rs(linhas: list[str]) -> bytes:
    cabecalho = "CD_ORGAO;NR_LICITACAO;ANO_LICITACAO;NR_CONTRATO;ANO_CONTRATO;TP_DOCUMENTO;NR_DOCUMENTO;VL_CONTRATO"
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as pacote:
        pacote.writestr("contrato.csv", "\n".join([cabecalho, *linhas]))
        pacote.writestr("pessoas.csv", "NR_DOCUMENTO\n12345678909")
    return saida.getvalue()


class _Fonte:
    """Dublê das APIs dos tribunais: devolve respostas pequenas e conta os pedidos."""

    def __init__(
        self, tamanho_pe: int | None = None, tamanho_licitacoes: int | None = None
    ) -> None:
        self.pedidos: list[str] = []
        self.tamanho_pe = tamanho_pe
        self.tamanho_licitacoes = tamanho_licitacoes

    def __call__(self, endereco: str) -> bytes:
        self.pedidos.append(endereco)
        if "DadosAbertos/Contratos!" in endereco:
            ano = endereco.rsplit("=", 1)[-1]
            return _pe(
                [
                    {
                        "NumeroDocumentoAjustado": CNPJ,
                        "CodigoContrato": f"c{ano}",
                        "Valor": "10.50",
                        "RazaoSocial": "NÃO ENTRA",
                    },
                    {"NumeroDocumentoAjustado": CNPJ_RUIM, "CodigoContrato": "x"},
                ],
                self.tamanho_pe,
            )
        if "DadosAbertos/TermoAditivo!" in endereco:
            return _pe(
                [
                    {
                        "NumeroDocumentoAjustado": CNPJ,
                        "CodigoContrato": "c2025",
                        "NumeroTermoAditivo": "001",
                    }
                ]
            )
        if "LicitacoesDetalhes!" in endereco:
            vencedor = {
                "NUMERODOCUMENTOAJUSTADO": f"{CNPJ}   ",
                "ADJUDICADA": "Vencedor",
                "CODIGOPL": f"pl-{endereco[-5:]}",
                "TOTALADJUDICADOLICITANTE": "4000.0000",
                "DATAPUBLICACAOHOMOLOGACAO": "2025-06-10 03:00:00.0",
                "RAZAOSOCIAL": "NÃO ENTRA",
                "DESCRICAOOBJETO": "NÃO ENTRA",
            }
            return _pe(
                [
                    vencedor,
                    {**vencedor, "ADJUDICADA": "Não Vencedor"},
                    {**vencedor, "NUMERODOCUMENTOAJUSTADO": "***.***.004-02"},
                ],
                self.tamanho_licitacoes,
            )
        if endereco.endswith("/municipios"):
            return json.dumps([{"municipio": "adamantina"}]).encode()
        if "/despesas/" in endereco:
            return json.dumps(
                [
                    {
                        "mes": "Janeiro",
                        "evento": "Empenhado",
                        "nr_empenho": "1-2025",
                        "id_fornecedor": f"CNPJ - PESSOA JURÍDICA - {CNPJ}",
                        "nm_fornecedor": "NÃO ENTRA",
                        "dt_emissao_despesa": "25/01/2025",
                        "vl_despesa": "100,00",
                    },
                    {"id_fornecedor": "CPF - PESSOA FÍSICA - 123456"},
                ]
            ).encode()
        if "package_search" in endereco:
            pacote = {
                "name": "contratos-orgao-1",
                "resources": [{"url": "https://dados.exemplo/orgao1.zip"}],
            }
            return json.dumps({"result": {"results": [pacote]}}).encode()
        return _zip_rs(
            [
                f"7;1;2024;9;2025;J;{CNPJ};1.500,00".replace(".", "", 1),
                "7;1;2024;10;2025;F;12345678909;5,00",
            ]
        )


def _baixar(destino: Path, fonte: _Fonte | None = None, **opcoes: object) -> _Fonte:
    fonte = fonte or _Fonte()
    carga.baixar(destino, anos=[2025], pausa=0, buscar=fonte, hoje=HOJE, **opcoes)  # type: ignore[arg-type]
    return fonte


def test_baixar_pede_uma_vez_cada_arquivo_e_retoma(tmp_path: Path) -> None:
    destino = tmp_path / "novo"
    fonte = _baixar(destino)
    assert (
        "https://sistemas.tce.pe.gov.br/DadosAbertos/Contratos!json?AnoContrato=2025"
        in fonte.pedidos
    )
    assert any("/despesas/adamantina/2025/12" in p for p in fonte.pedidos)
    assert sum("/despesas/" in p for p in fonte.pedidos) == 12
    assert sum(p.endswith(".zip") for p in fonte.pedidos) == 1
    antes = len(fonte.pedidos)
    _baixar(destino, fonte)
    assert len(fonte.pedidos) == antes
    registro = (destino / carga.BAIXADOS).read_text(encoding="utf-8")
    assert registro.count("2026-11-04") == len(registro.splitlines())


def test_baixar_so_o_tribunal_pedido(tmp_path: Path) -> None:
    fonte = _baixar(tmp_path / "novo", tribunais=["rs"])
    assert all("tce.pe" not in p and "transparencia" not in p for p in fonte.pedidos)


def test_baixar_para_quando_a_resposta_do_pe_chega_no_teto(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="teto"):
        _baixar(tmp_path / "novo", _Fonte(tamanho_pe=carga.TETO_DO_PEDIDO_PE))


def test_baixar_fatia_as_licitacoes_do_pe_por_ano_e_modalidade(tmp_path: Path) -> None:
    fonte = _baixar(tmp_path / "novo", tribunais=["pe"])
    base = "https://sistemas.tce.pe.gov.br/DadosAbertos/LicitacoesDetalhes!json"
    pedidos = [p for p in fonte.pedidos if p.startswith(base)]
    assert f"{base}?ANOMODALIDADE=2025&CODIGOMODALIDADE=8" in pedidos
    assert len(pedidos) == len(carga.MODALIDADES_PE)


def test_baixar_para_quando_uma_fatia_de_licitacoes_chega_no_teto(
    tmp_path: Path,
) -> None:
    with pytest.raises(SystemExit, match="modalidade 1"):
        _baixar(
            tmp_path / "novo",
            _Fonte(tamanho_licitacoes=carga.TETO_DO_PEDIDO_PE),
            tribunais=["pe"],
        )


def test_licitacoes_do_pe_so_o_vencedor_pessoa_juridica(tmp_path: Path) -> None:
    origem, saida = tmp_path / "baixado", tmp_path / "base"
    _baixar(origem, tribunais=["pe"])
    carga.carregar(origem, saida)
    lic = pd.read_parquet(saida / "tce_pe_licitacoes" / "2025.parquet")
    assert set(lic["cnpj"]) == {CNPJ}
    assert len(lic) == len(
        carga.MODALIDADES_PE
    )  # uma linha por fatia (o código da PL muda)
    assert set(lic["valor_adjudicado"]) == {4000.0}
    assert set(lic["data_homologacao"]) == {"2025-06-10"}
    assert set(lic["disponivel_em"]) == {"2026-11-04"}


def test_baixar_recusa_pasta_que_nao_esta_vazia(tmp_path: Path) -> None:
    (tmp_path / "algo.txt").write_text("x")
    with pytest.raises(SystemExit):
        _baixar(tmp_path)


def test_carregar_grava_uma_tabela_por_ano_so_com_cnpj_e_a_segunda_vez_e_igual(
    tmp_path: Path,
) -> None:
    origem, saida = tmp_path / "baixado", tmp_path / "base"
    _baixar(origem)
    primeira = carga.carregar(origem, saida)
    assert set(primeira) == {
        "tce_pe_contratos/2025",
        "tce_pe_aditivos/2025",
        "tce_pe_licitacoes/2025",
        "tce_sp_despesas/2025",
        "tce_rs_contratos/2025",
    }
    assert set(primeira.values()) == {"gravado"}
    assert set(carga.carregar(origem, saida).values()) == {"igual"}
    pe = pd.read_parquet(saida / "tce_pe_contratos" / "2025.parquet")
    assert list(pe["cnpj"]) == [CNPJ]
    assert set(pe["disponivel_em"]) == {"2026-11-04"}
    sp = pd.read_parquet(saida / "tce_sp_despesas" / "2025.parquet")
    assert set(sp["municipio"]) == {"adamantina"}
    rs = pd.read_parquet(saida / "tce_rs_contratos" / "2025.parquet")
    assert list(rs["cnpj"]) == [CNPJ]


def test_nenhuma_tabela_leva_nome_nem_cpf(tmp_path: Path) -> None:
    origem, saida = tmp_path / "baixado", tmp_path / "base"
    _baixar(origem)
    carga.carregar(origem, saida)
    for arquivo in saida.rglob("*.parquet"):
        colunas = set(pd.read_parquet(arquivo).columns)
        assert not {"razao_social", "nome", "nm_fornecedor", "objeto", "cpf"} & colunas


def test_ce_le_os_pares_postos_a_mao(tmp_path: Path) -> None:
    origem, saida = tmp_path / "baixado", tmp_path / "base"
    (origem / "ce").mkdir(parents=True)
    (origem / carga.BAIXADOS).write_text("")
    chave = {
        "codigo_municipio": "002",
        "numero_contrato": "1/2025",
        "data_contrato": "2025-02-04T00:00:00",
    }
    contratados = {"elements": [{**chave, "numero_documento_negociante": CNPJ}]}
    contratos = {"elements": [{**chave, "valor_total_contrato": "10,00"}]}
    (origem / "ce" / "contratados_002_2025.json").write_text(json.dumps(contratados))
    (origem / "ce" / "contratos_002_2025.json").write_text(json.dumps(contratos))
    resultado = carga.carregar(origem, saida)
    assert resultado == {"tce_ce_contratos/2025": "gravado"}
    assert list(
        pd.read_parquet(saida / "tce_ce_contratos" / "2025.parquet")["cnpj"]
    ) == [CNPJ]


def test_carga_sem_registro_de_download_sai_com_1(tmp_path: Path) -> None:
    assert carga.main(["--origem", str(tmp_path)]) == 1
