"""Tabela da base em Parquet com manifesto (série 3 da base de ML, PR 3): o mesmo conteúdo dá o mesmo
hash em qualquer ordem, o manifesto leva as origens e a versão do código, e a conferência acusa mudança."""

import json

import pandas as pd
import pytest

from base.parquet import conferir_tabela, gravar_tabela, hash_da_tabela, ler_tabela
from src import versao_do_codigo as vc

VERSAO = "587cb6c4d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7"
ORIGENS = [{"url": "https://dados.cvm.gov.br/x.zip", "sha256": "ab" * 32}]


@pytest.fixture
def tabela():
    return pd.DataFrame(
        {
            "cnpj": ["2", "1", "1"],
            "ano": [2020, 2021, 2020],
            "valor": [3.5, None, 1.0],
            "quando": pd.to_datetime(["2021-01-02", "2022-03-04", None]),
        }
    )


def test_mesmo_conteudo_em_outra_ordem_da_o_mesmo_hash(tabela):
    ordem = ["cnpj", "ano"]
    assert hash_da_tabela(tabela, ordem) == hash_da_tabela(tabela.iloc[::-1], ordem)
    mexida = tabela.assign(valor=tabela["valor"] + 0.01)
    assert hash_da_tabela(tabela, ordem) != hash_da_tabela(mexida, ordem)


def test_grava_com_manifesto_e_volta_igual(tabela, tmp_path, monkeypatch):
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    destino = gravar_tabela(
        tabela, tmp_path / "fca" / "emissores", ORIGENS, ["cnpj", "ano"]
    )
    assert destino == tmp_path / "fca" / "emissores.parquet"
    manifesto = json.loads(
        (tmp_path / "fca" / "emissores.json").read_text(encoding="utf-8")
    )
    assert manifesto["linhas"] == 3 and manifesto["origens"] == ORIGENS
    assert manifesto["versao_do_codigo"] == VERSAO
    assert manifesto["ordem"] == ["cnpj", "ano"]
    assert conferir_tabela(destino)
    pd.testing.assert_frame_equal(ler_tabela(destino), tabela, check_dtype=False)


def test_conferencia_acusa_parquet_mexido(tabela, tmp_path, monkeypatch):
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    destino = gravar_tabela(tabela, tmp_path / "t", ORIGENS, ["cnpj", "ano"])
    tabela.assign(valor=0.0).to_parquet(destino, index=False)
    assert not conferir_tabela(destino)


def test_sem_manifesto_nao_confere(tabela, tmp_path):
    destino = tmp_path / "solta.parquet"
    tabela.to_parquet(destino, index=False)
    assert not conferir_tabela(destino)
