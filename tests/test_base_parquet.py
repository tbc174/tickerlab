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


# --- versões (o que a CVM regrava não é apagado) -------------------------------------------------
OUTRAS = [{"url": "https://dados.cvm.gov.br/x.zip", "sha256": "cd" * 32}]


def test_mesmas_origens_nao_regravam(tabela, tmp_path, monkeypatch):
    from base.parquet import GRAVADO, IGUAL, gravar_com_versoes

    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    destino = tmp_path / "2005"
    assert (
        gravar_com_versoes(lambda: tabela, destino, ORIGENS, ["cnpj", "ano"]) == GRAVADO
    )
    montou = []
    assert (
        gravar_com_versoes(lambda: montou.append(1), destino, ORIGENS, ["cnpj"])
        == IGUAL
    )
    assert montou == []  # nem monta a tabela de novo


def test_origens_novas_guardam_a_versao_anterior(tabela, tmp_path, monkeypatch):
    from base.parquet import gravar_com_versoes

    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    destino = tmp_path / "2005"
    gravar_com_versoes(lambda: tabela, destino, ORIGENS, ["cnpj", "ano"])
    nova = tabela.assign(valor=9.0)
    gravar_com_versoes(lambda: nova, destino, OUTRAS, ["cnpj", "ano"])
    gravar_com_versoes(lambda: tabela, destino, ORIGENS, ["cnpj", "ano"])
    assert conferir_tabela(tmp_path / "2005.v1.parquet")
    assert conferir_tabela(tmp_path / "2005.v2.parquet")
    pd.testing.assert_frame_equal(
        ler_tabela(tmp_path / "2005.v2.parquet"), nova, check_dtype=False
    )
    pd.testing.assert_frame_equal(
        ler_tabela(tmp_path / "2005.parquet"), tabela, check_dtype=False
    )


def test_original_novo_com_o_mesmo_conteudo_nao_vira_versao(
    tabela, tmp_path, monkeypatch
):
    """Achado no fechamento da série 3 (PR 8): o BC devolve o cadastro do IF.data com outros bytes
    e o mesmo conteúdo; virava `.v1` igual à atual. Versão nova só quando o conteúdo muda; a tabela
    fica com o original anterior, que continua no acervo (a linhagem não quebra)."""
    from base.parquet import IGUAL, gravar_com_versoes

    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    destino = tmp_path / "202503"
    gravar_com_versoes(lambda: tabela, destino, ORIGENS, ["cnpj", "ano"])
    antes = (tmp_path / "202503.json").read_text(encoding="utf-8")
    resultado = gravar_com_versoes(
        lambda: tabela.iloc[::-1], destino, OUTRAS, ["cnpj", "ano"]
    )
    assert resultado == IGUAL
    assert not list(tmp_path.glob("202503.v*"))
    assert (tmp_path / "202503.json").read_text(encoding="utf-8") == antes


def test_tabela_de_entrada_nova_com_o_mesmo_conteudo_atualiza_as_origens(
    tabela, tmp_path, monkeypatch
):
    """Achado na série 4 (PR 1 no servidor): os emissores do FCA ganharam uma coluna e o painel dos
    fundos saiu igual; ficava o manifesto antigo, que apontava para a versão anterior dos emissores,
    já sobrescrita (a tabela de entrada não guarda versões) e a linhagem quebrava. Com uma tabela da
    base entre as origens, o manifesto passa a apontar as origens novas, sem versão nova."""
    from base.parquet import IGUAL, gravar_com_versoes, origens_gravadas

    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    destino = tmp_path / "painel"
    antes = [*ORIGENS, {"url": "fca/emissores.parquet", "sha256": "aa" * 32}]
    depois = [*ORIGENS, {"url": "fca/emissores.parquet", "sha256": "bb" * 32}]
    gravar_com_versoes(lambda: tabela, destino, antes, ["cnpj", "ano"])
    resultado = gravar_com_versoes(lambda: tabela, destino, depois, ["cnpj", "ano"])
    assert resultado == IGUAL
    assert not list(tmp_path.glob("painel.v*"))
    assert origens_gravadas(destino) == depois
    assert conferir_tabela(tmp_path / "painel.parquet")
