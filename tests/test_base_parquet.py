"""Tabela da base em Parquet com manifesto (série 3 da base de ML, PR 3): o mesmo conteúdo dá o mesmo
hash em qualquer ordem, o manifesto leva as origens e a versão do código, e a conferência acusa mudança."""

import json

import pandas as pd
import pytest

from base import parquet
from base.parquet import (
    ACRESCIDO,
    GRAVADO,
    IGUAL,
    conferir_tabela,
    gravar_se_mudou,
    gravar_tabela,
    hash_da_tabela,
    ler_tabela,
)
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


# --- gravar_se_mudou: manifesto sempre, versão só quando uma linha antiga muda (ADR 0078) --------
CARIMBOS = ("montado_em", "versao_do_codigo")


def _com_carimbo(tabela: pd.DataFrame, quando: str) -> pd.DataFrame:
    return tabela.assign(montado_em=quando, versao_do_codigo=quando)


def _arquivos(pasta):
    return sorted(p.name for p in pasta.iterdir())


def test_gravar_se_mudou_grava_com_manifesto_na_primeira_vez(tabela, tmp_path):
    resultado = gravar_se_mudou(
        _com_carimbo(tabela, "1"),
        tmp_path / "t.parquet",
        ORIGENS,
        ["cnpj"],
        carimbos=CARIMBOS,
    )
    assert resultado == GRAVADO
    assert _arquivos(tmp_path) == ["t.json", "t.parquet"]
    assert conferir_tabela(tmp_path / "t.parquet")


def test_mesmo_dado_com_outro_carimbo_nao_regrava(tabela, tmp_path):
    destino = tmp_path / "t.parquet"
    gravar_se_mudou(
        _com_carimbo(tabela, "1"), destino, ORIGENS, ["cnpj"], carimbos=CARIMBOS
    )
    antes = destino.read_bytes(), (tmp_path / "t.json").read_bytes()
    resultado = gravar_se_mudou(
        _com_carimbo(tabela.iloc[::-1], "2"),
        destino,
        ORIGENS,
        ["cnpj"],
        carimbos=CARIMBOS,
    )
    assert resultado == IGUAL
    assert (destino.read_bytes(), (tmp_path / "t.json").read_bytes()) == antes


def test_linhas_novas_regravam_sem_versao(tabela, tmp_path):
    destino = tmp_path / "t.parquet"
    gravar_se_mudou(
        _com_carimbo(tabela, "1"), destino, ORIGENS, ["cnpj"], carimbos=CARIMBOS
    )
    nova = pd.DataFrame(
        {"cnpj": ["3"], "ano": [2022], "valor": [9.0], "quando": [pd.NaT]}
    )
    maior = _com_carimbo(pd.concat([tabela, nova], ignore_index=True), "2")
    resultado = gravar_se_mudou(maior, destino, ORIGENS, ["cnpj"], carimbos=CARIMBOS)
    assert resultado == ACRESCIDO
    assert _arquivos(tmp_path) == ["t.json", "t.parquet"]
    assert len(ler_tabela(destino)) == 4 and conferir_tabela(destino)


def test_linha_antiga_mudada_guarda_a_versao_anterior(tabela, tmp_path):
    destino = tmp_path / "t.parquet"
    gravar_se_mudou(
        _com_carimbo(tabela, "1"), destino, ORIGENS, ["cnpj"], carimbos=CARIMBOS
    )
    mexida = _com_carimbo(tabela.assign(valor=0.0), "2")
    assert (
        gravar_se_mudou(mexida, destino, ORIGENS, ["cnpj"], carimbos=CARIMBOS)
        == GRAVADO
    )
    assert _arquivos(tmp_path) == ["t.json", "t.parquet", "t.v1.json", "t.v1.parquet"]
    assert ler_tabela(tmp_path / "t.v1.parquet")["valor"].isna().sum() == 1
    assert conferir_tabela(destino)


def test_sem_versoes_so_regrava(tabela, tmp_path):
    destino = tmp_path / "t.parquet"
    gravar_se_mudou(tabela, destino, [], ["cnpj"], versoes=False)
    assert (
        gravar_se_mudou(tabela.assign(valor=0.0), destino, [], ["cnpj"], versoes=False)
        == GRAVADO
    )
    assert _arquivos(tmp_path) == ["t.json", "t.parquet"]
    assert ler_tabela(destino)["valor"].eq(0.0).all()


def test_arquivo_antigo_sem_manifesto_ganha_manifesto(tabela, tmp_path):
    destino = tmp_path / "t.parquet"
    _com_carimbo(tabela, "1").to_parquet(destino, index=False)
    resultado = gravar_se_mudou(
        _com_carimbo(tabela, "2"), destino, ORIGENS, ["cnpj"], carimbos=CARIMBOS
    )
    assert resultado == GRAVADO
    assert _arquivos(tmp_path) == ["t.json", "t.parquet"]
    assert conferir_tabela(destino)


def test_arquivo_antigo_sem_manifesto_e_dado_mudado_vira_versao(tabela, tmp_path):
    destino = tmp_path / "t.parquet"
    tabela.to_parquet(destino, index=False)
    gravar_se_mudou(tabela.assign(valor=0.0), destino, ORIGENS, ["cnpj"])
    assert _arquivos(tmp_path) == ["t.json", "t.parquet", "t.v1.parquet"]


def test_coluna_nova_conta_como_mudanca(tabela, tmp_path):
    destino = tmp_path / "t.parquet"
    gravar_se_mudou(tabela, destino, ORIGENS, ["cnpj"])
    assert (
        gravar_se_mudou(tabela.assign(extra=1), destino, ORIGENS, ["cnpj"]) == GRAVADO
    )
    assert (tmp_path / "t.v1.parquet").exists()


# --- o hash é do que fica no disco: coluna `object` com float do Python (1.0) volta do Parquet como
# float64 e vira texto "1"; o manifesto feito na memória não conferia (eventos_de_capital, 15/10) ---
@pytest.fixture
def com_floats_em_object():
    return pd.DataFrame(
        {"cnpj": ["1", "2"], "fator": pd.Series([1.0, 4768706356.09], dtype=object)}
    )


def test_manifesto_confere_com_coluna_object_de_floats(com_floats_em_object, tmp_path):
    destino = gravar_tabela(com_floats_em_object, tmp_path / "t", ORIGENS, ["cnpj"])
    assert conferir_tabela(destino)


def test_remontar_coluna_object_de_floats_e_igual(com_floats_em_object, tmp_path):
    destino = tmp_path / "t.parquet"
    gravar_se_mudou(com_floats_em_object, destino, ORIGENS, ["cnpj"])
    assert gravar_se_mudou(com_floats_em_object, destino, ORIGENS, ["cnpj"]) == IGUAL
    assert _arquivos(tmp_path) == ["t.json", "t.parquet"]


def test_manifesto_que_nao_confere_e_refeito_sem_versao(com_floats_em_object, tmp_path):
    destino = tmp_path / "t.parquet"
    gravar_se_mudou(com_floats_em_object, destino, ORIGENS, ["cnpj"])
    manifesto = json.loads((tmp_path / "t.json").read_text(encoding="utf-8"))
    manifesto["sha256_da_tabela"] = "0" * 64  # o manifesto errado de antes da correção
    (tmp_path / "t.json").write_text(json.dumps(manifesto), encoding="utf-8")
    assert gravar_se_mudou(com_floats_em_object, destino, ORIGENS, ["cnpj"]) == GRAVADO
    assert _arquivos(tmp_path) == ["t.json", "t.parquet"] and conferir_tabela(destino)


def test_versoes_nao_nascem_de_diferenca_de_tipo(
    com_floats_em_object, tmp_path, monkeypatch
):
    monkeypatch.setenv(vc.VARIAVEL, VERSAO)
    from base.parquet import gravar_com_versoes

    destino = tmp_path / "t"
    gravar_com_versoes(lambda: com_floats_em_object, destino, ORIGENS, ["cnpj"])
    outras = [{"url": "https://dados.cvm.gov.br/y.zip", "sha256": "cd" * 32}]
    assert (
        gravar_com_versoes(lambda: com_floats_em_object, destino, outras, ["cnpj"])
        == IGUAL
    )


def test_hash_em_pedacos_e_o_mesmo_da_tabela_inteira(monkeypatch):
    """O texto do hash sai em pedaços (a tabela do ONS de um ano não cabia na memória); o hash não muda,
    senão todo manifesto já gravado deixaria de conferir."""
    tabela = pd.DataFrame(
        {"a": ["x", None, "z", "w", "y"], "b": [1.5, 2.0, None, 4.25, 0.1],
         "c": pd.to_datetime(["2020-01-31", None, "2021-02-28", "2022-03-31", "2023-04-30"])}
    )  # fmt: skip
    inteira = hash_da_tabela(tabela, ["a"])
    monkeypatch.setattr(parquet, "LINHAS_POR_PEDACO", 2)
    assert hash_da_tabela(tabela, ["a"]) == inteira
    assert hash_da_tabela(tabela.iloc[:0], ["a"]) == hash_da_tabela(
        tabela.iloc[:0], ["a"]
    )
