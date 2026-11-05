"""Coleta e carga de GO, MS e SP capital (scripts/carga_go_ms_sp.py): sem internet, só CNPJ, `disponivel_em` = download.

CNPJ 11.222.333/0001-81 tem DV certo; ...-82 é o mesmo com DV errado; nomes e documentos são inventados.
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts import carga_go_ms_sp as carga

HOJE = date(2026, 11, 4)
CNPJ = "11222333000181"
CNPJ_RUIM = "11222333000182"

CSV_GO = (
    "numero_licenca,versao,cpf_cnpj,nome_empreendimento,tipo_licenca,status,orgao,data_emissao,data_validade\n"
    f"L1,1,{CNPJ},NÃO ENTRA,LO,Vigente,SEMAD,2025-01-10,2027-01-10\n"
    "L2,1,***.123.456-**,NÃO ENTRA,LO,Vigente,SEMAD,2025-01-10,2027-01-10\n"
)
CSV_MS = (
    "Orgão,Credor,Cpf/Cnpj,Documento,Empenhado,Liquidado,Pago\n"
    f'SES,NÃO ENTRA,{CNPJ},2025NE1,"1.000,00","500,00","500,00"\n'
    f'SES,NÃO ENTRA,{CNPJ_RUIM},2025NE2,"1,00","1,00","1,00"\n'
)
CSV_SP = (
    "Número do Contrato;Número do Processo;CNPJ;Contratada;Data de Assinatura;Valor Total\n"
    f'10/2025;P1;{CNPJ};NÃO ENTRA;04/02/2025;"1.500,00"\n'
)


def _indice(
    *recursos: tuple[str, str],
    nome: str,
    outros: list[tuple[str, str]] = (),  # type: ignore[assignment]
) -> bytes:
    """Índice CKAN com um pacote; `outros` são pacotes extras (nome, endereço) de um recurso "2025-03"."""
    pacote = {
        "name": nome,
        "resources": [{"name": n, "url": u, "format": "CSV"} for n, u in recursos],
    }
    extras = [
        {
            "name": n,
            "resources": [{"name": "Outro 2025-03", "url": u, "format": "CSV"}],
        }
        for n, u in outros
    ]
    return json.dumps({"result": {"results": [pacote, *extras]}}).encode()


class _Fonte:
    """Dublê dos portais CKAN: devolve o índice e os CSVs e conta os pedidos."""

    def __init__(self, csv_sp: str = CSV_SP) -> None:
        self.pedidos: list[str] = []
        self.csv_sp = csv_sp

    def __call__(self, endereco: str) -> bytes:
        self.pedidos.append(endereco)
        if "dadosabertos.go.gov.br" in endereco and "package_search" in endereco:
            # o pacote do SGA (outro sistema) vem no mesmo índice e não pode ser baixado
            return _indice(
                ("Licenças 2025-03", "https://go.exemplo/a.csv"),
                ("Licenças 2019-03", "https://go.exemplo/velho.csv"),
                ("Licenças sem data", "https://go.exemplo/x.csv"),
                nome="licencas-ambientais-ipe",
                outros=[("licencas-ambientais-sga", "https://go.exemplo/sga.csv")],
            )
        if "dados.ms.gov.br" in endereco and "package_search" in endereco:
            return _indice(
                ("Despesas 03/2025", "https://ms.exemplo/b.csv"),
                nome="despesas-por-credor",
            )
        if "dados.prefeitura.sp.gov.br" in endereco and "package_search" in endereco:
            return _indice(
                ("Contratos 2025", "https://sp.exemplo/c.csv"),
                nome="base-de-compras-e-licitacoes",
            )
        if endereco.startswith("https://go."):
            return CSV_GO.encode()
        if endereco.startswith("https://ms."):
            return CSV_MS.encode()
        return self.csv_sp.encode()


def _baixar(destino: Path, fonte: _Fonte | None = None, **opcoes: object) -> _Fonte:
    fonte = fonte or _Fonte()
    carga.baixar(destino, anos=[2025], pausa=0, buscar=fonte, hoje=HOJE, **opcoes)  # type: ignore[arg-type]
    return fonte


def test_periodo_do_recurso_le_mes_e_ano_e_pula_o_que_nao_tem() -> None:
    assert carga.periodo_do_recurso("Lic 2025-03", "x", True) == (2025, 3)
    assert carga.periodo_do_recurso("Despesas 03/2025", "x", True) == (2025, 3)
    assert carga.periodo_do_recurso("sem data", "https://a/b_202511.csv", True) == (
        2025,
        11,
    )
    assert carga.periodo_do_recurso("Contratos 2025", "x", False) == (2025, 0)
    assert carga.periodo_do_recurso("sem data", "x", True) is None


def test_baixar_pede_so_o_ano_pedido_uma_vez_e_retoma(tmp_path: Path) -> None:
    destino = tmp_path / "novo"
    fonte = _baixar(destino)
    csvs = [p for p in fonte.pedidos if p.endswith(".csv")]
    assert sorted(csvs) == [
        "https://go.exemplo/a.csv",
        "https://ms.exemplo/b.csv",
        "https://sp.exemplo/c.csv",
    ]
    antes = len(fonte.pedidos)
    _baixar(destino, fonte)
    assert len(fonte.pedidos) == antes
    registro = (destino / carga.BAIXADOS).read_text(encoding="utf-8")
    assert registro.count("2026-11-04") == len(registro.splitlines())


def test_baixar_so_a_fonte_pedida(tmp_path: Path) -> None:
    fonte = _baixar(tmp_path / "novo", fontes=["sp"])
    assert all("prefeitura.sp" in p or "sp.exemplo" in p for p in fonte.pedidos)


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
        "go_licencas_ipe/2025",
        "ms_despesas/2025",
        "sp_capital_contratos/2025",
    }
    assert set(primeira.values()) == {"gravado"}
    assert set(carga.carregar(origem, saida).values()) == {"igual"}
    go = pd.read_parquet(saida / "go_licencas_ipe" / "2025.parquet")
    assert list(go["cnpj"]) == [CNPJ]
    assert set(go["disponivel_em"]) == {"2026-11-04"}
    ms = pd.read_parquet(saida / "ms_despesas" / "2025.parquet")
    assert list(ms["mes"]) == ["03"]
    assert list(ms["empenhado"]) == [1000.0]
    sp = pd.read_parquet(saida / "sp_capital_contratos" / "2025.parquet")
    assert list(sp["numero_contrato"]) == ["10/2025"]


def test_nenhuma_tabela_leva_nome_nem_cpf(tmp_path: Path) -> None:
    origem, saida = tmp_path / "baixado", tmp_path / "base"
    _baixar(origem)
    carga.carregar(origem, saida)
    proibidas = {"nome", "credor", "contratada", "razao_social", "objeto", "cpf"}
    for arquivo in saida.rglob("*.parquet"):
        assert not proibidas & set(pd.read_parquet(arquivo).columns)


def test_mapa_do_sp_que_nao_acha_o_documento_para_a_carga(tmp_path: Path) -> None:
    origem = tmp_path / "baixado"
    ruim = "Contrato;Documento_x\n10/2025;123\n"
    _baixar(origem, _Fonte(csv_sp=ruim), fontes=["sp"])
    with pytest.raises(SystemExit, match="nenhum CNPJ achado"):
        carga.carregar(origem, tmp_path / "base")


def test_mapa_do_sp_sem_numero_do_contrato_para_a_carga(tmp_path: Path) -> None:
    origem = tmp_path / "baixado"
    ruim = f"CNPJ;Valor\n{CNPJ};10,00\n"
    _baixar(origem, _Fonte(csv_sp=ruim), fontes=["sp"])
    with pytest.raises(SystemExit, match="numero_contrato"):
        carga.carregar(origem, tmp_path / "base")


def test_carga_sem_registro_de_download_sai_com_1(tmp_path: Path) -> None:
    assert carga.main(["--origem", str(tmp_path)]) == 1


def test_ms_usa_o_endereco_com_www_e_os_termos_estao_datados():
    """O host do MS só resolve com `www.` (linha 688); os termos dos três portais têm data."""
    from base.arquivo.orgaos import ORGAO_DA_FAMILIA
    from base.arquivo.registro import TERMOS_LIDOS_EM
    from base.licenca import familia_do_endereco

    assert carga.PORTAIS["ms"][0] == "https://www.dados.ms.gov.br"
    assert (ORGAO_DA_FAMILIA["msestado"].link or "").startswith("https://www.dados.ms.gov.br")
    assert familia_do_endereco("https://www.dados.ms.gov.br/dataset/x.csv") == "msestado"
    for familia in ("goias", "msestado", "spcapital"):
        assert TERMOS_LIDOS_EM[familia].isoformat() == "2026-11-05"
