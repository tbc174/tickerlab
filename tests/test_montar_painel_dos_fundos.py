"""Painéis dos fundos por emissor e por empresa (série 3 da base de ML, PR 5), montados das tabelas
da base (CDA por ano, emissores do FCA e a tabela conferida). Sem internet."""

import json

import pandas as pd
import pytest

from base.parquet import conferir_tabela, gravar_tabela
from scripts import montar_painel_dos_fundos as montar
from src import versao_do_codigo as vc
from tests.test_base_ligacoes import ITAU, PETROBRAS, _posicoes

VERSAO = "f59fad3c1e6b0b5a9c1d2e3f4a5b6c7d8e9f0a1b"


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    raiz = tmp_path / "base"
    origem = [{"url": "https://dados.cvm.gov.br/x.zip", "sha256": "ab" * 32}]
    gravar_tabela(_posicoes(), raiz / "cda" / "2008", origem, ["competencia"])
    emissores = pd.DataFrame(
        {"emissor": ["ITUB", "PETR"], "cnpj": [ITAU, PETROBRAS], "empresa": ["ITAU", "PETROBRAS"],
         "primeiro_ano": [2018, 2018], "ultimo_ano": [2026, 2026], "conflito": [False, False]}
    )  # fmt: skip
    gravar_tabela(emissores, raiz / "fca" / "emissores", origem, ["emissor"])
    return raiz


def test_monta_paineis_cobertura_e_buracos(base):
    assert montar.main(["--base", str(base)]) == 0
    saida = base / "fundos"
    for arquivo in (
        "painel_emissor/2008",
        "painel_empresa/2008",
        "cobertura",
        "buracos",
    ):
        caminho = saida / f"{arquivo}.parquet"
        assert conferir_tabela(caminho), arquivo
        manifesto = json.loads(caminho.with_suffix(".json").read_text(encoding="utf-8"))
        assert manifesto["versao_do_codigo"] == VERSAO
        assert any("emissores_antigos.csv" in o["url"] for o in manifesto["origens"])
    empresa = pd.read_parquet(saida / "painel_empresa" / "2008.parquet").set_index(
        ["cnpj", "tipo"]
    )
    assert (
        empresa.loc[(ITAU, "comprado"), "valor"] == 180.0
    )  # ITAU (tabela) + ITUB (FCA)
    buracos = pd.read_parquet(saida / "buracos.parquet")
    assert buracos["emissor"].tolist() == ["XXXX"]


def test_versao_anterior_do_cda_nao_entra(base):
    """O `2008.v1.parquet` (o que a CVM regravou depois) é histórico, não entra no painel de hoje."""
    (base / "cda" / "2008.parquet").rename(base / "cda" / "2008.v1.parquet")
    (base / "cda" / "2008.json").rename(base / "cda" / "2008.v1.json")
    assert montar.main(["--base", str(base)]) == 1  # nenhum ano: nada a montar


def test_sem_a_versao_do_codigo_nao_grava(base, monkeypatch):
    monkeypatch.delenv(vc.VARIAVEL)
    monkeypatch.setattr(vc, "_perguntar_ao_git", lambda: None)
    with pytest.raises(vc.VersaoDesconhecidaError, match=vc.VARIAVEL):
        montar.main(["--base", str(base)])
    assert not (base / "fundos").exists()
