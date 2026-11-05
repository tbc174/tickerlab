"""TCE-RN (base/tce_rn.py e scripts/carga_tce_rn.py): só pessoa jurídica, sem nomes, `disponivel_em` = download."""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from base import tce_rn
from scripts import carga_tce_rn as carga

AMOSTRAS = Path(__file__).resolve().parent.parent / "dados_de_exemplo" / "tce_rn"
HOJE = date(2026, 11, 4)


def _amostra(nome: str) -> bytes:
    return (AMOSTRAS / nome).read_bytes()


def test_unidades_guarda_todas_e_so_poe_cnpj_valido() -> None:
    lido = tce_rn.ler_unidades(_amostra("unidades_amostra.json"), HOJE)
    assert len(lido.linhas) == 5
    assert lido.descartadas == 2  # as duas sem CNPJ ficam na tabela, só sem o documento
    com = [u for u in lido.linhas if u["cnpj"]]
    assert len(com) == 3 and all(len(str(u["cnpj"])) == 14 for u in com)
    assert {"nome_unidade", "id_unidade", "disponivel_em"} <= set(lido.linhas[0])
    assert lido.linhas[0]["disponivel_em"] == "2026-11-04"
    assert lido.linhas[0]["inicio_atividade"] == "2000-05-29"


def test_licitacoes_uma_linha_por_lote_sem_texto_livre() -> None:
    lido = tce_rn.ler_licitacoes(_amostra("licitacoes_amostra.json"), 422, HOJE)
    assert [l["id_lote"] for l in lido.linhas] == [None, "1633765", "1633765"]
    primeira = lido.linhas[0]
    assert primeira["id_unidade"] == "422"
    assert primeira["data_publicacao"] == "2025-12-29"
    assert primeira["valor_orcado"] == 483655.26
    assert primeira["situacao"] == "HOMOLOGADA"
    assert primeira["disponivel_em"] == "2026-11-04"
    texto_livre = {"descricaoObjeto", "descricaoLote", "objeto", "descricao_objeto"}
    assert not texto_livre & set(primeira)
    assert "TEXTO LIVRE" not in json.dumps(lido.linhas)


def test_participantes_guarda_todos_com_classificacao_e_descarta_o_que_nao_e_cnpj() -> (
    None
):
    lido = tce_rn.ler_participantes(_amostra("participantes_amostra.json"), "99", HOJE)
    assert (
        lido.descartadas == 2
    )  # mascarado e CPF com zeros à esquerda (14 dígitos, DV de CNPJ errado)
    assert [(p["cnpj"], p["ordem_classificacao"]) for p in lido.linhas] == [
        ("11222333000181", "1"),
        ("44555666000181", "2"),
    ]
    assert lido.linhas[0]["valor_proposta"] == 232615.77
    assert lido.linhas[0]["id_lote"] == "99"
    assert not any("nome" in k for linha in lido.linhas for k in linha)
    assert "EXEMPLO" not in json.dumps(lido.linhas)


def test_lista_vazia_e_corpo_que_nao_e_lista() -> None:
    assert tce_rn.ler_participantes(b"[]", "0", HOJE).linhas == []
    assert tce_rn.ler_unidades(b'{"erro": "x"}', HOJE).linhas == []


class _Fonte:
    """Dublê da API: devolve as amostras e conta os pedidos."""

    def __init__(self) -> None:
        self.pedidos: list[str] = []

    def __call__(self, endereco: str) -> bytes:
        self.pedidos.append(endereco)
        if endereco.endswith("JurisdicionadosTCE/json"):
            return _amostra("unidades_amostra.json")
        if "/LicitacaoPublica/" in endereco:
            return _amostra("licitacoes_amostra.json")
        return _amostra("participantes_amostra.json")


def test_baixar_pede_uma_vez_cada_arquivo_e_retoma(tmp_path: Path) -> None:
    fonte = _Fonte()
    destino = tmp_path / "novo"
    carga.baixar(destino, [2025], 0, fonte, limite_de_unidades=2, hoje=HOJE)
    participantes = [p for p in fonte.pedidos if "ParticipantesDeLicitacao" in p]
    assert participantes == [
        f"{carga.ENDERECO_PARTICIPANTES}/1633765"
    ]  # lote 0 não é pedido; repetido, 1 vez
    assert any(p.endswith("/2025-01-01/2025-12-31") for p in fonte.pedidos)
    antes = len(fonte.pedidos)
    carga.baixar(destino, [2025], 0, fonte, limite_de_unidades=2, hoje=HOJE)
    assert len(fonte.pedidos) == antes  # nada pedido de novo
    registro = (destino / carga.BAIXADOS).read_text(encoding="utf-8")
    assert registro.count("2026-11-04") == len(registro.splitlines())


def test_baixar_recusa_pasta_que_nao_esta_vazia(tmp_path: Path) -> None:
    (tmp_path / "algo.txt").write_text("x")
    with pytest.raises(SystemExit):
        carga.baixar(tmp_path, [2025], 0, _Fonte(), hoje=HOJE)


def test_carregar_grava_as_tres_tabelas_e_a_segunda_vez_e_igual(tmp_path: Path) -> None:
    origem, saida = tmp_path / "baixado", tmp_path / "base"
    carga.baixar(origem, [2025], 0, _Fonte(), limite_de_unidades=1, hoje=HOJE)
    primeira = carga.carregar(origem, saida)
    assert set(primeira) == {"unidades", "licitacoes/2025", "participantes/2025"}
    assert set(primeira.values()) == {"gravado"}
    assert set(carga.carregar(origem, saida).values()) == {"igual"}
    participantes = pd.read_parquet(saida / "tce_rn" / "participantes" / "2025.parquet")
    assert list(participantes["ordem_classificacao"]) == ["1", "2"]
    assert set(participantes["disponivel_em"]) == {"2026-11-04"}
    unidades = pd.read_parquet(saida / "tce_rn" / "unidades.parquet")
    assert len(unidades) == 5


def test_carga_sem_arquivos_sai_com_1(tmp_path: Path) -> None:
    assert carga.main(["--origem", str(tmp_path)]) == 1
